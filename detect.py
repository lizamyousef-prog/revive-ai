"""
detect.py  -  STAGE 1: DETECT.
Plain rule-based checks on the BUSINESS state (no AI here, on purpose).
We check "is the business still correct?", not just "are servers running?".
"""
from sim import OPEN_STATUSES

LARGE_SAR = 100_000


def detect(sim):
    findings = []

    # 1) Conservation: every invoice we RECEIVED must be accounted for in the system.
    missing = sorted(i for i in sim.source if i not in sim.invoices)
    if missing:
        key = "gap:" + ",".join(missing)
        if key not in sim.acknowledged:
            findings.append({
                "kind": "conservation_gap", "key": key,
                "summary": f"{len(missing)} invoice(s) received but missing from the system",
                "evidence": {"received": len(sim.source), "in_system": len(sim.invoices),
                             "missing": missing,
                             "missing_value": sum(sim.source[i]["amount"] for i in missing)},
            })

    # 2) Payee check: the bank account we would pay must equal the last VERIFIED one.
    bad = {}
    for inv in sim.invoices.values():
        if inv["status"] in OPEN_STATUSES:
            v = sim.vendors[inv["vendor"]]
            if v["iban"] != v["verified_iban"]:
                bad.setdefault(inv["vendor"], []).append(inv)
    groups = {}
    for vid in bad:
        batch = sim.vendors[vid]["sync_batch"]
        groups.setdefault(("batch", batch) if batch else ("single", vid), []).append(vid)
    for (gkind, _gid), vids in groups.items():
        single = len(vids) == 1
        details = []
        for vid in vids:
            v, invs = sim.vendors[vid], bad[vid]
            details.append({
                "vendor": vid,
                "truncated_pattern": v["iban"] != v["verified_iban"] and v["verified_iban"].startswith(v["iban"]),
                "changed_recently": v["changed_recently"],
                "sync_batch": v["sync_batch"],
                "open_invoices": [i["id"] for i in invs],
                "open_amount": sum(i["amount"] for i in invs),
                "max_invoice": max(i["amount"] for i in invs),
            })
        key = "iban:" + ",".join(sorted(vids))
        if key in sim.acknowledged:
            continue
        findings.append({
            "kind": "payee_iban_mismatch", "key": key,
            "summary": f"{len(vids)} vendor(s) have a bank account that differs from the verified one",
            "evidence": {"vendors": details, "single_vendor": single,
                         "same_batch": (not single) and gkind == "batch",
                         "open_amount": sum(d["open_amount"] for d in details)},
        })

    # 3) Reconciliation: a payment whose result we do not know (UNKNOWN).
    for inv in sim.invoices.values():
        if inv["pay_state"] == "UNKNOWN":
            key = "unknown:" + inv["id"]
            if key in sim.acknowledged:
                continue
            findings.append({
                "kind": "unknown_payment", "key": key,
                "summary": f"payment for {inv['id']} timed out; result unknown",
                "evidence": {"invoice": inv["id"], "amount": inv["amount"],
                             "txn_key": inv["txn_key"],
                             "queued_waiting": sum(1 for i in sim.invoices.values()
                                                   if i["status"] == "APPROVED")},
            })
    return findings
