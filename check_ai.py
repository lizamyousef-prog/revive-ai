"""
check_ai.py  -  Tests your AI key with ONE call and tells you plainly what happened.

    python3.15 check_ai.py
(type  export GEMINI_API_KEY="your-key"  in the same terminal first)
"""
import json
import os
import urllib.request

import llm_diagnose as L

key = os.environ.get("GEMINI_API_KEY")
if not key:
    print("No GEMINI_API_KEY found in this terminal. Type  export GEMINI_API_KEY=\"your-key\"  first.")
    raise SystemExit
print("Key found. Model:", os.environ.get("GEMINI_MODEL", L.DEFAULT_MODEL))
try:
    text = L._call_model('Reply with exactly this JSON: {"ok": true}')
    print("SUCCESS - the AI answered:", text[:80])
except Exception as e:
    print("FAILED:", e)
    print("\nModels your key can use (look for one with 'flash'):")
    try:
        req = urllib.request.Request("https://generativelanguage.googleapis.com/v1beta/models?pageSize=100",
                                     headers={"x-goog-api-key": key})
        with urllib.request.urlopen(req, timeout=20) as r:
            models = json.loads(r.read()).get("models", [])
        names = [m["name"].replace("models/", "") for m in models
                 if "generateContent" in m.get("supportedGenerationMethods", [])]
        for n in names[:25]:
            print("   ", n)
        print("\nThen run:   export GEMINI_MODEL=\"one-of-the-names-above\"   and  python3.15 check_ai.py  again.")
    except Exception as e2:
        print("Could not list models either:", str(e2).replace(key, "***")[:160])
