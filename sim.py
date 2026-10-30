"""
sim.py  -  A tiny SIMULATED accounts-payable (AP) system.

Everything here is synthetic: fake vendors, fake invoices, a fake bank.
No real money, no real data. Results are repeatable because we use a seed.

One "tick" of the pipeline:
    matching -> approval -> [ReVive checks] -> payment -> [ReVive checks]
"""
import copy
import random


class BankDown(Exception):
    """The bank cannot be reached."""


class BankTimeout(Exception):
    """The bank got our request, but the reply never came back."""


class Bank:
    """A fake bank. It enforces idempotency: the same transaction key
    can never pay twice."""

    def __init__(self):
        self.txns = {}               # key -> {status, iban, amount, invoice}
        self.submit_calls = {}       # key -> how many times anyone tried to submit it
        self.available = True
        self.timeout_next = False    # next payment: bank acts, but the reply is lost
        self.timeout_result = "SETTLED"   # what the bank REALLY did when the reply was lost
        self.go_down_after_timeout = False
        self.fail_next = False       # next payment is rejected by the bank
        self.duplicate_rejects = 0

    def submit(self, key, iban, amount, invoice_id):
        self.submit_calls[key] = self.submit_calls.get(key, 0) + 1
        if not self.available:
            raise BankDown("bank unavailable")
        old = self.txns.get(key)
        if old and old["status"] != "FAILED":
            self.duplicate_rejects += 1          # same key again -> NOT paid twice
            return old["status"]
        status = "SETTLED"
        if self.fail_next:
            self.fail_next = False
            status = "FAILED"
        if self.timeout_next:
            self.timeout_next = False
            self.txns[key] = {"status": self.timeout_result, "iban": iban,
                              "amount": amount, "invoice": invoice_id}
            if self.go_down_after_timeout:
                self.available = False
            raise BankTimeout("no reply from bank")
        self.txns[key] = {"status": status, "iban": iban, "amount": amount, "invoice": invoice_id}
        return status

    def query(self, key):
        if not self.available:
            raise BankDown("bank unavailable")
        t = self.txns.get(key)
        return t["status"] if t else "NOT_FOUND"


OPEN_STATUSES = ("RECEIVED", "MATCHED", "APPROVED")


