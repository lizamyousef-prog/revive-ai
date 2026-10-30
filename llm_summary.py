"""
llm_summary.py  -  Gemini explains, the code decides.

When ReVive hands an incident to a person, Gemini writes a short plain-language note:
what happened, why ReVive stopped, and what the person should check next.

Safety rules:
  * This runs only AFTER ReVive has already decided to escalate. It cannot change any decision.
  * Gemini sees only the facts from the incident report, and is told to use nothing else.
  * Every number and ID in the note is checked against those facts. If anything is not
    there, the note is rejected and a plain template summary is used instead.
  * If Gemini is slow, down or has no key: saved answer (llm_cache.json), then the template.
"""
import hashlib
import json
import re

import llm_diagnose as L

CAUSE_NAMES = {
    "INTAKE_DROP": "invoices lost at intake",
    "SYNC_IBAN_CORRUPTION": "a vendor-sync bug that damaged bank accounts",
    "POSSIBLE_FRAUD": "a possibly fraudulent bank-account change",
    "BANK_TIMEOUT_UNKNOWN": "a bank timeout with an unknown payment result",
    "UNKNOWN_OTHER": "an unknown cause",
}

PROMPT = """You write a short handoff note for a finance manager. An automated payments-recovery system
called ReVive found a problem and has stopped to ask a person to decide.

Write 2 or 3 plain sentences, under 70 words in total:
1. what happened, 2. why ReVive stopped instead of fixing it, 3. what the person should check next.

Strict rules: use ONLY the facts below. Do not invent any number, amount, name, ID or date.
Write amounts exactly as given (for example "SAR 40,000"). No greetings, no bullet points.
Reply with JSON only: {"summary": "..."}

Facts:
"""


def _amount(inc):
    ev, k = inc.get("evidence", {}), inc.get("kind")
    if k == "payee_iban_mismatch":
        return ev.get("open_amount", 0)
    if k == "unknown_payment":
        return ev.get("amount", 0)
    if k == "conservation_gap":
        return ev.get("missing_value", 0)
    return 0


def _reason(reason):
    if "not certain" in reason:
        return "the evidence fits more than one cause, so it would not guess"
    if "not permitted" in reason:
        return "the only fix would change bank details, which is never automatic"
    if "not verified" in reason:
        return "its fixes did not verify within the attempt limit"
    if "single diagnosis" in reason:
        return "a rollback needs one clear cause"
    return reason


def facts(inc):
    """The ONLY information the AI is allowed to use."""
    e, ev = inc["escalation"], inc.get("evidence", {})
    suppliers = [v["vendor"] for v in ev.get("vendors", [])]
    f = {
        "incident": inc["id"],
        "problem": inc["symptoms"],
        "why_revive_stopped": _reason(e["reason"]),
        "possible_causes": [CAUSE_NAMES.get(c, c) for c in e.get("possible_causes", [])],
        "evidence": [x for x in e.get("cited_evidence", []) if "disagree" not in x],
        "suppliers": suppliers,
        "invoices_on_hold": e.get("still_held_invoices", []),
        "amount_at_risk": f"SAR {_amount(inc):,}",
        "actions_tried": [f"{a['action']} ({'worked' if a['verified'] else 'did not verify'})"
                          for a in e.get("actions_tried", [])],
        "attempts_made": len(e.get("actions_tried", [])),
        "revive_did_not": "resend, reverse or change any bank details",
    }
    if inc.get("kind") == "unknown_payment":
        f["payment"] = {"invoice": ev.get("invoice"), "bank_reference": ev.get("txn_key")}
    if any("disagree" in x for x in e.get("cited_evidence", [])):
        f["note"] = "the rules and the AI diagnosis disagreed about the cause"
    return f


ID_RE = re.compile(r"\b(?:INV-\d+|INC-\d+|TX-[A-Z0-9-]+|SYNC-\d+|V\d+)\b")
NUM_RE = re.compile(r"\d[\d,]*(?:\.\d+)?")


def _numbers(text):
    return {n.replace(",", "").rstrip(".") for n in NUM_RE.findall(ID_RE.sub(" ", text))}


def grounded(summary, f):
    """True only if every ID and number in the summary appears in the facts."""
    blob = json.dumps(f)
    if not summary or len(summary) > 600:
        return False
    if not set(ID_RE.findall(summary)) <= set(ID_RE.findall(blob)):
        return False
    return _numbers(summary) <= _numbers(blob)


def template(f):
    """Plain summary written by code, used whenever the AI note is missing or rejected."""
    held, sup, pay = f["invoices_on_hold"], f["suppliers"], f.get("payment")
    causes = " or ".join(f["possible_causes"]) or "an unknown cause"
    if pay:
        what = f"The payment for {pay['invoice']} ({f['amount_at_risk']}) timed out, and nobody knows yet whether it went through."
    elif len(sup) == 1:
        what = f"Supplier {sup[0]}'s bank account no longer matches the last verified one. The likely cause is {causes}."
    elif sup:
        what = f"The bank accounts of suppliers {', '.join(sup)} no longer match the verified ones. The likely cause is {causes}."
    else:
        what = f"{f['problem'][0].upper() + f['problem'][1:]}. The likely cause is {causes}."
    if pay:
        why = "ReVive could not confirm it with the bank, so it did not pay again."
    else:
        why = f"ReVive stopped because {f['why_revive_stopped']}."
    if held:
        why += f" {', '.join(held)} ({f['amount_at_risk']}) {'is' if len(held) == 1 else 'are'} on hold, and no bank details were changed."
    if "fraudulent" in causes:
        nxt = "Please confirm the supplier's bank details through a contact you already trust before releasing the payment."
    elif pay:
        nxt = f"Please ask the bank whether {pay['bank_reference']} settled before paying again."
    else:
        nxt = "Please check the vendor-sync batch and restore the verified bank accounts by hand."
    return f"{what} {why} {nxt}"


def _key(f):
    return "summary:" + hashlib.sha1(json.dumps(f, sort_keys=True).encode()).hexdigest()


def make_summarizer(live=True):
    def summarize(inc):
        f = facts(inc)
        key, text, source, why = _key(f), None, None, ""
        if live:
            try:
                reply = json.loads(L._call_model(PROMPT + json.dumps(f, indent=1)))
                text, source = str(reply.get("summary", "")).strip(), "live"
            except Exception as e:
                why = "no key" if isinstance(e, L.NoKey) else "AI unavailable"
        if text is None:
            saved = L._load_cache().get(key)
            if saved:
                text, source = saved.get("summary"), "saved"
        if text is not None and not grounded(text, f):
            text, why = None, "AI note rejected: it mentioned something not in the facts"
        if text is None:
            return {"text": template(f), "source": "template", "note": why or "AI unavailable"}
        if source == "live":
            cache = L._load_cache()
            cache[key] = {"summary": text}
            L._save_cache(cache)
        return {"text": text, "source": source, "note": "checked against the incident facts"}
    return summarize
