"""
revive.py  -  The ReVive recovery layer.

    DETECT -> DIAGNOSE -> TWO GATES -> RECOVER -> VERIFY -> (ADAPT) -> CLOSE or ESCALATE

Gate A  "Are we sure what the fault is?"  -> the diagnosis must name exactly ONE cause.
Gate B  "Is this action allowed and safe?" -> policy by risk tier + a dry run on a copy.
Failing either gate means: escalate to a human.

Safety rules baked in:
  * Hold before you heal: payments to a suspicious account are held at once.
  * A payment in UNKNOWN state is NEVER resent blindly. We query the bank first.
  * We may only resubmit after the bank confirms FAILED, using the SAME key.
  * Maximum 2 autonomous attempts, then stop and escalate.
  * An incident closes only if the business state is correct (verified).
"""
import json
import os

from detect import detect
from diagnose import diagnose

MAX_ATTEMPTS = 2

# ---------------- risk tiers (the action-safety policy) ----------------
RISK = {
    "replay_dropped_invoices": "LOW",
    "replay_dropped_invoices_one_by_one": "LOW",
    "query_bank_status": "LOW",
    "query_bank_status_after_wait": "LOW",
    "hold_payment": "LOW",
    "rollback_sync_batch": "MEDIUM",
    "restore_verified_iban_per_vendor": "MEDIUM",
    "change_bank_details": "HIGH",          # never automatic
    "resend_while_unknown": "HIGH",         # never automatic
    "reverse_settled_payment": "HIGH",      # never automatic
}
READ_ONLY = {"query_bank_status", "query_bank_status_after_wait"}   # no dry run needed

# For each diagnosed cause: the actions ReVive may try, in order (attempt 1, attempt 2).
PLAYBOOK = {
    "INTAKE_DROP": ["replay_dropped_invoices", "replay_dropped_invoices_one_by_one"],
    "SYNC_IBAN_CORRUPTION": ["rollback_sync_batch", "restore_verified_iban_per_vendor"],
    "BANK_TIMEOUT_UNKNOWN": ["query_bank_status", "query_bank_status_after_wait"],
    # What a naive agent would do about a suspicious account change is "just update it".
    # ReVive proposes it so that gate B can visibly BLOCK it.
    "POSSIBLE_FRAUD": ["change_bank_details"],
    "UNKNOWN_OTHER": [],
}


# ======================= recovery actions =======================
def _affected_vendors(finding):
    return [v["vendor"] for v in finding["evidence"]["vendors"]]


def act_replay(sim, finding, name="replay_dropped_invoices"):
    if sim.noop(name):
        return {"ok": True, "note": "action reported success but changed nothing"}
    n, held = 0, 0
    for iid in finding["evidence"]["missing"]:
        if iid not in sim.invoices:
            sim.add_to_system(sim.source[iid])
            n += 1
            v = sim.vendors[sim.source[iid]["vendor"]]
            if v["iban"] != v["verified_iban"]:          # never let a replay reach a bad payee
                hold_invoices(sim, [sim.source[iid]["vendor"]])
                held += 1
    note = f"replayed {n} dropped invoice(s) from the source queue"
    return {"ok": True, "note": note + (f" ({held} held: payee account not verified)" if held else "")}


def act_replay_one_by_one(sim, finding):
    return act_replay(sim, finding, name="replay_dropped_invoices_one_by_one")


def act_restore_iban(sim, finding, name="rollback_sync_batch"):
    if sim.noop(name):
        return {"ok": True, "note": "action reported success but changed nothing"}
    targets = set(_affected_vendors(finding))
    if name == "rollback_sync_batch":
        # V2 fix (found by the held-out set): roll back the WHOLE sync batch, not just
        # the vendors that happen to have open invoices right now.
        batches = {sim.vendors[v]["sync_batch"] for v in targets if sim.vendors[v]["sync_batch"]}
        targets |= {vid for vid, d in sim.vendors.items() if d["sync_batch"] in batches}
    for vid in targets:
        v = sim.vendors[vid]
        v["iban"], v["sync_batch"] = v["verified_iban"], None
    return {"ok": True, "note": f"restored last verified bank accounts for {len(targets)} vendor(s)"}


