"""
calibrate.py  -  Is the diagnostic gate (Gate A) honest about its own uncertainty?

    python3.15 calibrate.py

We generate synthetic payee-mismatch incidents whose TRUE cause (sync bug or fraud) is hidden from the
diagnoser. Evidence overlaps on purpose (some frauds look like truncated bugs; some bugs hit big, recently
changed vendors). The diagnoser returns a SET of possible causes. We measure:
   coverage      how often the TRUE cause is inside the set   (target >= 90%)
   avg set size  1.0 = always decisive
   escalation    how often the set has more than one cause   (a human is asked)
Threshold q is CALIBRATED on 100 dev incidents (seeds 0-99), then CHECKED on 200 held-out ones (seeds 1000-1199).
Coverage is a marginal target to evaluate, not a guarantee.
"""
import json
import random

import diagnose as D
from detect import detect
from sim import Sim

TARGET = 0.90


def make_incident(seed):
    r = random.Random(seed)
    sim = Sim(seed=seed)
    truth = r.choice(["SYNC_IBAN_CORRUPTION", "POSSIBLE_FRAUD"])
    vid = f"V{r.randrange(1, 7)}"
    if truth == "SYNC_IBAN_CORRUPTION":
        multi = r.random() < 0.55
        vids = [vid] + ([f"V{(int(vid[1]) % 6) + 1}", f"V{((int(vid[1]) + 1) % 6) + 1}"] if multi else [])
        sim.corrupt_vendor_ibans(vids, batch="SYNC-0042" if multi else None)
        if not multi and r.random() < 0.30:
            sim.vendors[vid]["changed_recently"] = True        # an old vendor whose record was just edited
        big = r.random() < 0.25
        for v in vids:
            sim.intake(sim.make_invoices(1, vendor=v, amount=(r.randrange(120, 400) if big else r.randrange(5, 60)) * 1000))
    else:
        lookalike = r.random() < 0.30                          # attacker uses a near-copy of the real account
        if lookalike:
            sim.corrupt_vendor_ibans([vid], batch=None)
            sim.vendors[vid]["changed_recently"] = True
        else:
            sim.change_vendor_iban(vid)
        big = r.random() < 0.80
        sim.intake(sim.make_invoices(1, vendor=vid, amount=(r.randrange(120, 450) if big else r.randrange(5, 60)) * 1000))
    sim.matching(); sim.approval()
    f = [x for x in detect(sim) if x["kind"] == "payee_iban_mismatch"][0]
    return truth, f


def evaluate(seeds, q):
    cov = size = esc = 0
    for s in seeds:
        truth, f = make_incident(s)
        dx = D.diagnose(f)
        pset = [c for c, sc in dx["scores"].items() if sc >= q]
        if not pset:                      # nothing above the bar -> be maximally cautious
            pset = list(dx["scores"])
        cov += truth in pset
        size += len(pset)
        esc += len(pset) > 1
    n = len(seeds)
    return {"coverage": round(cov / n, 3), "avg_set_size": round(size / n, 2), "escalation_rate": round(esc / n, 3)}


if __name__ == "__main__":
    dev, held = range(0, 100), range(1000, 1200)
    curve = {}
    for q in [0.05, 0.1, 0.15, 0.2, 0.3, 0.4, 0.5, 0.6, 0.8]:
        curve[q] = {"dev": evaluate(dev, q), "held": evaluate(held, q)}
    # calibrated q = the LARGEST threshold (smallest sets) that still reaches the target on DEV
    ok = [q for q in curve if curve[q]["dev"]["coverage"] >= TARGET]
    q_star = max(ok) if ok else min(curve)
    print(f"{'q':>6} | {'DEV cov':>8} {'size':>5} {'esc':>6} | {'HELD cov':>9} {'size':>5} {'esc':>6}")
    for q, v in curve.items():
        d, h = v["dev"], v["held"]
        mark = "  <- calibrated on dev" if q == q_star else ("  <- current setting" if q == D.INCLUDE_THRESHOLD else "")
        print(f"{q:>6} | {d['coverage']:>8} {d['avg_set_size']:>5} {d['escalation_rate']:>6} | "
              f"{h['coverage']:>9} {h['avg_set_size']:>5} {h['escalation_rate']:>6}{mark}")
    json.dump({"target": TARGET, "q_calibrated": q_star, "q_current": D.INCLUDE_THRESHOLD,
               "curve": {str(q): v for q, v in curve.items()}}, open("calibration.json", "w"), indent=2)
    print(f"\nCalibrated threshold on dev: q = {q_star}.  Saved calibration.json")
