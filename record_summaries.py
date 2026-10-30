"""
record_summaries.py  -  Ask Gemini for the handoff notes once and save them in llm_cache.json,
so the public dashboard (which cannot call Gemini) can show real Gemini notes.

    export GEMINI_API_KEY="your-key"
    python3 record_summaries.py
"""
import os

import dash_api
from diagnose import diagnose
from llm_diagnose import make_llm_diagnoser
from llm_summary import make_summarizer

if not os.environ.get("GEMINI_API_KEY"):
    raise SystemExit("Set your key first:  export GEMINI_API_KEY=\"your-key\"")

SEED = 7      # the same recorded runs as the public dashboard
ok = 0
for key in dash_api.CASES:
    # same diagnosis as the public page: saved Gemini answer for the ambiguous case, rules elsewhere
    dash_api.make_llm_diagnoser = (lambda: make_llm_diagnoser(live=False)) if key == "d2b" else (lambda: diagnose)
    dash_api.make_summarizer = lambda: make_summarizer(live=True)
    run = dash_api.run_case(key, "revive", SEED)
    for inc in run["incidents"]:
        s = (inc.get("escalation") or {}).get("ai_summary")
        if not s:
            continue
        ok += s["source"] in ("live", "saved")
        print(f"\n[{run['label']}]  source: {s['source']}  ({s['note']})\n  {s['text']}")
print(f"\nDone: {ok} Gemini note(s) saved in llm_cache.json.")
