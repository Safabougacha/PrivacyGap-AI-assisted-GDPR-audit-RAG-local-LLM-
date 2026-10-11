"""Step 4 - Run the audit on one case and write the report.

Run:
  python -m src.audit flo                 # all flows of the Flo case
  python -m src.audit flo --limit 2       # quick test on the first 2 flows
  python -m src.audit trap_app --flow TRP-02
Outputs (in reports/):
  <case>_report.md     the human-readable audit report
  <case>_results.json  the raw results, used by the evaluation (step 5)
"""
import argparse
import json
import time

from src.auditor import audit_flow
from src.cases import list_cases, load_case
from src.config import REPORTS_DIR
from src.llm import model_name
from src.report import to_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description="PrivacyGap audit")
    parser.add_argument("case", choices=list_cases())
    parser.add_argument("--limit", type=int, help="audit only the first N flows")
    parser.add_argument("--flow", help="audit a single flow id, e.g. FLO-01")
    args = parser.parse_args()

    case = load_case(args.case)
    flows = case["flows"].to_dict(orient="records")
    if args.flow:
        flows = [f for f in flows if f["flow_id"] == args.flow]
    if args.limit:
        flows = flows[:args.limit]

    print(f"Auditing {len(flows)} flow(s) of '{args.case}' with {model_name()}...\n")
    results, start = [], time.time()
    for i, flow in enumerate(flows, 1):
        r = audit_flow(flow, case["policy"])
        results.append(r)
        flag = "  [human review: LLM disagrees on data type]" if r.needs_human_review else ""
        print(f"[{i}/{len(flows)}] {r.flow_id}: risk={r.risk_level:<6} "
              f"contradiction={'yes' if r.contradicts_policy else 'no ':<3} "
              f"articles={r.cited_articles}  ({r.seconds}s){flag}")

    REPORTS_DIR.mkdir(exist_ok=True)
    md = REPORTS_DIR / f"{args.case}_report.md"
    js = REPORTS_DIR / f"{args.case}_results.json"
    md.write_text(to_markdown(args.case, results, model_name()), encoding="utf-8")
    js.write_text(json.dumps([r.model_dump() for r in results], indent=2, ensure_ascii=False),
                  encoding="utf-8")
    print(f"\nDone in {time.time() - start:.0f}s")
    print(f"Report : {md}")
    print(f"Results: {js}")


if __name__ == "__main__":
    main()
