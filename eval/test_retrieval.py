"""Step 2 check - does the search find the right GDPR article?

A first mini-evaluation: for each question we know which article(s) a
lawyer would expect. We measure "hit@5": is at least one expected
article among the 5 retrieved passages?

Run:  python -m eval.test_retrieval
"""
from src.retriever import search

TESTS = [
    ("The app shares menstrual cycle dates and pregnancy status with advertisers",
     {9}),
    ("special categories of personal data such as data concerning health", {9}),
    ("conditions for valid consent, freely given and specific", {7, 4}),
    ("information to provide to users when collecting their personal data", {13, 12}),
    ("third-party SDK that processes data on behalf of the app (processor contract)", {28}),
    ("data protection impact assessment for high-risk processing", {35}),
    ("data protection by design and by default", {25}),
    ("how long personal data can be kept, storage limitation", {5}),
    ("transfer of personal data to a country outside the EU", {44, 45, 46}),
    ("administrative fines for infringements", {83}),
]

hits = 0
for question, expected in TESTS:
    results = search(question, k=5)
    found = [r["article"] for r in results]
    ok = bool(expected & set(found))
    hits += ok
    print(f"{'OK ' if ok else 'KO '} expected {sorted(expected)} -> got {found}  | {question[:60]}")

print(f"\nhit@5 = {hits}/{len(TESTS)} ({hits / len(TESTS):.0%})")
