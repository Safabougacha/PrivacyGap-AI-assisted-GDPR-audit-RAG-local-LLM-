"""Debug - show the RAW answers of the model when it reads the privacy policy,
and why the code accepts or rejects them.

Run:  python -m eval.debug_policy control_app CTL-03
      python -m eval.debug_policy flo FLO-11
"""
import json
import sys

from src.auditor import commitments, quote_is_real
from src.cases import load_case
from src.llm import ask
from src.schemas import PolicyMatch

case_name, flow_id = sys.argv[1], sys.argv[2]
case = load_case(case_name)
policy = case["policy"]
flow = case["flows"].set_index("flow_id").loc[flow_id].to_dict()
items = commitments(policy)
print(f"Commitments parsed from the policy: {list(items)}\n")

for question in [
    "Which ONE commitment explicitly ANNOUNCES or ALLOWS this data flow "
    "(same kind of data, recipient and purpose)?",
    "Which ONE commitment explicitly says this kind of data will NOT be shared "
    "or used this way?",
]:
    raw = ask(
        f"PRIVACY POLICY:\n{policy}\n\n"
        f"DATA FLOW: data = {flow['data_fields']}; recipient = {flow['recipient']} "
        f"({flow['recipient_type']}); purpose = {flow['purpose']}\n\n"
        f"QUESTION: {question}\nIf no commitment clearly does, answer NONE. Do not guess.\n"
        'Return JSON: {"commitment": "P1".."Pn" or "NONE", '
        '"quote": "<exact words copied from that commitment, or empty>"}',
        json_output=True,
    )
    print("QUESTION:", question[:60], "...")
    print("RAW ANSWER:", raw)
    try:
        m = PolicyMatch.model_validate(json.loads(raw))
        ref = m.commitment.strip().upper()
        print(f"-> commitment '{ref}' exists: {ref in items} | quote accepted: {quote_is_real(m, items)}")
        if ref in items:
            print(f"   real text of {ref}: {items[ref][:120]}")
    except Exception as exc:
        print("-> invalid answer:", exc)
    print()
