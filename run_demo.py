"""
run_demo.py  -  Run every demo scenario and print a plain-English report.

    python3 run_demo.py
"""
from scenarios import SCENARIOS


def show(name, sim, rv):
    print("=" * 78)
    print(name)
    print("-" * 78)
    for inc in rv.incidents:
        print(f"  {inc['id']}  {inc['symptoms']}")
        for step in inc["timeline"]:
            print(f"      [{step['stage']:<9}] {step['note']}")
        print(f"      >>> OUTCOME: {inc['outcome']}   money protected: {inc['money_protected_sar']:,} SAR")
        if inc["escalation"]:
            print(f"      >>> HUMAN NEEDED: {inc['escalation']['reason']}")
    s = sim.summary()
    print(f"  SAFETY: duplicate payments = {s['duplicate_payments']}, "
          f"misdirected payments = {s['misdirected_payments']}   |   "
          f"invoices received {s['invoices_received']}, by status {s['by_status']}")


if __name__ == "__main__":
    for name, fn in SCENARIOS.items():
        sim, rv = fn(seed=1, save_dir="incidents")
        show(name, sim, rv)
