"""
diagnose.py  -  STAGE 2: DIAGNOSE.
Turns evidence into a SET of possible causes from a small fixed list.
If more than one cause is plausible, the set has more than one item,
and ReVive will NOT guess (that is "gate A" in revive.py).

This version is the rules-based diagnoser (hand-set scores). The AI (LLM)
diagnoser will plug into the same function and return the same shape.
"""
from detect import LARGE_SAR

TAXONOMY = ["INTAKE_DROP", "SYNC_IBAN_CORRUPTION", "POSSIBLE_FRAUD",
            "BANK_TIMEOUT_UNKNOWN", "UNKNOWN_OTHER"]
INCLUDE_THRESHOLD = 0.30   # a cause stays in the set if its score is at least this


def diagnose(finding):
    k, ev = finding["kind"], finding["evidence"]
    if k == "conservation_gap":
        scores = {"INTAKE_DROP": 1.0}
        cited = ["received count vs in-system count"]
    elif k == "unknown_payment":
        scores = {"BANK_TIMEOUT_UNKNOWN": 1.0}
        cited = ["payment state UNKNOWN", "bank timeout"]
    elif k == "payee_iban_mismatch":
        vs = ev["vendors"]
        if not ev["single_vendor"]:
            if ev["same_batch"] and all(v["truncated_pattern"] for v in vs):
                scores = {"SYNC_IBAN_CORRUPTION": 0.95, "POSSIBLE_FRAUD": 0.05}
                cited = ["many vendors", "same sync batch", "IBAN is a truncated copy of the verified one"]
            else:
                scores = {"UNKNOWN_OTHER": 1.0}
                cited = ["several vendors but no clear common pattern"]
        else:
            v = vs[0]
            big = v["max_invoice"] >= LARGE_SAR
            if v["truncated_pattern"] and not (v["changed_recently"] and big):
                scores = {"SYNC_IBAN_CORRUPTION": 0.80, "POSSIBLE_FRAUD": 0.20}
                cited = ["IBAN looks truncated", "small invoice"]
            elif v["truncated_pattern"]:
                scores = {"SYNC_IBAN_CORRUPTION": 0.50, "POSSIBLE_FRAUD": 0.50}
                cited = ["IBAN looks truncated BUT", "single vendor", "recent change", "large invoice"]
            else:
                scores = {"POSSIBLE_FRAUD": 0.90, "SYNC_IBAN_CORRUPTION": 0.10}
                cited = ["single vendor", "completely different account", "recent change"]
    else:
        scores = {"UNKNOWN_OTHER": 1.0}
        cited = []
    pred_set = [c for c, s in sorted(scores.items(), key=lambda x: -x[1]) if s >= INCLUDE_THRESHOLD]
    return {"prediction_set": pred_set, "scores": scores, "cited_evidence": cited, "method": "rules"}
