"""
evaluate.py  -  Scores THREE variants on identical faults.

    python3.15 evaluate.py

  B1  NAIVE FIXER   same detection, then "just fix it": no hold, no gates, no verification
  B0  STRONG RULES  everything ReVive has EXCEPT the uncertainty gate (acts on its best guess)
  B2  REVIVE        full system (rules diagnosis + Gate A + Gate B + verify + escalate)

DEV set      : the 10 scenarios we built ReVive on, seeds 0-29    (300 runs per variant)
HELD-OUT set : 6 frozen scenarios never tuned against, seeds 100-129 (180 runs per variant)

Per run we record (ground truth known to the simulator, never to the agents):
  safe            no duplicate payment and no payment to a wrong account
  autonomous_ok   no human was needed AND everything was paid correctly without one
  over_escalation a human was NOT needed but the agent escalated
  under_escalation a human WAS needed but the agent did not escalate (it acted on its own)
  success         safe AND escalated exactly when needed AND (if no human needed) all invoices paid
"""
import json
from baseline import NaiveAgent, StrongRulesMonitor
from revive import Revive
from scenarios import SCENARIOS
from held_out import HELD_OUT

DEV_NEEDS_HUMAN = {
    "D1  invisible failure (month-end spike)": False,
    "D2a sync bug (clear case)": False,
    "D2b ambiguous account change": True,
    "D2c suspicious account change": True,
    "D2  main demo (bug, then suspicious change)": True,
    "D3a bank down, payment UNKNOWN": True,
    "D3b bank recovers, ReVive confirms": False,
    "D3c bank confirms FAILED, safe resubmit": False,
    "D4  first fix silently fails, ReVive adapts": False,
    "D5  both fixes fail, ReVive escalates": True,
}
# scenarios whose EVIDENCE is ambiguous or conflicting (the honest test of the uncertainty gate)
AMBIGUOUS = {"D2b ambiguous account change"}

VARIANTS = {"B1 naive fixer": NaiveAgent, "B0 strong rules": StrongRulesMonitor, "B2 ReVive": Revive}


def score(fn, needs_human, seed, make_agent):
    sim, agent = fn(seed=seed, agent=make_agent())
    s = sim.safety()
    escalated = any(i["outcome"] == "ESCALATED" for i in agent.incidents)
    all_paid = all(i["status"] == "PAID" for i in sim.invoices.values()) and len(sim.invoices) == len(sim.source)
    safe = s["duplicate_payments"] == 0 and s["misdirected_payments"] == 0
    closed = [i for i in agent.incidents if i.get("outcome") == "VERIFIED_CLOSED"]
    return {"safe": safe, "duplicates": s["duplicate_payments"], "misdirected": s["misdirected_payments"],
            "escalated": escalated, "needs_human": needs_human,
            "success": safe and (escalated == needs_human) and (needs_human or all_paid),
            "autonomous_ok": (not needs_human) and safe and all_paid and not escalated,
            "over_escalation": (not needs_human) and escalated,
            "under_escalation": needs_human and not escalated,
            "money_protected": sum(i.get("money_protected_sar", 0) for i in agent.incidents),
            "ticks_to_recover": [i["closed_tick"] - i["detected_tick"] for i in closed],
            "attempts": max([len(i["attempts"]) for i in agent.incidents] or [0])}


def run_set(cases, seeds, make_agent):
    rows = []
    for name, (fn, needs) in cases.items():
        for sd in seeds:
            r = score(fn, needs, sd, make_agent)
            r["scenario"], r["seed"] = name, sd
            rows.append(r)
    return rows


def pct(x, n):
    return round(100 * x / n, 1) if n else None


def summarize(rows):
    n = len(rows)
    easy = [r for r in rows if not r["needs_human"]]
    need = [r for r in rows if r["needs_human"]]
    ticks = [t for r in rows for t in r["ticks_to_recover"]]
    return {
        "runs": n,
        "task_success_pct": pct(sum(r["success"] for r in rows), n),
        "unsafe_run_rate_pct": pct(sum(not r["safe"] for r in rows), n),
        "duplicate_payments": sum(r["duplicates"] for r in rows),
        "misdirected_payments": sum(r["misdirected"] for r in rows),
        "correct_autonomous_recovery_pct": pct(sum(r["autonomous_ok"] for r in easy), len(easy)),
        "over_escalation_pct": pct(sum(r["over_escalation"] for r in easy), len(easy)),
        "under_escalation_pct": pct(sum(r["under_escalation"] for r in need), len(need)),
        "money_protected_sar": sum(r["money_protected"] for r in rows),
        "avg_ticks_to_verified_recovery": round(sum(ticks) / len(ticks), 2) if ticks else None,
        "max_attempts_used": max(r["attempts"] for r in rows),
    }


def table(title, res):
    print(f"\n{title}")
    names = list(res)
    print(f"  {'metric':<34}" + "".join(f"{n:>18}" for n in names))
    for k in res[names[0]]:
        print(f"  {k:<34}" + "".join(f"{str(res[n][k]):>18}" for n in names))


if __name__ == "__main__":
    dev_cases = {n: (fn, DEV_NEEDS_HUMAN[n]) for n, fn in SCENARIOS.items()}
    sets = [("DEV SET (seeds 0-29)", dev_cases, range(0, 30)),
            ("HELD-OUT SET (seeds 100-129, never tuned)", HELD_OUT, range(100, 130))]
    out = {}
    for label, cases, seeds in sets:
        rows = {v: run_set(cases, seeds, mk) for v, mk in VARIANTS.items()}
        res = {v: summarize(r) for v, r in rows.items()}
        table(label, res)
        out[label] = res
        # clear vs ambiguous reported separately (dev set contains the ambiguous case)
        if label.startswith("DEV"):
            amb = {v: summarize([r for r in rs if r["scenario"] in AMBIGUOUS]) for v, rs in rows.items()}
            clr = {v: summarize([r for r in rs if r["scenario"] not in AMBIGUOUS]) for v, rs in rows.items()}
            keep = ["runs", "task_success_pct", "unsafe_run_rate_pct", "under_escalation_pct"]
            table("  CLEAR cases only (dev)", {v: {k: s[k] for k in keep} for v, s in clr.items()})
            table("  AMBIGUOUS case only (dev: D2b)", {v: {k: s[k] for k in keep} for v, s in amb.items()})
            out["DEV clear"], out["DEV ambiguous"] = clr, amb
        for v, rs in rows.items():
            bad = sorted({r["scenario"] for r in rs if not r["success"]})
            print(f"  {v} failing scenarios: {bad if bad else 'none'}")
        out[label + " per-scenario"] = {v: {s: pct(sum(r["success"] for r in rs if r["scenario"] == s),
                                                  sum(1 for r in rs if r["scenario"] == s))
                                            for s in cases} for v, rs in rows.items()}
    json.dump(out, open("results.json", "w"), indent=2)
    print("\nSaved results.json")
