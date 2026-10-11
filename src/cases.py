"""Step 3 - Load and validate the test cases.

Each case folder (data/cases/<name>/) contains:
  policy.md              what the app PROMISES (numbered commitments P1, P2...)
  flows.csv              what the app actually DOES (one row per data flow)
  expected_findings.csv  the ground truth, written BEFORE running the tool

Run:  python -m src.cases      (checks all cases and prints a summary)
"""
import sys

import pandas as pd

from src.config import CASES_DIR

FLOW_COLUMNS = ["flow_id", "event_name", "data_fields", "recipient",
                "recipient_type", "purpose", "consent", "source"]
TRUTH_COLUMNS = ["flow_id", "contradicts_policy", "risk_level",
                 "expected_articles", "rationale"]
ALLOWED = {
    "recipient_type": {"third_party", "processor", "internal"},
    "consent": {"none_specific", "general_terms", "bundled", "opt_in", "explicit"},
    "contradicts_policy": {"yes", "no"},
    "risk_level": {"high", "medium", "low"},
}


def list_cases() -> list[str]:
    return sorted(p.name for p in CASES_DIR.iterdir() if (p / "flows.csv").exists())


def load_case(name: str) -> dict:
    folder = CASES_DIR / name
    return {
        "name": name,
        "policy": (folder / "policy.md").read_text(encoding="utf-8"),
        "flows": pd.read_csv(folder / "flows.csv", dtype=str).fillna(""),
        "truth": pd.read_csv(folder / "expected_findings.csv", dtype=str).fillna(""),
    }


def validate(case: dict) -> list[str]:
    """Data quality checks: columns, unique IDs, allowed values, flows <-> truth."""
    errors = []
    flows, truth = case["flows"], case["truth"]
    for df, cols, label in [(flows, FLOW_COLUMNS, "flows"), (truth, TRUTH_COLUMNS, "truth")]:
        missing = set(cols) - set(df.columns)
        if missing:
            errors.append(f"{label}: missing columns {sorted(missing)}")
            return errors
        if df["flow_id"].duplicated().any():
            errors.append(f"{label}: duplicated flow_id {df.loc[df.flow_id.duplicated(), 'flow_id'].tolist()}")
    for col, allowed in ALLOWED.items():
        df = flows if col in flows.columns else truth
        bad = sorted(set(df[col]) - allowed)
        if bad:
            errors.append(f"{col}: unexpected values {bad} (allowed: {sorted(allowed)})")
    if set(flows.flow_id) != set(truth.flow_id):
        errors.append(f"flows and truth do not cover the same flows: "
                      f"{sorted(set(flows.flow_id) ^ set(truth.flow_id))}")
    for _, row in truth.iterrows():
        if not all(a.strip().isdigit() for a in row.expected_articles.split(";")):
            errors.append(f"{row.flow_id}: expected_articles must look like 9;6;13")
    return errors


if __name__ == "__main__":
    ok = True
    for name in list_cases():
        case = load_case(name)
        errors = validate(case)
        truth = case["truth"]
        print(f"\n{name}: {len(case['flows'])} flows | "
              f"contradictions {sum(truth.contradicts_policy == 'yes')} | "
              f"risk high/medium/low = "
              f"{sum(truth.risk_level == 'high')}/{sum(truth.risk_level == 'medium')}/"
              f"{sum(truth.risk_level == 'low')}")
        for e in errors:
            print("   KO", e)
        ok &= not errors
    print("\nAll cases valid." if ok else "\nFix the errors above.")
    sys.exit(0 if ok else 1)
