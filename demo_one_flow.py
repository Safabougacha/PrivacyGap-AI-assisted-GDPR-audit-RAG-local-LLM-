"""Demo - audit ONE data flow of Flo, end to end, and show every step.

This is a preview of the audit engine (step 4) on a single example:
  1. CLASSIFY  the data with the LLM (business words -> legal category)
  2. RETRIEVE  the relevant GDPR articles with that legal category (RAG)
  3. JUDGE     the flow against the policy promise, citing retrieved articles
  4. CHECK     that every cited article really was retrieved (anti-hallucination)

Run:  python demo_one_flow.py
"""
import json
import time

from src.llm import ask
from src.retriever import search

# --- The case (from the Flo case study and public court documents) ----------
POLICY_PROMISE = (
    "We will not share information regarding your marked cycles, pregnancy, "
    "symptoms, notes and other information entered by you with third parties."
)
FLOW = {
    "event_name": "R_SELECT_LAST_PERIOD_DATE",
    "data": "date of the user's last menstrual period",
    "recipient": "Meta (Facebook) SDK - third party",
    "purpose": "advertising and analytics",
    "consent": "no specific consent, only general terms of use",
}

print("=" * 70)
print("FLOW :", json.dumps(FLOW, indent=2))
print("PROMISE in the privacy policy:", POLICY_PROMISE)
print("=" * 70)

# --- 1. CLASSIFY --------------------------------------------------------------
t = time.time()
classification = json.loads(ask(
    "You are a GDPR auditor. Classify this data flow.\n"
    f"Flow: {json.dumps(FLOW)}\n"
    'Return JSON: {"personal_data": true/false, "health_data": true/false, '
    '"special_category": true/false, "third_party_recipient": true/false, '
    '"legal_category": "<the GDPR wording for this kind of data>"}',
    json_output=True,
))
print(f"\n[1] CLASSIFY ({time.time() - t:.0f}s)")
print(json.dumps(classification, indent=2))

# --- 2. RETRIEVE --------------------------------------------------------------
# Query rewriting: we search with the LEGAL category, not the raw business words.
query = (f"{classification.get('legal_category', '')} shared with a third party "
         f"for {FLOW['purpose']} without explicit consent")
passages = search(query, k=8)
# Keep the best passage of each article (diversity, not 5x the same article)
best = {}
for p in passages:
    best.setdefault(p["article"], p)
passages = list(best.values())[:5]
print(f"\n[2] RETRIEVE  query = '{query}'")
for p in passages:
    print(f"    Article {p['article']:>2} (distance {p['distance']}) - {p['title']}")

# --- 3. JUDGE -----------------------------------------------------------------
context = "\n\n".join(p["text"] for p in passages)
t = time.time()
verdict = json.loads(ask(
    "You are a GDPR auditor. Use ONLY the legal passages below; do not use outside knowledge.\n\n"
    f"LEGAL PASSAGES:\n{context}\n\n"
    f"PRIVACY POLICY PROMISE: {POLICY_PROMISE}\n"
    f"DATA FLOW: {json.dumps(FLOW)}\n\n"
    'Return JSON: {"contradicts_policy": true/false, '
    '"policy_quote": "<the promise that is broken, or empty>", '
    '"risk_level": "high" | "medium" | "low", '
    '"cited_articles": [<article numbers from the passages above>], '
    '"justification": "<2-3 sentences>", "recommendation": "<1-2 sentences>"}',
    json_output=True,
))
print(f"\n[3] JUDGE ({time.time() - t:.0f}s)")
print(json.dumps(verdict, indent=2))

# --- 4. CHECK -----------------------------------------------------------------
retrieved = {p["article"] for p in passages}
cited = set()
for a in verdict.get("cited_articles", []):
    try:
        cited.add(int(str(a).lower().replace("article", "").strip()))
    except ValueError:
        pass
invented = cited - retrieved
print("\n[4] CHECK citations")
print(f"    cited     : {sorted(cited)}")
print(f"    retrieved : {sorted(retrieved)}")
print("    OK - every cited article comes from the retrieved passages" if not invented
      else f"    WARNING - cited but NOT retrieved (possible hallucination): {sorted(invented)}")
