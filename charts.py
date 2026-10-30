"""charts.py - makes the result figures:  python3.15 charts.py   (needs: pip3 install matplotlib)
F4  safety vs autonomy (clear and ambiguous cases separately, dev + held-out pooled)
F6  calibration: does Gate A's prediction set contain the true cause?"""
import json
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from evaluate import run_set, summarize, VARIANTS, DEV_NEEDS_HUMAN, AMBIGUOUS
from scenarios import SCENARIOS
from held_out import HELD_OUT

COL = {"B1 naive fixer": "#eb6834", "B0 strong rules": "#2a78d6", "B2 ReVive": "#1baf7a"}
INK, MUTED = "#0b0b0b", "#52514e"

dev = {n: (fn, DEV_NEEDS_HUMAN[n]) for n, fn in SCENARIOS.items()}
rows = {v: run_set(dev, range(30), mk) + run_set(HELD_OUT, range(100, 130), mk) for v, mk in VARIANTS.items()}
is_amb = lambda r: r["scenario"] in AMBIGUOUS or r["scenario"].startswith("H7")
clear = {v: summarize([r for r in rs if not is_amb(r)]) for v, rs in rows.items()}
amb = {v: summarize([r for r in rs if is_amb(r)]) for v, rs in rows.items()}
json.dump({"clear": clear, "ambiguous": amb}, open("results_split.json", "w"), indent=2)

fig, axes = plt.subplots(1, 2, figsize=(11, 4.6), facecolor="white")
panels = [
    (axes[0], "CLEAR cases", clear, [("Correct autonomous\nrecovery %", "correct_autonomous_recovery_pct", True),
                                      ("Unsafe runs %", "unsafe_run_rate_pct", False)]),
    (axes[1], "AMBIGUOUS cases", amb, [("Escalated to a human\nwhen needed %", "under_escalation_pct", True),
                                       ("Unsafe runs %", "unsafe_run_rate_pct", False)]),
]
for ax, title, data, metrics in panels:
    w = 0.26
    for j, (v, c) in enumerate(COL.items()):
        for i, (lab, key, good) in enumerate(metrics):
            val = data[v][key]
            if key == "under_escalation_pct":
                val = round(100 - val, 1)
            ax.bar(i + (j - 1) * (w + 0.02), val, w, color=c, label=v if i == 0 else None)
            ax.text(i + (j - 1) * (w + 0.02), val + 1.5, f"{val:g}", ha="center", fontsize=9, color=INK)
    ax.set_xticks([0, 1]); ax.set_xticklabels([m[0] for m in metrics], color=INK)
    ax.set_ylim(0, 112); ax.set_title(f"{title}  (n = {data['B2 ReVive']['runs']} runs per variant)", color=INK, fontsize=11, loc="left")
    for s in ("top", "right"): ax.spines[s].set_visible(False)
    ax.tick_params(colors=MUTED); ax.yaxis.grid(True, color="#e6e5e0"); ax.set_axisbelow(True)
axes[0].set_ylabel("% of runs  (higher = better, except unsafe)", color=MUTED)
axes[0].legend(frameon=False, loc="upper center", ncol=3, bbox_to_anchor=(1.12, -0.10))
fig.suptitle("F4  Safety vs autonomy: only ReVive is safe AND knows when to stop", x=0.01, ha="left", color=INK, fontsize=13)
fig.tight_layout(rect=(0, 0.04, 1, 0.94)); fig.savefig("F4_safety_vs_autonomy.png", dpi=170)

cal = json.load(open("calibration.json"))
qs = [float(q) for q in cal["curve"]]
fig, ax = plt.subplots(1, 2, figsize=(11, 4.2), facecolor="white")
ax[0].plot(qs, [cal["curve"][str(q)]["held"]["coverage"] * 100 for q in qs], color="#2a78d6", lw=2, marker="o", label="held-out coverage")
ax[0].plot(qs, [cal["curve"][str(q)]["dev"]["coverage"] * 100 for q in qs], color="#9a9890", lw=1.5, marker="o", ms=4, label="dev coverage")
ax[0].axhline(90, color="#eb6834", ls="--", lw=1.2); ax[0].text(0.05, 91, "90% target", color="#eb6834", fontsize=9)
ax[0].axvline(0.30, color=MUTED, ls=":", lw=1); ax[0].text(0.31, 98.5, "current setting", color=MUTED, fontsize=9)
ax[0].set_ylim(75, 102); ax[0].set_xlabel("inclusion threshold q", color=MUTED); ax[0].set_ylabel("true cause inside the set (%)", color=MUTED)
ax[0].set_title("Coverage vs target", loc="left", color=INK, fontsize=11); ax[0].legend(frameon=False, loc="lower left")
ax[1].plot(qs, [cal["curve"][str(q)]["held"]["escalation_rate"] * 100 for q in qs], color="#1baf7a", lw=2, marker="o")
ax[1].axvline(0.30, color=MUTED, ls=":", lw=1)
ax[1].set_xlabel("inclusion threshold q", color=MUTED); ax[1].set_ylabel("incidents sent to a human (%)", color=MUTED)
ax[1].set_title("Cost of caution: escalation rate (held-out)", loc="left", color=INK, fontsize=11)
for a in ax:
    for s in ("top", "right"): a.spines[s].set_visible(False)
    a.tick_params(colors=MUTED); a.yaxis.grid(True, color="#e6e5e0"); a.set_axisbelow(True)
fig.suptitle("F6  Calibration of the diagnostic gate (100 dev / 200 held-out synthetic incidents)", x=0.01, ha="left", color=INK, fontsize=13)
fig.tight_layout(rect=(0, 0, 1, 0.93)); fig.savefig("F6_calibration.png", dpi=170)
print("clear:", {v: (s['correct_autonomous_recovery_pct'], s['unsafe_run_rate_pct']) for v, s in clear.items()})
print("ambiguous:", {v: (100 - s['under_escalation_pct'], s['unsafe_run_rate_pct']) for v, s in amb.items()})