def act_restore_iban_per_vendor(sim, finding):
    return act_restore_iban(sim, finding, name="restore_verified_iban_per_vendor")


def _query_and_reconcile(sim, finding):
    ev = finding["evidence"]
    inv = sim.invoices[ev["invoice"]]
    try:
        status = sim.bank.query(ev["txn_key"])
    except Exception as e:
        return {"ok": False, "note": f"bank unreachable ({e}); cannot confirm the payment"}
    if status == "SETTLED":
        sim.mark_paid(inv)
        return {"ok": True, "note": "bank confirms SETTLED; recorded in ledger; NOTHING was resent"}
    if status == "FAILED":
        # Allowed: bank confirmed failure, resubmit with the SAME idempotency key.
        r = sim.bank.submit(ev["txn_key"], inv["payee_iban"], inv["amount"], inv["id"])
        if r == "SETTLED":
            sim.mark_paid(inv)
            return {"ok": True, "note": "bank confirmed FAILED; resubmitted with the same key; now SETTLED"}
        return {"ok": False, "note": "bank confirmed FAILED; resubmit did not settle"}
    return {"ok": False, "note": "bank has no clear record; NOT safe to resend automatically"}


def act_query(sim, finding):
    return _query_and_reconcile(sim, finding)


def act_query_after_wait(sim, finding):
    sim.wait(3)      # give the bank time to recover, then ask again
    return _query_and_reconcile(sim, finding)


def act_change_bank_details(sim, finding):     # pragma: no cover - blocked by gate B
    raise RuntimeError("HIGH-risk action must never run automatically")


ACTIONS = {
    "replay_dropped_invoices": act_replay,
    "replay_dropped_invoices_one_by_one": act_replay_one_by_one,
    "rollback_sync_batch": act_restore_iban,
    "restore_verified_iban_per_vendor": act_restore_iban_per_vendor,
    "query_bank_status": act_query,
    "query_bank_status_after_wait": act_query_after_wait,
    "change_bank_details": act_change_bank_details,
}


# ======================= containment (hold before you heal) =======================
def hold_invoices(sim, vendor_ids):
    held = []
    for inv in sim.invoices.values():
        if inv["vendor"] in vendor_ids and inv["status"] in ("RECEIVED", "MATCHED", "APPROVED"):
            inv["held_from"], inv["status"] = inv["status"], "HELD"
            held.append(inv["id"])
    return held


def release_hold(sim, vendor_ids):
    for inv in sim.invoices.values():
        if inv["vendor"] in vendor_ids and inv["status"] == "HELD":
            inv["status"], inv["held_from"] = inv["held_from"] or "APPROVED", None


# ======================= verification =======================
def verify(sim, finding):
    """An incident is VERIFIED only if: (1) the business rule holds again,
    (2) the interrupted work actually finished, (3) nothing unsafe happened.
    Check (1) is done BEFORE any money moves."""
    checks = []
    k, ev = finding["kind"], finding["evidence"]

    if k == "conservation_gap":
        ok1 = all(i in sim.invoices for i in ev["missing"])
        checks.append(("every received invoice is accounted for", ok1))
        if ok1:
            for _ in range(3):
                sim.step()
            ok2 = all(sim.invoices[i]["status"] == "PAID" for i in ev["missing"])
            checks.append(("replayed invoices were completed (paid)", ok2))

    elif k == "payee_iban_mismatch":
        vids = _affected_vendors(finding)
        ok1 = all(sim.vendors[v]["iban"] == sim.vendors[v]["verified_iban"] for v in vids)
        checks.append(("payee accounts match the last verified accounts", ok1))
        if ok1:
            release_hold(sim, vids)          # now it is safe to let the payments go
            for _ in range(3):
                sim.step()
            ids = [i for d in ev["vendors"] for i in d["open_invoices"]]
            ok2 = all(sim.invoices[i]["status"] == "PAID" for i in ids)
            checks.append(("held invoices were completed (paid) to the verified account", ok2))

    elif k == "unknown_payment":
        inv = sim.invoices[ev["invoice"]]
        ok1 = inv["status"] == "PAID" and inv["pay_state"] == "SETTLED"
        checks.append(("payment result confirmed and recorded", ok1))

    s = sim.safety()
    checks.append(("no duplicate payments", s["duplicate_payments"] == 0))
    checks.append(("no misdirected payments", s["misdirected_payments"] == 0))
    return {"ok": all(c[1] for c in checks), "checks": [{"check": n, "pass": bool(p)} for n, p in checks]}


