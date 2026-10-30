"""
scenarios.py  -  The demo failures. Each function builds a fresh simulated
store, injects a fault, runs the business with ReVive watching, and returns
(sim, revive) so the results can be inspected.
"""
from sim import Sim
from revive import Revive


def _new(seed, save_dir=None, agent=None):
    return Sim(seed=seed), (agent if agent is not None else Revive(save_dir=save_dir))


# ---------------- D1: the invisible failure ----------------
def d1_invisible_failure(seed=0, save_dir=None, agent=None):
    """Month-end spike: the intake agent silently drops invoices. No crash, no error."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.add("intake_drop")
    sim.intake(sim.make_invoices(8))            # 8 arrive, only 5 get in
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


# ---------------- D2: same symptom, different causes ----------------
def d2_sync_bug(seed=0, save_dir=None, agent=None):
    """A nightly sync bug truncates the bank accounts of 3 vendors (same batch)."""
    sim, rv = _new(seed, save_dir, agent)
    sim.corrupt_vendor_ibans(["V1", "V2", "V3"])
    sim.intake(sim.make_invoices(6))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def d2_ambiguous(seed=0, save_dir=None, agent=None):
    """ONE vendor, account looks truncated BUT it changed recently and the invoice is large."""
    sim, rv = _new(seed, save_dir, agent)
    sim.corrupt_vendor_ibans(["V1"], batch=None)
    sim.vendors["V1"]["changed_recently"] = True
    sim.intake(sim.make_invoices(1, vendor="V1", amount=250_000))
    for _ in range(3):
        sim.tick(rv)
    return sim, rv


def d2_fraud(seed=0, save_dir=None, agent=None):
    """ONE vendor suddenly has a completely different bank account before a large payment."""
    sim, rv = _new(seed, save_dir, agent)
    sim.change_vendor_iban("V2")
    sim.intake(sim.make_invoices(1, vendor="V2", amount=300_000))
    for _ in range(3):
        sim.tick(rv)
    return sim, rv


def d2_main(seed=0, save_dir=None, agent=None):
    """The main demo: a sync bug is repaired, then a suspicious change is contained and escalated."""
    sim, rv = _new(seed, save_dir, agent)
    sim.corrupt_vendor_ibans(["V1", "V2", "V3"])
    sim.intake(sim.make_invoices(6))
    for _ in range(3):
        sim.tick(rv)
    sim.change_vendor_iban("V5")
    sim.intake(sim.make_invoices(1, vendor="V5", amount=300_000))
    for _ in range(3):
        sim.tick(rv)
    return sim, rv


# ---------------- D3: the agent admits failure ----------------
def d3_bank_down(seed=0, save_dir=None, agent=None):
    """Bank times out AND goes offline. Payment state UNKNOWN. ReVive must not resend."""
    sim, rv = _new(seed, save_dir, agent)
    sim.bank.timeout_next = True
    sim.bank.go_down_after_timeout = True
    sim.intake(sim.make_invoices(3))
    for _ in range(3):
        sim.tick(rv)
    return sim, rv


def d3_bank_recovers(seed=0, save_dir=None, agent=None):
    """Bank times out, goes down briefly, then comes back. ReVive waits, queries, confirms."""
    sim, rv = _new(seed, save_dir, agent)
    sim.bank.timeout_next = True
    sim.bank.go_down_after_timeout = True
    sim.bank_back_at = 4
    sim.intake(sim.make_invoices(3))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def d3_confirmed_failed(seed=0, save_dir=None, agent=None):
    """Bank times out and the bank confirms the payment FAILED: safe to resubmit with the SAME key."""
    sim, rv = _new(seed, save_dir, agent)
    sim.bank.timeout_next = True
    sim.bank.timeout_result = "FAILED"
    sim.intake(sim.make_invoices(3))
    for _ in range(3):
        sim.tick(rv)
    return sim, rv


# ---------------- Failed-recovery cases ----------------
def d4_fix_silently_fails_once(seed=0, save_dir=None, agent=None):
    """The first repair claims success but does nothing. Verification catches it; ReVive adapts."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.add("noop:rollback_sync_batch")
    sim.corrupt_vendor_ibans(["V1", "V2", "V3"])
    sim.intake(sim.make_invoices(6))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def d5_fix_fails_twice(seed=0, save_dir=None, agent=None):
    """Both repairs silently fail. ReVive stops after 2 attempts and escalates."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.update({"noop:rollback_sync_batch", "noop:restore_verified_iban_per_vendor"})
    sim.corrupt_vendor_ibans(["V1", "V2", "V3"])
    sim.intake(sim.make_invoices(6))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


SCENARIOS = {
    "D1  invisible failure (month-end spike)": d1_invisible_failure,
    "D2a sync bug (clear case)": d2_sync_bug,
    "D2b ambiguous account change": d2_ambiguous,
    "D2c suspicious account change": d2_fraud,
    "D2  main demo (bug, then suspicious change)": d2_main,
    "D3a bank down, payment UNKNOWN": d3_bank_down,
    "D3b bank recovers, ReVive confirms": d3_bank_recovers,
    "D3c bank confirms FAILED, safe resubmit": d3_confirmed_failed,
    "D4  first fix silently fails, ReVive adapts": d4_fix_silently_fails_once,
    "D5  both fixes fail, ReVive escalates": d5_fix_fails_twice,
}
