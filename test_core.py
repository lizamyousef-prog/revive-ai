"""
test_core.py  -  Automatic checks. Run with:   python3 test_core.py

For every scenario and every seed we assert the SAFETY rules (no duplicate and
no misdirected payments) and the expected OUTCOME. If anything is wrong the
program stops and says exactly what.
"""
from scenarios import (d1_invisible_failure, d2_sync_bug, d2_ambiguous, d2_fraud, d2_main,
                       d3_bank_down, d3_bank_recovers, d3_confirmed_failed,
                       d4_fix_silently_fails_once, d5_fix_fails_twice, SCENARIOS)

SEEDS = range(30)
checks = 0


def check(cond, msg):
    global checks
    checks += 1
    assert cond, "FAILED: " + msg


def outcomes(rv):
    return [i["outcome"] for i in rv.incidents]


for seed in SEEDS:
    tag = f"(seed {seed})"

    # --- universal safety rule across EVERY scenario ---
    for name, fn in SCENARIOS.items():
        sim, rv = fn(seed=seed)
        s = sim.safety()
        check(s["duplicate_payments"] == 0, f"{name} duplicate payment {tag}")
        check(s["misdirected_payments"] == 0, f"{name} misdirected payment {tag}")
        check(len(rv.incidents) >= 1, f"{name} raised no incident {tag}")
        for inc in rv.incidents:
            check(len(inc["attempts"]) <= 2, f"{name} used more than 2 attempts {tag}")

    # --- D1: gap found, replayed, everything paid exactly once ---
    sim, rv = d1_invisible_failure(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED"], f"D1 outcome {tag}")
    check(all(i["status"] == "PAID" for i in sim.invoices.values()), f"D1 all paid {tag}")
    check(len(sim.invoices) == len(sim.source) == 8, f"D1 conservation {tag}")

    # --- D2a: clear sync bug is repaired ---
    sim, rv = d2_sync_bug(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED"], f"D2a outcome {tag}")
    check(all(i["status"] == "PAID" for i in sim.invoices.values()), f"D2a all paid {tag}")

    # --- D2b: ambiguous -> gate A fails -> escalate and hold ---
    sim, rv = d2_ambiguous(seed)
    check(outcomes(rv) == ["ESCALATED"], f"D2b outcome {tag}")
    check(rv.incidents[0]["gate_a"]["pass"] is False, f"D2b gate A should fail {tag}")
    check(all(i["status"] == "HELD" for i in sim.invoices.values()), f"D2b held {tag}")

    # --- D2c: single suspicious cause, but action is HIGH risk -> gate B blocks ---
    sim, rv = d2_fraud(seed)
    check(outcomes(rv) == ["ESCALATED"], f"D2c outcome {tag}")
    check(rv.incidents[0]["gate_a"]["pass"] is True, f"D2c gate A passes {tag}")
    check(rv.incidents[0]["gate_b"]["pass"] is False, f"D2c gate B must block {tag}")
    check(all(i["status"] == "HELD" for i in sim.invoices.values()), f"D2c held {tag}")

    # --- D2 main: repair one, escalate the other ---
    sim, rv = d2_main(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED", "ESCALATED"], f"D2 main outcomes {tag}")

    # --- D3a: bank down -> query fails twice -> escalate, NEVER resend ---
    sim, rv = d3_bank_down(seed)
    check(outcomes(rv) == ["ESCALATED"], f"D3a outcome {tag}")
    check(sim.bank.submit_calls["TX-INV-001"] == 1, f"D3a payment was resent {tag}")

    # --- D3b: bank recovers -> confirmed, still no resend ---
    sim, rv = d3_bank_recovers(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED"], f"D3b outcome {tag}")
    check(len(rv.incidents[0]["attempts"]) == 2, f"D3b needed the adapted attempt {tag}")
    check(sim.bank.submit_calls["TX-INV-001"] == 1, f"D3b payment was resent {tag}")

    # --- D3c: bank confirms FAILED -> resubmit once with the same key ---
    sim, rv = d3_confirmed_failed(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED"], f"D3c outcome {tag}")
    check(sim.bank.submit_calls["TX-INV-001"] == 2, f"D3c should resubmit exactly once {tag}")

    # --- D4: first fix is a silent no-op -> verification catches it -> adapt ---
    sim, rv = d4_fix_silently_fails_once(seed)
    check(outcomes(rv) == ["VERIFIED_CLOSED"], f"D4 outcome {tag}")
    a = rv.incidents[0]["attempts"]
    check(len(a) == 2 and a[0]["verified"] is False and a[1]["verified"] is True, f"D4 attempts {tag}")

    # --- D5: both fixes fail -> stop at 2 attempts and escalate ---
    sim, rv = d5_fix_fails_twice(seed)
    check(outcomes(rv) == ["ESCALATED"], f"D5 outcome {tag}")
    check(len(rv.incidents[0]["attempts"]) == 2, f"D5 exactly 2 attempts {tag}")

# --- regression for the bug the held-out set found: the whole sync batch must be repaired ---
from held_out import h1_two_faults_at_once
for seed in SEEDS:
    sim, rv = h1_two_faults_at_once(seed=seed)
    check(all(d["iban"] == d["verified_iban"] for d in sim.vendors.values()), f"H1 whole batch repaired (seed {seed})")
    check(all(i["status"] == "PAID" for i in sim.invoices.values()) and len(sim.invoices) == len(sim.source),
          f"H1 everything paid (seed {seed})")

print(f"ALL GOOD: {checks} checks passed across {len(list(SEEDS))} seeds and {len(SCENARIOS)} scenarios.")