# ======================= the ReVive agent =======================
class Revive:
    def __init__(self, diagnoser=diagnose, save_dir=None):
        self.diagnoser = diagnoser
        self.save_dir = save_dir
        self.incidents = []
        self._n = 0

    # ----- main entry: called by the simulator twice per tick -----
    def run(self, sim):
        findings = detect(sim)
        if not findings:
            return
        # most dangerous first: money going to the wrong account before anything else
        findings.sort(key=lambda f: 0 if f["kind"] == "payee_iban_mismatch" else 1)
        # CONTAIN first: hold payments to any suspicious account BEFORE anything else.
        pre_held = {}
        for f in findings:
            if f["kind"] == "payee_iban_mismatch":
                pre_held[f["key"]] = hold_invoices(sim, _affected_vendors(f))
        for f in findings:
            self.handle(sim, f, pre_held.get(f["key"], []))

    # ----- one incident from start to finish -----
    def handle(self, sim, finding, held_ids):
        self._n += 1
        inc = {"id": f"INC-{self._n:03d}", "kind": finding["kind"],
               "symptoms": finding["summary"], "evidence": finding["evidence"],
               "detected_tick": sim.tick_no, "timeline": [], "attempts": [],
               "held_invoices": held_ids}

        def stage(name, note=""):
            inc["timeline"].append({"stage": name, "tick": sim.tick_no, "note": note})

        stage("DETECT", finding["summary"])
        if held_ids:
            stage("CONTAIN", f"payments held for {len(held_ids)} invoice(s) before any repair")

        # ---- DIAGNOSE ----
        dx = self.diagnoser(finding)
        inc["diagnosis"] = dx
        note = f"possible causes: {dx['prediction_set']}"
        if dx.get("method", "rules") != "rules":
            note = f"[{dx['method']}] " + note
        if dx.get("explanation"):
            note += f" - {dx['explanation']}"
        stage("DIAGNOSE", note)

        # ---- GATE A: are we sure? ----
        if len(dx["prediction_set"]) != 1 or dx["prediction_set"][0] == "UNKNOWN_OTHER":
            inc["gate_a"] = {"pass": False, "reason": f"diagnosis is not certain: {dx['prediction_set']}"}
            stage("GATE A", "FAIL - not sure what the fault is")
            return self._escalate(sim, finding, inc, inc["gate_a"]["reason"])
        cause = dx["prediction_set"][0]
        inc["cause"] = cause
        inc["gate_a"] = {"pass": True, "reason": f"single cause: {cause}"}
        stage("GATE A", f"PASS - {cause}")

        playbook = PLAYBOOK[cause]

        # ---- up to MAX_ATTEMPTS: GATE B -> (dry run) -> act -> VERIFY -> ADAPT ----
        for idx in range(MAX_ATTEMPTS):
            if idx >= len(playbook):
                break
            action = playbook[idx]
            tier = RISK[action]

            # GATE B: policy
            if tier == "HIGH":
                inc["gate_b"] = {"pass": False, "action": action, "tier": tier,
                                 "reason": "HIGH-risk action: never automatic"}
                stage("GATE B", f"BLOCKED - {action} is HIGH risk")
                return self._escalate(sim, finding, inc, f"action '{action}' is not permitted automatically")
            if tier == "MEDIUM" and len(dx["prediction_set"]) != 1:
                inc["gate_b"] = {"pass": False, "action": action, "tier": tier, "reason": "diagnosis not unique"}
                stage("GATE B", "BLOCKED - MEDIUM risk needs a single diagnosis")
                return self._escalate(sim, finding, inc, "medium-risk action needs a single diagnosis")

            # GATE B: dry run on a copy of the system
            if action not in READ_ONLY:
                trial = sim.copy_for_dry_run()
                r = ACTIONS[action](trial, finding)
                v = verify(trial, finding)
                dry_ok = r["ok"] and v["ok"]
                inc["gate_b"] = {"pass": dry_ok, "action": action, "tier": tier, "dry_run": v["checks"]}
                stage("GATE B", f"{'PASS' if dry_ok else 'FAIL'} - dry run of {action} ({tier})")
                if not dry_ok:
                    inc["attempts"].append({"attempt": idx + 1, "action": action, "tier": tier,
                                            "result": "dry run failed - not executed", "verified": False})
                    continue
            else:
                inc["gate_b"] = {"pass": True, "action": action, "tier": tier, "dry_run": "not needed (read-only)"}
                stage("GATE B", f"PASS - {action} is read-only")

            # RECOVER (live)
            res = ACTIONS[action](sim, finding)
            stage("RECOVER", f"attempt {idx + 1}: {action} -> {res['note']}")

            # VERIFY
            ver = verify(sim, finding)
            stage("VERIFY", "PASS" if ver["ok"] else "FAIL")
            inc["attempts"].append({"attempt": idx + 1, "action": action, "tier": tier,
                                    "result": res["note"], "verified": ver["ok"], "checks": ver["checks"]})
            if ver["ok"]:
                return self._close(sim, finding, inc)
            if idx + 1 < MAX_ATTEMPTS and idx + 1 < len(playbook):
                stage("ADAPT", "fix did not verify - switching to a different strategy")

        return self._escalate(sim, finding, inc, f"not verified after {len(inc['attempts'])} autonomous attempt(s)")

    # ----- outcomes -----
    def _close(self, sim, finding, inc):
        inc["outcome"] = "VERIFIED_CLOSED"
        inc["closed_tick"] = sim.tick_no
        inc["escalation"] = None
        inc["money_protected_sar"] = self._at_risk(finding)
        inc["timeline"].append({"stage": "CLOSED", "tick": sim.tick_no, "note": "business state verified"})
        return self._finish(inc)

    def _escalate(self, sim, finding, inc, reason):
        sim.acknowledged.add(finding["key"])
        # containment stays in place: make sure risky payments are held
        if finding["kind"] == "payee_iban_mismatch":
            hold_invoices(sim, _affected_vendors(finding))
        inc["outcome"] = "ESCALATED"
        inc["closed_tick"] = sim.tick_no
        s = sim.safety()
        inc["money_protected_sar"] = (self._at_risk(finding)
                                      if s["duplicate_payments"] == 0 and s["misdirected_payments"] == 0 else 0)
        causes = inc.get("diagnosis", {}).get("prediction_set", [])
        inc["escalation"] = {
            "reason": reason,
            "for_a_human": "Review the evidence and decide. ReVive has NOT resent, reversed or changed any bank details.",
            "possible_causes": causes,
            "cited_evidence": inc.get("diagnosis", {}).get("cited_evidence", []),
            "actions_tried": [{"action": a["action"], "result": a["result"], "verified": a["verified"]}
                              for a in inc["attempts"]],
            "still_held_invoices": inc["held_invoices"],
        }
        inc["timeline"].append({"stage": "ESCALATED", "tick": sim.tick_no, "note": reason})
        return self._finish(inc)

    def _at_risk(self, finding):
        ev, k = finding["evidence"], finding["kind"]
        if k == "conservation_gap":
            return ev["missing_value"]
        if k == "payee_iban_mismatch":
            return ev["open_amount"]
        if k == "unknown_payment":
            return ev["amount"]
        return 0

    def _finish(self, inc):
        self.incidents.append(inc)
        if self.save_dir:
            os.makedirs(self.save_dir, exist_ok=True)
            with open(os.path.join(self.save_dir, f"{inc['id']}.json"), "w") as f:
                json.dump(inc, f, indent=2)
        return inc
