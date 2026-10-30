"""
baseline.py  -  The "naive fixer" ReVive is compared against.
It uses the SAME detection as ReVive, so the comparison is fair. What it lacks:
no hold, no gates, no dry run, no verification, no escalation. It just fixes and moves on.
"""
from detect import detect
from revive import act_replay, act_restore_iban
from sim import BankDown, BankTimeout


class NaiveAgent:
    def __init__(self):
        self.incidents = []
        self._seen = set()

    def run(self, sim):
        for f in detect(sim):
            k, ev = f["kind"], f["evidence"]
            if k == "conservation_gap":
                act_replay(sim, f)
            elif k == "payee_iban_mismatch":
                if all(v["truncated_pattern"] for v in ev["vendors"]):
                    act_restore_iban(sim, f)                 # one attempt, never checked
                else:                                        # "just update the bank details"
                    for v in ev["vendors"]:
                        sim.vendors[v["vendor"]]["verified_iban"] = sim.vendors[v["vendor"]]["iban"]
            elif k == "unknown_payment":
                inv = sim.invoices[ev["invoice"]]            # "just retry" with a new key
                try:
                    if sim.bank.submit(ev["txn_key"] + "-R", inv["payee_iban"], inv["amount"], inv["id"]) == "SETTLED":
                        sim.mark_paid(inv)
                except (BankDown, BankTimeout):
                    pass
            if f["key"] not in self._seen:
                self._seen.add(f["key"])
                self.incidents.append({"id": f"NAIVE-{len(self._seen):03d}", "kind": k,
                                       "outcome": "CLOSED_UNVERIFIED", "attempts": [], "escalation": None})


# ---------------------------------------------------------------------------
# B0 "Strong rules": a well-engineered deterministic monitor with the SAME evidence.
# It has everything ReVive has (containment hold, risk-tier policy, dry run, verification,
# 2-attempt limit, escalation report) EXCEPT the uncertainty gate (Gate A): when the evidence
# is ambiguous it simply acts on the highest-scoring cause instead of escalating.
# This isolates exactly what Gate A adds.
# ---------------------------------------------------------------------------
from diagnose import diagnose as _rules_diagnose
from revive import Revive


def _argmax_diagnoser(finding):
    dx = _rules_diagnose(finding)
    top = max(dx["scores"], key=dx["scores"].get)
    return dict(dx, prediction_set=[top], method="rules (best guess, no uncertainty gate)")


class StrongRulesMonitor(Revive):
    def __init__(self, save_dir=None):
        super().__init__(diagnoser=_argmax_diagnoser, save_dir=save_dir)
