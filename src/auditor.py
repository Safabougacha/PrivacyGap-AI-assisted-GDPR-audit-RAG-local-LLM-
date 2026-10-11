"""Step 4 - The audit engine: one data flow in, one verified finding out.

  1. CLASSIFY  keyword rule decides if the data is a special category (art. 9);
               the LLM gives a second opinion -> disagreement = human review
  2. POLICY    the LLM reads the privacy policy: does the flow contradict it?
  3. RISK      the audit grid (src/rules.py) sets the risk level, with reasons
  4. RETRIEVE  multi-query search in the GDPR; check that every article the
               grid relies on was actually retrieved (provenance check)
  5. WRITE     the LLM writes justification + recommendation from the passages
"""
import json
import re
import time

from pydantic import ValidationError

from src.llm import ask
from src.retriever import search
from src.rules import assess_risk, is_special_category, transfer_outside_eu
from src.schemas import DataOpinion, FlowResult, PolicyMatch, Writeup

PASSAGE_CHARS = 600


def _ask_json(prompt: str, model: type, retries: int = 2):
    """Ask for JSON, validate it with Pydantic, re-ask with the error if invalid."""
    last_error = ""
    for _ in range(retries + 1):
        full = prompt if not last_error else (
            f"{prompt}\n\nYour previous answer was invalid: {last_error}\n"
            "Return ONLY valid JSON with exactly the requested keys.")
        try:
            return model.model_validate(json.loads(ask(full, json_output=True)))
        except (json.JSONDecodeError, ValidationError) as exc:
            last_error = str(exc)[:300]
    raise RuntimeError(f"Model kept returning invalid JSON: {last_error}")


# 1. second opinion on the data - ONLY the data text, balanced examples
def llm_data_opinion(data_fields: str) -> DataOpinion:
    return _ask_json(
        "Does this data describe a person's health or sex life (GDPR art. 9)?\n"
        "Look ONLY at the data below. Examples:\n"
        '- "blood pressure readings" -> true\n'
        '- "email address" -> false\n'
        '- "device identifier and app clicks" -> false\n'
        '- "account data and app content" -> false\n\n'
        f'DATA: "{data_fields}"\n'
        'Return JSON: {"health_or_sex_life": bool, "data_description": "<short legal wording>"}',
        DataOpinion,
    )


# 2. read the privacy policy - two narrow questions, each backed by an exact quote
def commitments(policy: str) -> dict[str, str]:
    """{'P1': 'text of P1', ...} parsed from the numbered policy."""
    return {m.group(1): m.group(2).strip()
            for m in re.finditer(r"\*\*(P\d+)\.\*\*\s*(.+?)(?=\n\s*\*\*P\d+\.\*\*|\Z)", policy, re.S)}


def _overlap(quote: str, text: str) -> float:
    words = re.findall(r"[a-z]{4,}", quote.lower())
    if len(words) < 2:
        return 0.0
    return sum(w in text.lower() for w in words) / len(words)


def locate_quote(quote: str, items: dict[str, str]) -> str:
    """Find which commitment the quote REALLY comes from (the model often quotes
    the right sentence with the wrong number). '' if the quote is not in the policy."""
    best_id, best = "", 0.0
    for cid, text in items.items():
        score = _overlap(quote, text)
        if score > best:
            best_id, best = cid, score
    return best_id if best >= 0.7 else ""


def quote_is_real(match: PolicyMatch, items: dict[str, str]) -> bool:
    """Used by the debug script: does the quote really come from the named commitment?"""
    text = items.get(match.commitment.strip().upper())
    return bool(text) and _overlap(match.quote, text) >= 0.7


PROHIBITION = r"\b(not|never)\b"


def find_commitment(question: str, flow: dict, policy: str, items: dict[str, str]) -> str:
    """Ask one narrow question; return the commitment id if backed by a real quote."""
    m = _ask_json(
        f"PRIVACY POLICY:\n{policy}\n\n"
        f"DATA FLOW: data = {flow['data_fields']}; recipient = {flow['recipient']} "
        f"({flow['recipient_type']}); purpose = {flow['purpose']}\n\n"
        f"QUESTION: {question}\n"
        "If no commitment clearly does, answer NONE. Do not guess.\n"
        'Return JSON: {"commitment": "P1".."Pn" or "NONE", '
        '"quote": "<exact words copied from that commitment, or empty>"}',
        PolicyMatch,
    )
    if m.commitment.strip().upper() == "NONE":
        return ""
    # Trust the quote, not the number: the code finds where the sentence really is.
    return locate_quote(m.quote, items)


