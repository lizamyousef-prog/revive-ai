"""
dash_api.py  -  Runs one scenario with one agent and returns plain data for the dashboard.
"""
from baseline import NaiveAgent
from revive import Revive
from llm_diagnose import make_llm_diagnoser, ai_available
from llm_summary import make_summarizer
import scenarios as S
import held_out as H

# key -> (button label, one-line story, function)
CASES = {
    "d1":  ("Month-end spike: invoices vanish silently", "8 invoices arrive. The intake agent quietly loses 3. No error, no crash.", S.d1_invisible_failure),
    "d2a": ("Sync bug corrupts supplier accounts", "A nightly sync bug truncates the bank accounts of 3 suppliers.", S.d2_sync_bug),
    "d2c": ("Suspicious account change", "One supplier suddenly has a totally different bank account before a SAR 300,000 invoice.", S.d2_fraud),
    "d2b": ("Ambiguous: looks like a bug, or fraud?", "One supplier's account looks truncated, but it changed recently and the invoice is large.", S.d2_ambiguous),
    "d2m": ("Main demo: bug, then suspicious change", "A sync bug is repaired. Then a suspicious change arrives and must NOT be repaired automatically.", S.d2_main),
    "d3a": ("Bank times out, then goes offline", "A payment gets no reply and the bank is down. Did it go through? Nobody knows.", S.d3_bank_down),
    "d3b": ("Bank times out, then comes back", "Same timeout, but the bank recovers. ReVive asks the bank instead of paying again.", S.d3_bank_recovers),
    "d4":  ("First repair silently fails", "The first repair claims success but changes nothing. Does anyone notice?", S.d4_fix_silently_fails_once),
    "d5":  ("Both repairs fail", "Two different repairs both do nothing. The agent must know when to stop.", S.d5_fix_fails_twice),
    "h1":  ("Two faults at once (unseen test)", "Invoices vanish AND supplier accounts are corrupted at the same moment.", H.h1_two_faults_at_once),
    "h3":  ("Timeout + sync bug (unseen test)", "The bank times out while two suppliers have corrupted accounts.", H.h3_timeout_then_sync_bug),
}


def catalog():
    return [{"key": k, "label": v[0], "story": v[1]} for k, v in CASES.items()]


def run_case(key, agent_name, seed):
    label, story, fn = CASES[key]
    agent = Revive(diagnoser=make_llm_diagnoser(), summarizer=make_summarizer()) if agent_name == "revive" else NaiveAgent()
    sim, agent = fn(seed=seed, agent=agent)

    incidents = []
    for inc in agent.incidents:
        if agent_name == "revive":
            incidents.append({"id": inc["id"], "symptoms": inc["symptoms"], "outcome": inc["outcome"],
                              "timeline": inc["timeline"], "money_protected": inc["money_protected_sar"],
                              "escalation": inc["escalation"], "attempts": len(inc["attempts"])})
        else:
            incidents.append({"id": inc["id"], "symptoms": inc["kind"].replace("_", " "), "outcome": "CLOSED_UNVERIFIED",
                              "timeline": [{"stage": "DETECT", "note": "problem noticed"},
                                           {"stage": "RECOVER", "note": "applied a fix straight away (no hold, no checks)"},
                                           {"stage": "CLOSED", "note": "marked solved without verifying"}],
                              "money_protected": 0, "escalation": None, "attempts": 1})

    # what really happened at the bank
    per_inv = {}
    for t in sim.bank.txns.values():
        if t["status"] == "SETTLED":
            per_inv[t["invoice"]] = per_inv.get(t["invoice"], 0) + 1
    payments = []
    for key2, t in sorted(sim.bank.txns.items()):
        if t["status"] != "SETTLED":
            continue
        inv = sim.source.get(t["invoice"], {})
        payments.append({"invoice": t["invoice"], "vendor": inv.get("vendor", "?"), "amount": t["amount"],
                         "right_account": t["iban"] == sim.true_iban.get(inv.get("vendor")),
                         "duplicate": per_inv[t["invoice"]] > 1})
    s = sim.summary()
    status = s["by_status"]
    return {"label": label, "story": story, "agent": agent_name, "seed": seed, "incidents": incidents,
            "received": s["invoices_received"], "paid": status.get("PAID", 0),
            "held": status.get("HELD", 0), "unconfirmed": status.get("PAYMENT_UNKNOWN", 0),
            "queued": status.get("APPROVED", 0),
            "lost": s["invoices_received"] - s["in_system"],
            "duplicates": s["duplicate_payments"], "misdirected": s["misdirected_payments"],
            "payments": payments, "bank_submit_calls": sum(sim.bank.submit_calls.values())}
