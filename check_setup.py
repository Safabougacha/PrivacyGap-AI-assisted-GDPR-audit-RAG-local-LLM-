"""Step 1 check: libraries, LLM, and local embeddings.

Run:  python check_setup.py
"""
import sys
import time

print(f"Python {sys.version.split()[0]}")

try:
    import chromadb, pydantic, pandas, requests, streamlit  # noqa: F401
    print("OK  libraries installed")
except ImportError as exc:
    sys.exit(f"KO  missing library: {exc.name} -> run: pip install -r requirements.txt")

from src.config import LLM_PROVIDER
from src.llm import LLMError, ask, model_name

# 1) Chat model: one tiny request (local models: first call loads the model, ~10-30 s)
print(f"..  asking {LLM_PROVIDER} / {model_name()} (first call can take ~30 s)")
start = time.time()
try:
    answer = ask("Answer with one word: what does the GDPR protect?")
except LLMError as exc:
    sys.exit(f"KO  {exc}")
print(f"OK  model answered in {time.time() - start:.0f} s: {answer.strip()[:60]}")

# 2) JSON mode, which the audit engine relies on
raw = ask('Return a JSON object with one key "risk" whose value is "high".', json_output=True)
print(f"OK  JSON mode works: {raw.strip()[:60]}")

# 3) Embedding model (local): first run downloads ~80 MB, once
print("..  loading the local embedding model (first time: ~1 min download)")
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

vector = DefaultEmbeddingFunction()(["data concerning health"])[0]
print(f"OK  local embeddings returned a vector of {len(vector)} numbers")

print("\nSetup complete. Ready for step 2.")