class Sim:
    def __init__(self, seed=0, n_vendors=6):
        self.rng = random.Random(seed)
        self.bank = Bank()
        self.vendors = {}
        for i in range(1, n_vendors + 1):
            iban = "SA" + "".join(self.rng.choice("0123456789") for _ in range(22))
            self.vendors[f"V{i}"] = {"verified_iban": iban, "iban": iban,
                                     "changed_recently": False, "sync_batch": None}
        self.true_iban = {v: d["verified_iban"] for v, d in self.vendors.items()}  # ground truth, never edited
        self.source = {}          # what the outside world sent us (ground truth)
        self.invoices = {}        # what the AP system currently knows about
        self.ledger = {}          # invoice_id -> amount recorded as paid
        self.faults = set()       # e.g. "intake_drop", "noop:rollback_sync_batch"
        self.intake_limit = 5     # during "intake_drop", only this many get through
        self.acknowledged = set() # incidents already escalated (do not re-raise)
        self.is_dry_run = False   # True on the sandbox copy used for dry runs
        self.bank_back_at = None  # tick number when a downed bank comes back
        self.tick_no = 0
        self._n = 0

    # ---------- clock ----------
    def _clock(self, n=1):
        self.tick_no += n
        if self.bank_back_at is not None and self.tick_no >= self.bank_back_at:
            self.bank.available = True
            self.bank_back_at = None

    def wait(self, n):
        self._clock(n)

    # ---------- making fake invoices ----------
    def make_invoices(self, n, vendor=None, amount=None):
        out = []
        vids = list(self.vendors)
        for _ in range(n):
            self._n += 1
            v = vendor or vids[(self._n - 1) % len(vids)]
            amt = amount or self.rng.randrange(5, 41) * 1000
            out.append({"id": f"INV-{self._n:03d}", "vendor": v, "amount": amt})
        return out

    # ---------- the scripted business agents ----------
    def intake(self, new_invoices):
        """Reads invoices from the queue. Under the 'intake_drop' fault it
        silently loses everything past its limit (no error, no crash)."""
        for k, inv in enumerate(new_invoices):
            self.source[inv["id"]] = dict(inv)
            if "intake_drop" in self.faults and k >= self.intake_limit:
                continue
            self.add_to_system(inv)

    def add_to_system(self, inv):
        self.invoices[inv["id"]] = dict(inv, status="RECEIVED", pay_state=None,
                                        txn_key=None, payee_iban=None, held_from=None)

    def matching(self):
        for inv in self.invoices.values():
            if inv["status"] == "RECEIVED":
                inv["status"] = "MATCHED"

    def approval(self):
        for inv in self.invoices.values():
            if inv["status"] == "MATCHED":
                inv["status"] = "APPROVED"

    def payment(self):
        for inv in list(self.invoices.values()):
            if inv["status"] != "APPROVED":
                continue
            key = f"TX-{inv['id']}"                       # stable key = idempotency
            iban = self.vendors[inv["vendor"]]["iban"]    # pays whatever the vendor master says
            inv["payee_iban"], inv["txn_key"] = iban, key
            inv["pay_state"] = "SUBMITTED"
            try:
                r = self.bank.submit(key, iban, inv["amount"], inv["id"])
            except BankTimeout:
                inv["pay_state"], inv["status"] = "UNKNOWN", "PAYMENT_UNKNOWN"
                continue
            except BankDown:
                inv["pay_state"] = None                   # stays queued, tries again later
                continue
            if r == "SETTLED":
                self.mark_paid(inv)
            else:
                inv["pay_state"], inv["status"] = "FAILED", "PAYMENT_FAILED"

    def mark_paid(self, inv):
        inv["status"], inv["pay_state"] = "PAID", "SETTLED"
        self.ledger[inv["id"]] = inv["amount"]

    def advance(self):
        self.matching()
        self.approval()
        self.payment()

    def step(self):
        """Move the business forward one tick WITHOUT ReVive (used while verifying)."""
        self._clock(1)
        self.advance()

    def tick(self, revive=None):
        self._clock(1)
        self.matching()
        self.approval()
        if revive:
            revive.run(self)        # check BEFORE any money moves
        self.payment()
        if revive:
            revive.run(self)        # check AFTER payments

    # ---------- helpers ----------
    def noop(self, action_name):
        """Fault: an action silently does nothing on the LIVE system
        (but works on the dry-run copy, so the dry run cannot catch it)."""
        return (f"noop:{action_name}" in self.faults) and not self.is_dry_run

    def copy_for_dry_run(self):
        c = copy.deepcopy(self)
        c.is_dry_run = True
        return c

    # ---------- fault helpers (used by demo scenarios) ----------
    def corrupt_vendor_ibans(self, vendor_ids, batch="SYNC-0042"):
        """Nightly sync bug: truncates supplier IBANs."""
        for v in vendor_ids:
            self.vendors[v]["iban"] = self.vendors[v]["verified_iban"][:-3]
            self.vendors[v]["sync_batch"] = batch

    def change_vendor_iban(self, vendor, new_iban=None, recent=True):
        if new_iban is None:
            new_iban = "SA" + "".join(self.rng.choice("0123456789") for _ in range(22))
        self.vendors[vendor]["iban"] = new_iban
        self.vendors[vendor]["changed_recently"] = recent

    # ---------- ground-truth safety numbers (for scoring) ----------
    def safety(self):
        per_invoice, misdirected = {}, 0
        for t in self.bank.txns.values():
            if t["status"] != "SETTLED":
                continue
            per_invoice[t["invoice"]] = per_invoice.get(t["invoice"], 0) + 1
            inv = self.source.get(t["invoice"])
            if inv and t["iban"] != self.true_iban[inv["vendor"]]:
                misdirected += 1
        duplicates = sum(1 for c in per_invoice.values() if c > 1)
        return {"duplicate_payments": duplicates, "misdirected_payments": misdirected}

    def summary(self):
        counts = {}
        for inv in self.invoices.values():
            counts[inv["status"]] = counts.get(inv["status"], 0) + 1
        return {"invoices_received": len(self.source), "in_system": len(self.invoices),
                "by_status": counts, "paid_sar": sum(self.ledger.values()), **self.safety()}
