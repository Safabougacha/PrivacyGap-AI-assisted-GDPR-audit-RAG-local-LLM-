"""Step 4 - Deterministic audit rules (the written audit methodology).

Why rules and not the LLM?  A first version let a small local model decide
everything: it rated every flow "high" (it copied examples from its prompt).
Decisions on STRUCTURED inventory fields are now taken by explicit,
auditable rules; the LLM is kept for what needs language understanding
(reading the privacy policy, writing the justification).
"""
import re

# --- Is the data a GDPR special category (art. 9)? ----------------------------
HEALTH_TERMS = r"menstrua|period|cycle|pregnan|symptom|cramp|pms|fatigue|heart rate|sleep|health|medical|diagnos|ovulat|fertil"
SEX_TERMS = r"sexual|sex life|sex activity"
NEGATION = r"\bno (?:health|sensitive) data\b"


def is_special_category(data_fields: str) -> tuple[bool, str]:
    """Return (special?, reason). Explicit negations like '(no health data)' win."""
    text = re.sub(NEGATION, "", data_fields.lower())
    if re.search(SEX_TERMS, text):
        return True, "sex life data"
    m = re.search(HEALTH_TERMS, text)
    if m:
        return True, f"health data (keyword: '{m.group()}')"
    return False, "not a special category"


# --- Is the purpose the service the user asked for, or a secondary use? -------
SECONDARY_TERMS = r"advertis|marketing|retarget|tracking|attribution|analytics|offers|insurance|profil|newsletter|sell"


def is_secondary_purpose(purpose: str) -> bool:
    return re.search(SECONDARY_TERMS, purpose.lower()) is not None


# --- Other red flags ----------------------------------------------------------
def undefined_retention(flow: dict) -> bool:
    text = " ".join(flow.values()).lower()
    return "as long as necessary" in text or "no defined period" in text


def transfer_outside_eu(flow: dict) -> bool:
    text = " ".join(flow.values()).lower()
    return any(w in text for w in ("united states", "outside the eu", "outside the european"))


# --- The risk grid -----------------------------------------------------------
def assess_risk(flow: dict, special: bool, contradicts: bool) -> tuple[str, list[str], list[int]]:
    """Apply the audit grid. Returns (risk_level, reasons, articles concerned)."""
    consent = flow["consent"]
    explicit = consent == "explicit"
    valid_opt_in = consent in {"explicit", "opt_in"}
    third_party = flow["recipient_type"] == "third_party"
    secondary = is_secondary_purpose(flow["purpose"])
    reasons, articles = [], {6}  # art. 6: every processing needs a legal basis

    if special or consent == "opt_in":
        articles.add(7)  # art. 7: conditions for consent (met or not)
    if special:
        articles.add(9)
    if flow["recipient_type"] == "processor":
        articles.add(28)
    if contradicts:
        articles.add(13)

    # HIGH: sensitive data to a third party or for a secondary purpose, no explicit consent
    if special and not explicit and (third_party or secondary):
        reasons.append("special-category data shared with a third party or used for a "
                       "secondary purpose without explicit consent")
        return "high", reasons, sorted(articles)

    medium = []
    if special and not explicit:
        medium.append("special-category data processed without explicit consent")
    if not special and secondary and not valid_opt_in:
        medium.append("secondary use (marketing, tracking or analytics) without a valid opt-in")
    if not special and contradicts:
        medium.append("the flow goes beyond what the privacy policy announces")
    if transfer_outside_eu(flow):
        medium.append("transfer outside the EU")
        articles.update({44, 13})
    if undefined_retention(flow):
        medium.append("no defined retention period")
        articles.update({5, 13})
    if medium:
        return "medium", medium, sorted(articles)

    return "low", ["use disclosed, valid legal basis or consent, processors under contract"], sorted(articles)
