"""
llm_diagnose.py  -  The AI (language model) diagnosis step.

How it works (two opinions, one safety rule):
  1. The rules produce a diagnosis (diagnose.py).
  2. The AI model reads the same evidence and gives its own diagnosis + a plain explanation.
  3. If they AGREE -> use it.  If they DISAGREE -> the diagnosis is "not certain" and ReVive
     escalates to a human (gate A).  The AI can never push ReVive into a risky action on its own.

Fallback chain, so the demo NEVER depends on internet:
     live AI call  ->  saved answer from an earlier live run (llm_cache.json)  ->  rules only

Setup (optional):  put your key in the terminal that runs serve.py, never in a file:
     export GEMINI_API_KEY="your-key-here"
Uses only Python's standard library (no installs).
"""
import hashlib
import json
import os
import time
import urllib.error
import urllib.request

from diagnose import diagnose as rules_diagnose, TAXONOMY, INCLUDE_THRESHOLD

CACHE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "llm_cache.json")
DEFAULT_MODEL = "gemini-flash-latest"


class NoKey(Exception):
    pass


PROMPT = """You are a careful diagnostic assistant inside a supplier-payments recovery system.
Below is evidence about ONE problem found in the system. Decide which cause is most likely.

Allowed causes (use ONLY these exact names):
- INTAKE_DROP: invoices received but silently lost before processing
- SYNC_IBAN_CORRUPTION: a data-sync bug damaged supplier bank accounts (accounts look truncated, many suppliers, same sync batch)
- POSSIBLE_FRAUD: a supplier's bank account was replaced with a different one (single supplier, recent change, large invoice)
- BANK_TIMEOUT_UNKNOWN: a payment timed out and its result is unknown
- UNKNOWN_OTHER: none of the above fits

Rules: give a probability for each plausible cause (they should add up to about 1). If two causes are both plausible, give BOTH a meaningful probability. Do not be overconfident.
Reply with JSON only, in this shape:
{"scores": {"CAUSE_NAME": 0.0}, "cited_evidence": ["short fact from the evidence"], "explanation": "one or two plain sentences"}

Evidence:
"""


class ApiError(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


FALLBACK_MODELS = ["gemini-flash-lite-latest"]    # lighter backup if the main model is busy or missing


def _call_one(model, prompt, key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0, "responseMimeType": "application/json"}}).encode()
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json",
                                                          "x-goog-api-key": key})   # key kept out of the URL
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            data = json.loads(r.read())
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read())["error"]["message"]
        except Exception:
            pass
        raise ApiError(e.code, f"HTTP {e.code} {detail}".replace(key, "***")[:160])
    except urllib.error.URLError as e:
        raise ApiError(0, f"network problem: {e.reason}".replace(key, "***")[:160])
    except (TimeoutError, OSError) as e:          # slow reply: treated like "busy"
        raise ApiError(504, f"timed out waiting for Google ({e})".replace(key, "***")[:160])


def _call_model(prompt):
    """Try the main model (retry once if it is busy), then the backup model."""
    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        raise NoKey("no GEMINI_API_KEY set")
    models = [os.environ.get("GEMINI_MODEL", DEFAULT_MODEL)] + FALLBACK_MODELS
    last = None
    for model in models:
        for attempt in (1, 2):
            try:
                return _call_one(model, prompt, key)
            except ApiError as e:
                last = e
                if e.code in (429, 500, 503) and attempt == 1:
                    time.sleep(1.5)          # busy: wait a moment and try the same model once more
                    continue
                break                        # anything else: move on to the backup model
    raise last


def parse_reply(text):
    """Turn the model's text into a safe, validated structure. Raises on anything odd."""
    obj = json.loads(text)
    scores = {}
    for k, v in obj["scores"].items():
        if k in TAXONOMY:
            scores[k] = max(0.0, min(1.0, float(v)))
    if not scores:
        raise ValueError("no valid causes in reply")
    cited = [str(x)[:120] for x in obj.get("cited_evidence", [])][:5]
    return {"scores": scores, "cited_evidence": cited, "explanation": str(obj.get("explanation", ""))[:300]}


def _load_cache():
    try:
        with open(CACHE_PATH) as f:
            return json.load(f)
    except Exception:
        return {}


def _save_cache(cache):
    try:
        with open(CACHE_PATH, "w") as f:
            json.dump(cache, f, indent=2)
    except Exception:
        pass


def _fingerprint(finding):
    blob = json.dumps({"kind": finding["kind"], "evidence": finding["evidence"]}, sort_keys=True)
    return hashlib.sha1(blob.encode()).hexdigest()


def ai_available():
    return bool(os.environ.get("GEMINI_API_KEY"))


def make_llm_diagnoser(live=True):
    def diagnose(finding):
        base = rules_diagnose(finding)
        if finding["kind"] != "payee_iban_mismatch":
            return base          # one possible cause by construction: no need to ask the AI (keeps runs fast)
        fp = _fingerprint(finding)
        prompt = PROMPT + json.dumps({"kind": finding["kind"], "summary": finding["summary"],
                                      "evidence": finding["evidence"]}, indent=1)
        reply, source, err = None, None, "bad reply"
        try:
            if not live:
                raise NoKey("live calls switched off")
            reply, source = parse_reply(_call_model(prompt)), "live"
            cache = _load_cache()
            cache[fp] = reply
            _save_cache(cache)
        except Exception as e:
            err = str(e)[:120] if not isinstance(e, NoKey) else "no key"
            cached = _load_cache().get(fp)
            if cached:
                try:
                    reply, source = parse_reply(json.dumps(cached)), "saved"
                except Exception:
                    reply = None
        if reply is None:
            out = dict(base)
            out["method"] = f"rules (AI unavailable: {err})"
            return out

        ai_set = [c for c, s in sorted(reply["scores"].items(), key=lambda x: -x[1]) if s >= INCLUDE_THRESHOLD]
        if set(ai_set) == set(base["prediction_set"]):
            return {"prediction_set": base["prediction_set"], "scores": reply["scores"],
                    "cited_evidence": reply["cited_evidence"] or base["cited_evidence"],
                    "explanation": reply["explanation"], "method": f"AI ({source}) agrees with rules"}
        union = list(dict.fromkeys(base["prediction_set"] + ai_set))      # disagreement -> not certain
        return {"prediction_set": union, "scores": reply["scores"],
                "cited_evidence": base["cited_evidence"] + ["AI and rules disagree"],
                "explanation": reply["explanation"], "method": f"AI ({source}) and rules DISAGREE"}
    return diagnose
