"""
test_llm.py  -  Checks the AI diagnosis step WITHOUT needing internet or a key.
We replace the real model call with fake answers and confirm the safety behavior.
    python3.15 test_llm.py
"""
import json, os, tempfile
import llm_diagnose as L
from detect import detect
from revive import Revive
from sim import Sim
import scenarios as S

L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "cache.json")
n = 0
def check(c, m):
    global n; n += 1; assert c, "FAILED: " + m

def finding(seed=0):
    sim = Sim(seed=seed); sim.corrupt_vendor_ibans(["V1", "V2", "V3"]); sim.intake(sim.make_invoices(6))
    sim.matching(); sim.approval()
    return detect(sim)[0]

f = finding()
dx = L.make_llm_diagnoser()

# 1) AI agrees with the rules -> accepted
L._call_model = lambda p: json.dumps({"scores": {"SYNC_IBAN_CORRUPTION": 0.93, "POSSIBLE_FRAUD": 0.07},
                                      "cited_evidence": ["3 suppliers, same batch"], "explanation": "Looks like a sync bug."})
r = dx(f); check(r["prediction_set"] == ["SYNC_IBAN_CORRUPTION"] and "agrees" in r["method"], "agree case")

# 2) AI disagrees -> not certain -> whole run escalates, nothing unsafe happens
L._call_model = lambda p: json.dumps({"scores": {"POSSIBLE_FRAUD": 0.9, "SYNC_IBAN_CORRUPTION": 0.1},
                                      "cited_evidence": [], "explanation": "Could be fraud."})
for seed in range(10):
    sim, rv = S.d2_sync_bug(seed=seed, agent=Revive(diagnoser=L.make_llm_diagnoser()))
    check([i["outcome"] for i in rv.incidents] == ["ESCALATED"], f"disagree must escalate (seed {seed})")
    s = sim.safety(); check(s["duplicate_payments"] == 0 and s["misdirected_payments"] == 0, "disagree unsafe")
    check(all(i["status"] == "HELD" for i in sim.invoices.values() if i["vendor"] in ("V1", "V2", "V3")), "disagree must hold the suspicious suppliers")

# 3) garbage from the model -> falls back to rules, still works
for bad in ["not json at all", json.dumps({"scores": {"MADE_UP": 1.0}}), json.dumps({"nope": 1})]:
    L._call_model = lambda p, bad=bad: bad
    L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "c.json")
    sim, rv = S.d2_sync_bug(seed=1, agent=Revive(diagnoser=L.make_llm_diagnoser()))
    check([i["outcome"] for i in rv.incidents] == ["VERIFIED_CLOSED"], "garbage must fall back to rules")
    check("unavailable" in rv.incidents[0]["diagnosis"]["method"], "garbage method label")

# 4) a good live answer is saved; later with no internet the saved answer is used
L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "c2.json")
L._call_model = lambda p: json.dumps({"scores": {"SYNC_IBAN_CORRUPTION": 0.95}, "cited_evidence": ["x"], "explanation": "ok"})
dx = L.make_llm_diagnoser(); dx(f)
def offline(p): raise OSError("no internet")
L._call_model = offline
r = L.make_llm_diagnoser()(f); check("saved" in r["method"], "cache replay")

# 5) no key and no cache -> plain rules
L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "c3.json")
L._call_model = L.__dict__["_call_model"]
os.environ.pop("GEMINI_API_KEY", None)
import importlib; importlib.reload(L); L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "c4.json")
r = L.make_llm_diagnoser()(f); check("unavailable" in r["method"] and r["prediction_set"] == ["SYNC_IBAN_CORRUPTION"], "no key -> rules")

# 6) a failing live call shows WHY in the label, and never leaks the key
import io, urllib.error, urllib.request
os.environ["GEMINI_API_KEY"] = "SECRET-KEY-123"
importlib.reload(L); L.CACHE_PATH = os.path.join(tempfile.mkdtemp(), "c5.json")
def boom(req, timeout=0):
    raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error": {"message": "model not found SECRET-KEY-123"}}'))
urllib.request.urlopen = boom
r = L.make_llm_diagnoser()(f)
check("HTTP 404" in r["method"] and "model not found" in r["method"], "error reason shown")
check("SECRET-KEY-123" not in r["method"], "key must never appear in the label")
os.environ.pop("GEMINI_API_KEY", None)

# 7) a busy (503) answer is retried, then the backup model is used
import time as _t
_t.sleep = lambda x: None
os.environ["GEMINI_API_KEY"] = "SECRET-KEY-123"
importlib.reload(L); L.time.sleep = lambda x: None
calls = []
class FakeResp:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def read(self): return json.dumps({"candidates": [{"content": {"parts": [{"text": "OK-TEXT"}]}}]}).encode()
def busy_then_ok(req, timeout=0):
    calls.append(req.full_url)
    if len(calls) == 1:
        raise urllib.error.HTTPError("u", 503, "Unavailable", {}, io.BytesIO(b'{"error": {"message": "busy"}}'))
    return FakeResp()
urllib.request.urlopen = busy_then_ok
check(L._call_model("hi") == "OK-TEXT" and len(calls) == 2 and calls[0] == calls[1], "503 retried on same model")
calls.clear()
def main_down(req, timeout=0):
    calls.append(req.full_url)
    if "flash-lite" not in req.full_url:
        raise urllib.error.HTTPError("u", 404, "Not Found", {}, io.BytesIO(b'{"error": {"message": "gone"}}'))
    return FakeResp()
urllib.request.urlopen = main_down
check(L._call_model("hi") == "OK-TEXT" and "flash-lite" in calls[-1], "falls back to backup model")
calls.clear()
def slow_main(req, timeout=0):
    calls.append(req.full_url)
    if "flash-lite" not in req.full_url:
        raise TimeoutError("The read operation timed out")
    return FakeResp()
urllib.request.urlopen = slow_main
check(L._call_model("hi") == "OK-TEXT" and "flash-lite" in calls[-1], "timeout falls back to backup model")
os.environ.pop("GEMINI_API_KEY", None)

print(f"ALL GOOD: {n} AI-step checks passed.")
