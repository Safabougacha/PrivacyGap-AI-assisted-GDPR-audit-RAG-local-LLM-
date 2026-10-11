"""Step 6 - Streamlit demo of PrivacyGap.

Run:  streamlit run app.py
Shows the audit results already produced by `python -m src.audit <case>`,
the evaluation scores, and can audit one flow live.
"""
import json

import pandas as pd
import streamlit as st

from eval.evaluate import evaluate_case, score
from src.cases import list_cases, load_case
from src.config import REPORTS_DIR

st.set_page_config(page_title="PrivacyGap", page_icon="🔍", layout="wide")

RISK_ICON = {"high": "🔴 High", "medium": "🟠 Medium", "low": "🟢 Low"}
CASE_LABEL = {
    "flo": "Flo (real case, 2016–2019, reconstructed)",
    "control_app": "ClearCycle (fictional, compliant control case)",
    "trap_app": "StepWell (fictional, subtle trap case)",
}

st.title("🔍 PrivacyGap")
st.markdown(
    "**AI-assisted privacy audit** — compares what an app *promises* in its privacy policy "
    "with what it *does* with your data, and justifies each risk with the GDPR.  \n"
    "Local LLM (Ollama) · RAG on the GDPR (ChromaDB) · auditable rules · evaluated against a "
    "ground truth. *Audit-support tool, not legal advice.*")

case = st.sidebar.selectbox("Case", list_cases(), format_func=lambda c: CASE_LABEL.get(c, c))
data = load_case(case)
results_path = REPORTS_DIR / f"{case}_results.json"

tab_report, tab_flows, tab_policy, tab_eval, tab_live = st.tabs(
    ["📋 Audit report", "🔎 Findings", "📄 Privacy policy", "📊 Evaluation", "⚡ Live audit"])

# ------------------------------------------------------------------ report
with tab_report:
    if not results_path.exists():
        st.info(f"No results yet. Run in a terminal:  `python -m src.audit {case}`")
    else:
        results = json.loads(results_path.read_text(encoding="utf-8"))
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Flows audited", len(results))
        c2.metric("Contradict the policy", sum(r["contradicts_policy"] for r in results))
        c3.metric("High risk", sum(r["risk_level"] == "high" for r in results))
        c4.metric("Need human review", sum(r["needs_human_review"] for r in results))
        st.dataframe(pd.DataFrame([{
            "Flow": r["flow_id"],
            "Data": r["flow"]["data_fields"],
            "Recipient": r["flow"]["recipient"],
            "Purpose": r["flow"]["purpose"],
            "Contradiction": f"Yes ({r['policy_reference']})" if r["contradicts_policy"] else "No",
            "Risk": RISK_ICON[r["risk_level"]],
            "GDPR articles": ", ".join(map(str, r["cited_articles"])),
        } for r in results]), hide_index=True, width="stretch")
        md = REPORTS_DIR / f"{case}_report.md"
        if md.exists():
            st.download_button("⬇️ Download the full report (Markdown)", md.read_bytes(),
                               file_name=md.name)

# ------------------------------------------------------------------ findings
with tab_flows:
    if results_path.exists():
        for r in json.loads(results_path.read_text(encoding="utf-8")):
            with st.expander(f"{RISK_ICON[r['risk_level']]} — {r['flow_id']} · {r['flow']['data_fields']}"):
                f = r["flow"]
                st.markdown(
                    f"**Flow:** {f['data_fields']} → **{f['recipient']}** ({f['recipient_type']})  \n"
                    f"**Purpose:** {f['purpose']} · **Consent:** {f['consent']}  \n"
                    f"**Data type:** {r['special_reason']}"
                    f"{' — ⚠️ LLM disagrees, human review needed' if r['needs_human_review'] else ''}  \n"
                    f"**Privacy policy:** {r['policy_explanation']}  \n"
                    f"**Why this risk level:** {'; '.join(r['risk_reasons'])}")
                st.info(f"**Justification.** {r['justification']}")
                st.success(f"**Recommendation.** {r['recommendation']}")
                st.caption(f"GDPR articles: {', '.join(map(str, r['cited_articles']))} · "
                           f"source of the flow: {f.get('source', '')} · {r['seconds']} s")
    else:
        st.info("Run the audit first.")

# ------------------------------------------------------------------ policy
with tab_policy:
    st.markdown(data["policy"])
    st.subheader("Data flow inventory")
    st.dataframe(data["flows"], hide_index=True, width="stretch")

# ------------------------------------------------------------------ evaluation
with tab_eval:
    cases = [c for c in (evaluate_case(n) for n in list_cases()) if c]
    if not cases:
        st.info("Run the audits, then `python -m eval.evaluate`.")
    else:
        rows = []
        for c in cases + [{"case": "ALL", "rows": [r for c in cases for r in c["rows"]]}]:
            s = score(c["rows"])
            rows.append({"Case": c["case"], "Flows": s["flows"],
                         "Risk level correct": f"{s['risk_accuracy']:.0%}",
                         "Problems found (recall)": f"{s['issue_recall']:.0%}",
                         "Alerts that were right (precision)": f"{s['issue_precision']:.0%}",
                         "Contradiction correct": f"{s['contradiction_accuracy']:.0%}",
                         "GDPR articles found": f"{s['article_recall']:.0%}",
                         "False alerts": s["false_alerts"]})
        st.dataframe(pd.DataFrame(rows), hide_index=True, width="stretch")
        history = REPORTS_DIR / "eval_history.csv"
        if history.exists():
            st.subheader("Experiments: before / after")
            st.dataframe(pd.read_csv(history), hide_index=True, width="stretch")
        st.caption("Ground truth written before running the tool. 26 flows: an indicator, "
                   "not a statistical proof.")

# ------------------------------------------------------------------ live
with tab_live:
    st.markdown("Audit **one flow** now with the local model (about 30 seconds). "
                "Ollama must be running.")
    flow_id = st.selectbox("Flow", data["flows"]["flow_id"].tolist())
    if st.button("Run the audit"):
        from src.auditor import audit_flow
        flow = data["flows"].set_index("flow_id").loc[flow_id].to_dict() | {"flow_id": flow_id}
        with st.spinner("Classifying, reading the policy, searching the GDPR, writing..."):
            try:
                r = audit_flow(flow, data["policy"])
            except Exception as exc:  # e.g. Ollama not running
                st.error(f"Audit failed: {exc}")
                st.stop()
        truth = data["truth"].set_index("flow_id").loc[flow_id]
        st.markdown(f"### {RISK_ICON[r.risk_level]} · contradiction: "
                    f"{'yes (' + r.policy_reference + ')' if r.contradicts_policy else 'no'}")
        st.markdown(f"**Expected (ground truth):** risk {truth.risk_level}, "
                    f"contradiction {truth.contradicts_policy} — *{truth.rationale}*")
        st.info(r.justification)
        st.success(r.recommendation)
        st.caption(f"Articles: {r.cited_articles} · {r.seconds} s")
