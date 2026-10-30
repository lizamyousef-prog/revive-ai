# ReVive AI

**A safety and recovery layer for autonomous finance agents.**
When AI agents run a company's payments, ReVive makes sure every invoice is paid **once**, to the **right account**, or a human knows exactly why not.

HUMAIN × Misk Future AI Builders Hackathon · Challenge 1 (Agentic Recovery of a Failing System) · Liza AlGhazal

| | |
|---|---|
| Live dashboard | https://revive-ai-dashboard.netlify.app |
| Presentation | https://canva.link/l24yiy77yuwwk5v |
| Demo video | VIDEO_LINK |

---

## The problem

AI agents are starting to act, not just advise. In accounts payable, their worst failures make no noise:

| Challenge 1 failure | How it shows up in accounts payable | What catches it in ReVive |
|---|---|---|
| Payments silently drop | The bank call times out; the payment is UNKNOWN | Ask the bank by transaction reference before anything else |
| A queue loses messages under load | At a month-end spike the intake agent drops invoices, with no error | Conservation check: received = matched + pending + rejected + paid |
| A sync job slowly corrupts data | A nightly bug truncates supplier bank accounts | Every payee account must equal the last verified one |
| A repair agent never escalates | A naive fixer guesses and acts | Two gates, a 2-attempt limit and verification |

A repair agent that just guesses makes things worse: in our tests a naive fixer sent 240 payments to the wrong account and paid 30 twice in 300 runs.

**Research question.** Can constrained AI diagnosis choose better between recovering and escalating than a well-engineered rules monitor, without compromising financial safety?

## How ReVive works

Code acts. AI only diagnoses.

```
DETECT -> CONTAIN -> DIAGNOSE -> GATE A -> GATE B -> RECOVER -> VERIFY -> closed
                                   |         |                    |
                                   +---------+--------------------+--> HUMAN DECIDES (incident report with evidence)
```

1. **Detect** (deterministic, no LLM): business invariants such as every invoice accounted for and every payee account verified.
2. **Contain**: affected payments are held before any repair.
3. **Diagnose**: the rules and a live Gemini call each name possible causes from a small fixed list, citing evidence. This is the only step that uses AI.
4. **Gate A, "are we sure?"**: the answers are combined; exactly one cause must remain, otherwise ReVive escalates. Calibrated on 100 synthetic incidents: the true cause stays in the set 95% of the time (target 90%).
5. **Gate B, "is it allowed?"**: a fixed risk policy the AI cannot change, plus a dry run on a copy of the system.
   - LOW: replay an invoice, ask the bank, resubmit after a confirmed FAILED with the same key, after a dry run
   - MEDIUM: roll back a vendor-sync batch, only with one cause and a passing dry run
   - HIGH: new bank details, resending while UNKNOWN, reversing a settled payment, never automatic
6. **Recover**: permitted fixes only. A timeout is not a failure: ReVive asks the bank first and never resends blindly. The simulated bank rejects duplicate idempotency keys.
7. **Verify**: the incident closes only when the business state is correct. At most 2 attempts, then a human gets an incident report (`incidents/INC-xxx.json`) with the evidence, the remaining causes and the actions not taken.

If Gemini is slow or unavailable (12-second limit, one retry, a backup model), ReVive falls back to a saved answer and then to its rules. Both gates apply either way.

## Results

Three systems on identical faults: a **naive fixer** (same detection, then just fixes), **strong rules** (everything ReVive has except Gate A) and **ReVive**. Development set: 10 failures × 30 seeds = 300 runs. Held-out set: 7 failures frozen before testing × 30 seeds = 210 runs.

| Metric (dev / held-out) | Naive fixer | Strong rules | ReVive |
|---|---|---|---|
| Task success | 30% / 14.3% | 90% / 85.7% | **100% / 100%** |
| Unsafe runs | 50% / 42.9% | 0% / 0% | **0% / 0%** |
| Missed escalations | 100% / 100% | 20% / 25% | **0% / 0%** |
| Over-escalation | 0% / 0% | 0% / 0% | **0% / 0%** |

On clear cases strong rules tie ReVive. On ambiguous evidence (for example a changed bank account that could be a sync bug or fraud) strong rules guess and act; ReVive escalated every one. Over-escalation is 0%, so ReVive is not safe simply by refusing to act. Held-out testing caught a real bug in ReVive (a rollback that repaired only some vendors); it was fixed and covered by a regression test, and `results_v1.json` keeps the run from before the fix.

## Run it

Python 3.10 or newer. The core needs no installs. `charts.py` needs `matplotlib`.

```
python3 test_core.py        # 2,010 checks across 30 seeds and 10 scenarios
python3 test_llm.py         # 44 checks of the AI step with fake answers (no internet needed)
python3 run_demo.py         # every demo scenario as a plain-English report
python3 evaluate.py         # the full evaluation above, saved to results.json
python3 calibrate.py        # Gate A calibration, saved to calibration.json
python3 charts.py           # the safety-vs-autonomy and calibration figures
python3 serve.py            # live dashboard at http://localhost:8000 (Ctrl + C to stop)
```

**Live AI (optional).** Without a key everything runs on the rules. To add Gemini as the second opinion, type this in the terminal first (never put a key in a file):

```
export GEMINI_API_KEY="your-key"
python3 check_ai.py         # explains any connection problem and lists the models your key can use
```

`python3 build_public.py` records demo runs into `public.html`, the self-contained public dashboard.

## Project structure

| File | What it does |
|---|---|
| `sim.py` | The failing system: accounts-payable agents, vendor sync, event log, ledger, and a bank with a payment state machine and idempotency keys |
| `scenarios.py` | Development failures and the three demos (D1 invisible failure, D2 same symptom with different causes, D3 the agent admits failure) |
| `held_out.py` | The frozen held-out failures (H1–H7) |
| `detect.py` | Business-invariant detection |
| `diagnose.py` | Rules diagnosis: a set of possible causes from a fixed fault list, with cited evidence |
| `llm_diagnose.py` | Gemini second opinion, with timeout, retry, backup model and a saved-answer fallback |
| `revive.py` | The recovery loop: contain, Gate A, Gate B, dry run, recover, verify, escalate, incident reports |
| `baseline.py` | The naive fixer and the strong-rules monitor |
| `evaluate.py` | Evaluation of the three systems on dev and held-out sets |
| `calibrate.py`, `charts.py` | Gate A calibration and the result figures |
| `serve.py`, `dash_api.py`, `dashboard.html` | The live dashboard |
| `build_public.py`, `public.html` | The public dashboard with recorded runs |
| `test_core.py`, `test_llm.py` | Tests |
| `figures/` | Architecture diagram, D2 outcomes (F3) and D1 incident timeline (F5); `F4_safety_vs_autonomy.png` and `F6_calibration.png` are made by `charts.py` |
| `incidents/` | Example incident reports written by ReVive |
| `llm_cache.json` | Saved real Gemini answers, replayed if the internet drops |

## Scope 

- **Business process:** accounts payable, run by five AI agents: intake, matching, approval, payment and a nightly vendor sync.
- **Failures covered:** month-end overload that silently drops invoices, supplier bank-account mismatches (sync bug or fraud), bank timeouts that leave a payment UNKNOWN, and repairs that silently fail.
- **Evaluation:** 17 failure scenarios (10 development, 7 held-out and frozen before testing), 30 seeds each, three systems compared over 510 runs.
- **Environment:** a reproducible simulation, so every failure can be injected and replayed exactly.
- **AI:** Gemini gives a second opinion on diagnosis; every action stays behind the two deterministic gates.
