"""Step 5 - Compare the audit results with the ground truth.

Reads reports/<case>_results.json (produced by `python -m src.audit <case>`)
and data/cases/<case>/expected_findings.csv (written before running the tool).

Run:
  python -m eval.evaluate                    # evaluate every audited case
  python -m eval.evaluate --label baseline   # also record the scores in history
Outputs:
  reports/evaluation.md       readable scoreboard (for the README)
  reports/eval_history.csv    one line per labelled run -> compare before/after
"""
import argparse
import csv
import json
from datetime import datetime

from src.cases import list_cases, load_case
from src.config import REPORTS_DIR

LEVELS = ["low", "medium", "high"]


def ratio(num: int, den: int) -> str:
    return f"{num}/{den} ({num / den:.0%})" if den else "n/a"


def prf(tp: int, fp: int, fn: int) -> tuple[float, float]:
    precision = tp / (tp + fp) if tp + fp else 1.0
    recall = tp / (tp + fn) if tp + fn else 1.0
    return precision, recall


def evaluate_case(case: str) -> dict | None:
    path = REPORTS_DIR / f"{case}_results.json"
    if not path.exists():
        return None
    results = {r["flow_id"]: r for r in json.loads(path.read_text(encoding="utf-8"))}
    truth = load_case(case)["truth"].set_index("flow_id")
    rows = []
    for fid, r in results.items():
        t = truth.loc[fid]
        expected = {int(a) for a in t.expected_articles.split(";")}
        cited = set(r["cited_articles"])
        rows.append({
            "flow_id": fid,
            "risk_pred": r["risk_level"], "risk_true": t.risk_level,
            "contra_pred": r["contradicts_policy"], "contra_true": t.contradicts_policy == "yes",
            "expected": expected, "cited": cited,
            "review": r["needs_human_review"],
        })
    return {"case": case, "rows": rows}


def score(rows: list[dict]) -> dict:
    n = len(rows)
    risk_ok = sum(r["risk_pred"] == r["risk_true"] for r in rows)
    contra_ok = sum(r["contra_pred"] == r["contra_true"] for r in rows)
    # "issue" = any risk above low: does the tool find the problems without crying wolf?
    tp = sum(r["risk_true"] != "low" and r["risk_pred"] != "low" for r in rows)
    fp = sum(r["risk_true"] == "low" and r["risk_pred"] != "low" for r in rows)
    fn = sum(r["risk_true"] != "low" and r["risk_pred"] == "low" for r in rows)
    issue_p, issue_r = prf(tp, fp, fn)
    ctp = sum(r["contra_pred"] and r["contra_true"] for r in rows)
    cfp = sum(r["contra_pred"] and not r["contra_true"] for r in rows)
    cfn = sum(not r["contra_pred"] and r["contra_true"] for r in rows)
    contra_p, contra_r = prf(ctp, cfp, cfn)
    art_found = sum(len(r["expected"] & r["cited"]) for r in rows)
    art_expected = sum(len(r["expected"]) for r in rows)
    art_cited = sum(len(r["cited"]) for r in rows)
    return {
        "flows": n,
        "risk_accuracy": risk_ok / n,
        "issue_precision": issue_p, "issue_recall": issue_r,
        "false_alerts": fp,
        "contradiction_accuracy": contra_ok / n,
        "contradiction_precision": contra_p, "contradiction_recall": contra_r,
        "article_recall": art_found / art_expected if art_expected else 1.0,
        "article_precision": art_found / art_cited if art_cited else 1.0,
        "human_review": sum(r["review"] for r in rows),
        "_risk_ok": risk_ok, "_contra_ok": contra_ok,
    }