def check_policy(flow: dict, policy: str) -> tuple[bool, str, str]:
    """Return (contradicts, reference, explanation). The decision is made in code."""
    items = commitments(policy)
    allows = find_commitment(
        "Which ONE commitment explicitly ANNOUNCES or ALLOWS this data flow "
        "(same kind of data, recipient and purpose)?", flow, policy, items)
    forbids = find_commitment(
        "Which ONE commitment explicitly says this kind of data will NOT be shared "
        "or used this way?", flow, policy, items)
    if transfer_outside_eu(flow) and not re.search(
            r"transfer|outside the eu|outside the european|united states", policy.lower()):
        return True, "", "transfer outside the EU not disclosed in the policy"
    # A quote only counts as a prohibition if it really contains one ("not", "never")
    if forbids and re.search(PROHIBITION, items[forbids].lower()):
        return True, forbids, f"{forbids} says this will not be done"
    if not allows:
        return True, "", "no commitment of the policy announces this flow"
    return False, allows, f"announced in {allows}"


# 4. multi-query retrieval
QUERIES = {
    5: "storage limitation, kept no longer than necessary",
    6: "lawfulness of processing, legal basis",
    7: "conditions for consent, freely given, specific, distinguishable",
    9: "processing of special categories of personal data, data concerning health, explicit consent",
    13: "information to be provided where personal data are collected from the data subject",
    28: "processor acting on behalf of the controller, contract",
    44: "transfer of personal data to third countries",
}


def retrieve(flow: dict, articles: list[int]) -> list[dict]:
    queries = [QUERIES[a] for a in articles if a in QUERIES]
    queries.append(f"{flow['data_fields']} processed for {flow['purpose']}")
    best = {}
    for q in queries:
        for p in search(q, k=3):
            if p["article"] not in best or p["distance"] < best[p["article"]]["distance"]:
                best[p["article"]] = p
    return sorted(best.values(), key=lambda p: p["distance"])


# 5. write-up grounded in passages
def write_up(flow: dict, risk: str, reasons: list[str], passages: list[dict]) -> Writeup:
    legal = "\n\n".join(p["text"][:PASSAGE_CHARS] for p in passages)
    return _ask_json(
        "You are a GDPR auditor writing a finding. The assessment is ALREADY decided; "
        "explain it using ONLY the legal passages below, citing article numbers.\n\n"
        f"LEGAL PASSAGES:\n{legal}\n\n"
        f"DATA FLOW: {flow['data_fields']} -> {flow['recipient']} for {flow['purpose']} "
        f"(consent: {flow['consent']})\n"
        f"RISK: {risk}. REASONS: {'; '.join(reasons)}\n\n"
        'Return JSON: {"justification": "2-3 sentences", "recommendation": "1-2 sentences"}',
        Writeup,
    )


def audit_flow(flow: dict, policy: str) -> FlowResult:
    start = time.time()
    flow = {k: str(v) for k, v in flow.items()}

    special, special_reason = is_special_category(flow["data_fields"])
    opinion = llm_data_opinion(flow["data_fields"])
    contradicts, reference, explanation = check_policy(flow, policy)
    risk, reasons, articles = assess_risk(flow, special, contradicts)

    passages = retrieve(flow, articles)
    retrieved = sorted({p["article"] for p in passages})
    cited = [a for a in articles if a in retrieved]
    misses = [a for a in articles if a not in retrieved]
    relevant = [p for p in passages if p["article"] in cited] or passages[:4]
    writeup = write_up(flow, risk, reasons, relevant)

    return FlowResult(
        flow_id=flow["flow_id"], flow=flow,
        special_category=special, special_reason=special_reason,
        llm_opinion=opinion, needs_human_review=opinion.health_or_sex_life != special,
        contradicts_policy=contradicts,
        policy_reference=reference,
        policy_explanation=explanation,
        risk_level=risk, risk_reasons=reasons,
        cited_articles=cited, retrieval_misses=misses, retrieved_articles=retrieved,
        justification=writeup.justification, recommendation=writeup.recommendation,
        seconds=round(time.time() - start, 1),
    )
