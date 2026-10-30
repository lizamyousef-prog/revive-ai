"""
test_summary.py  -  Checks the AI incident summary (no internet needed: Gemini is faked).

    python3 test_summary.py
"""
import json
import os
import tempfile

import llm_diagnose as L
import llm_summary as M
import scenarios as S
import held_out as H
from revive import Revive

L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "cache.json")
os.environ.pop("GEMINI_API_KEY", None)
passed = 0


def check(cond, msg):
    global passed
    assert cond, msg
    passed += 1


def escalated(fn, seed=7, summarizer=None):
    sim, rv = fn(seed=seed, agent=Revive(summarizer=summarizer))
    return [i for i in rv.incidents if i["outcome"] == "ESCALATED"]


def fake(reply):
    def call(prompt):
        if isinstance(reply, Exception):
            raise reply
        return json.dumps({"summary": reply})
    return call


real_call = L._call_model
inc = escalated(S.d2_fraud)[0]
f = M.facts(inc)

# 1. facts hold only what is in the incident
check(f["suppliers"] == ["V2"] and f["invoices_on_hold"] == ["INV-001"], "facts: supplier and held invoice")
check(f["amount_at_risk"] == "SAR 300,000", "facts: amount")

# 2. a grounded live note is accepted and saved
L._call_model = fake("Supplier V2's bank account changed before the SAR 300,000 invoice INV-001. "
                     "ReVive held it because changing bank details is never automatic. Confirm the account with V2.")
r = M.make_summarizer()(inc)
check(r["source"] == "live" and "V2" in r["text"], "grounded live note accepted")
check(any(k.startswith("summary:") for k in L._load_cache()), "live note saved for offline replay")

# 3. a made-up amount is rejected
L._call_model = fake("Supplier V2 is owed SAR 450,000 on INV-001. Please check.")
r = M.make_summarizer()(inc)
check(r["source"] == "template" and "rejected" in r["note"], "invented amount rejected")

# 4. a made-up invoice or supplier is rejected
L._call_model = fake("Supplier V9 changed the account on INV-777.")
check(M.make_summarizer()(inc)["source"] == "template", "invented IDs rejected")

# 5. Gemini down -> saved answer
L._call_model = fake(L.ApiError(503, "busy"))
check(M.make_summarizer()(inc)["source"] == "saved", "service down -> saved note")

# 6. nothing saved and no key -> template, which is itself grounded
L._call_model = real_call
L._save_cache({})
r = M.make_summarizer()(inc)
check(r["source"] == "template" and M.grounded(r["text"], f), "no key -> grounded template")

# 7. every escalating demo gets a grounded template note
for fn in (S.d2_fraud, S.d2_ambiguous, S.d2_main, S.d3_bank_down, S.d5_fix_fails_twice):
    for i in escalated(fn, summarizer=M.make_summarizer(live=False)):
        s = i["escalation"]["ai_summary"]
        check(s["text"] and M.grounded(s["text"], M.facts(i)), f"template grounded: {fn.__name__}")

# 8. a crashing summarizer never changes the outcome
def boom(_):
    raise RuntimeError("summary crashed")
a, b = escalated(S.d2_fraud), escalated(S.d2_fraud, summarizer=boom)
check([i["outcome"] for i in a] == [i["outcome"] for i in b] and "ai_summary" not in b[0]["escalation"],
      "crash in summary -> same decision, no note")

# 9. decisions are identical with and without the summary, everywhere
def fingerprint(sim, rv):
    return (json.dumps([(i["outcome"], i["timeline"]) for i in rv.incidents], sort_keys=True),
            json.dumps(sim.summary(), sort_keys=True, default=str))

L._call_model = fake("Supplier V1 needs a check.")
cases = list(S.SCENARIOS.values()) + [fn for fn, _ in H.HELD_OUT.values()]
for fn in cases:
    for seed in range(10):
        plain = fingerprint(*fn(seed=seed, agent=Revive()))
        with_note = fingerprint(*fn(seed=seed, agent=Revive(summarizer=M.make_summarizer())))
        check(plain == with_note, f"same decisions: {fn.__name__} seed {seed}")

# 10. closed incidents never call the summarizer
calls = []
S.d1_invisible_failure(seed=7, agent=Revive(summarizer=lambda i: calls.append(i)))
check(not calls, "no summary for incidents ReVive fixed itself")

L._call_model = real_call
print(f"ALL GOOD: {passed} AI-summary checks passed.")