def confusion(rows: list[dict]) -> list[str]:
    lines = ["| truth \\ predicted | low | medium | high |", "| --- | --- | --- | --- |"]
    for t in LEVELS:
        cells = [str(sum(r["risk_true"] == t and r["risk_pred"] == p for r in rows)) for p in LEVELS]
        lines.append(f"| **{t}** | " + " | ".join(cells) + " |")
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", help="name of this run, saved in eval_history.csv")
    args = parser.parse_args()

    cases = [c for c in (evaluate_case(name) for name in list_cases()) if c]
    if not cases:
        raise SystemExit("No results found. Run first: python -m src.audit flo")
    all_rows = [r for c in cases for r in c["rows"]]

    md = ["# Evaluation", "", f"*{datetime.now():%Y-%m-%d %H:%M}*", "",
          "| Case | Flows | Risk level correct | Issues found (recall) | Alerts that were right (precision) "
          "| Contradiction correct | GDPR articles found |",
          "| --- | --- | --- | --- | --- | --- | --- |"]
    print(f"\n{'case':<12} {'flows':>5}  {'risk ok':>9}  {'issue R':>7}  {'issue P':>7}  "
          f"{'contra ok':>9}  {'contra P':>8}  {'art R':>6}")
    for c in cases + [{"case": "ALL", "rows": all_rows}]:
        s = score(c["rows"])
        print(f"{c['case']:<12} {s['flows']:>5}  {s['risk_accuracy']:>9.0%}  {s['issue_recall']:>7.0%}  "
              f"{s['issue_precision']:>7.0%}  {s['contradiction_accuracy']:>9.0%}  "
              f"{s['contradiction_precision']:>8.0%}  {s['article_recall']:>6.0%}")
        md.append(f"| **{c['case']}** | {s['flows']} | {ratio(s['_risk_ok'], s['flows'])} | "
                  f"{s['issue_recall']:.0%} | {s['issue_precision']:.0%} | "
                  f"{ratio(s['_contra_ok'], s['flows'])} | {s['article_recall']:.0%} |")

    total = score(all_rows)
    md += ["", "## Risk level: truth vs prediction (all cases)", ""] + confusion(all_rows)
    md += ["", "## Errors to review", "",
           "| Flow | Risk (truth → predicted) | Contradiction (truth → predicted) | Missing articles |",
           "| --- | --- | --- | --- |"]
    for r in all_rows:
        wrong_risk = r["risk_pred"] != r["risk_true"]
        wrong_contra = r["contra_pred"] != r["contra_true"]
        missing = sorted(r["expected"] - r["cited"])
        if wrong_risk or wrong_contra or missing:
            md.append(f"| {r['flow_id']} | {r['risk_true']} → {r['risk_pred']}{' ❌' if wrong_risk else ''} | "
                      f"{'yes' if r['contra_true'] else 'no'} → {'yes' if r['contra_pred'] else 'no'}"
                      f"{' ❌' if wrong_contra else ''} | {', '.join(map(str, missing)) or '—'} |")
    md += ["", "**How to read it.** *Recall*: share of real problems the tool found. "
           "*Precision*: share of the tool's alerts that were right. "
           "In compliance, recall matters most (a missed risk costs more than a false alert), "
           "but low precision makes the report unusable."]

    REPORTS_DIR.mkdir(exist_ok=True)
    (REPORTS_DIR / "evaluation.md").write_text("\n".join(md), encoding="utf-8")
    print(f"\nFalse alerts (risk above 'low' on a compliant flow): {total['false_alerts']}")
    print(f"Flows flagged for human review: {total['human_review']}")
    print(f"Article precision (cited articles that were expected): {total['article_precision']:.0%}")
    print(f"\nScoreboard written to {REPORTS_DIR / 'evaluation.md'}")

    if args.label:
        history = REPORTS_DIR / "eval_history.csv"
        new = not history.exists()
        keys = ["risk_accuracy", "issue_recall", "issue_precision", "contradiction_accuracy",
                "contradiction_precision", "article_recall", "false_alerts"]
        with history.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if new:
                w.writerow(["date", "label", "cases", "flows"] + keys)
            w.writerow([f"{datetime.now():%Y-%m-%d %H:%M}", args.label,
                        "+".join(c["case"] for c in cases), total["flows"]]
                       + [round(total[k], 3) if isinstance(total[k], float) else total[k] for k in keys])
        print(f"Run '{args.label}' added to {history}")


if __name__ == "__main__":
    main()
