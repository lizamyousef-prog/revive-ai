"""
held_out.py  -  FROZEN held-out scenarios. Written once, then never tuned against.
They differ from the dev scenarios: random sizes/amounts, and TWO faults at once.
Seeds 100-109 are used for these.
"""
from sim import Sim
from revive import Revive


def _new(seed, save_dir, agent):
    return Sim(seed=seed), (agent if agent is not None else Revive(save_dir=save_dir))


def h1_two_faults_at_once(seed=100, save_dir=None, agent=None):
    """Silent intake drop AND a sync bug hit at the same time."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.add("intake_drop")
    sim.intake_limit = sim.rng.randrange(2, 7)
    sim.corrupt_vendor_ibans(["V1", "V2", "V3"])
    sim.intake(sim.make_invoices(sim.rng.randrange(9, 15)))
    for _ in range(5):
        sim.tick(rv)
    return sim, rv


def h2_big_spike(seed=100, save_dir=None, agent=None):
    """A much bigger month-end spike with a random drop limit."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.add("intake_drop")
    sim.intake_limit = sim.rng.randrange(3, 10)
    sim.intake(sim.make_invoices(sim.rng.randrange(15, 26)))
    for _ in range(5):
        sim.tick(rv)
    return sim, rv


def h3_timeout_then_sync_bug(seed=100, save_dir=None, agent=None):
    """The bank times out (and really settles) while two vendors have corrupted accounts."""
    sim, rv = _new(seed, save_dir, agent)
    sim.bank.timeout_next = True
    sim.corrupt_vendor_ibans(["V4", "V5"])
    sim.intake(sim.make_invoices(6))
    for _ in range(5):
        sim.tick(rv)
    return sim, rv


def h4_small_invoice_new_account(seed=100, save_dir=None, agent=None):
    """A vendor's account is replaced by a different one right before a payment."""
    sim, rv = _new(seed, save_dir, agent)
    vendor = f"V{sim.rng.randrange(1, 7)}"
    sim.change_vendor_iban(vendor)
    sim.intake(sim.make_invoices(2, vendor=vendor, amount=sim.rng.randrange(150, 400) * 1000))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def h5_timeout_bank_stays_down(seed=100, save_dir=None, agent=None):
    """A timeout with the bank staying offline, on a random invoice batch size."""
    sim, rv = _new(seed, save_dir, agent)
    sim.bank.timeout_next = True
    sim.bank.go_down_after_timeout = True
    sim.intake(sim.make_invoices(sim.rng.randrange(2, 8)))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def h6_repeat_sync_bug_fix_fails(seed=100, save_dir=None, agent=None):
    """A sync bug hits 2 vendors and BOTH repair actions silently do nothing."""
    sim, rv = _new(seed, save_dir, agent)
    sim.faults.update({"noop:rollback_sync_batch", "noop:restore_verified_iban_per_vendor"})
    sim.corrupt_vendor_ibans(["V2", "V6"])
    sim.intake(sim.make_invoices(sim.rng.randrange(4, 9)))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


def h7_ambiguous_account(seed=100, save_dir=None, agent=None):
    """Added in held-out v2 (the doctor's plan asks for ambiguous cases): ONE vendor, account looks
    truncated BUT it changed recently and the invoice is large. Random vendor and amount."""
    sim, rv = _new(seed, save_dir, agent)
    vendor = f"V{sim.rng.randrange(1, 7)}"
    sim.corrupt_vendor_ibans([vendor], batch=None)
    sim.vendors[vendor]["changed_recently"] = True
    sim.intake(sim.make_invoices(sim.rng.randrange(1, 3), vendor=vendor, amount=sim.rng.randrange(120, 450) * 1000))
    for _ in range(4):
        sim.tick(rv)
    return sim, rv


# name -> (function, should the agent escalate to a human?)
HELD_OUT = {
    "H1 two faults at once": (h1_two_faults_at_once, False),
    "H2 big month-end spike": (h2_big_spike, False),
    "H3 timeout + sync bug": (h3_timeout_then_sync_bug, False),
    "H4 new account, big invoice": (h4_small_invoice_new_account, True),
    "H5 timeout, bank stays down": (h5_timeout_bank_stays_down, True),
    "H6 both repairs fail": (h6_repeat_sync_bug_fix_fails, True),
    "H7 ambiguous account (added v2)": (h7_ambiguous_account, True),
}
