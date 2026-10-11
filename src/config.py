"""Central configuration: paths, model names and provider choice.

Every other module imports its settings from here, so changing a model
or a folder only ever happens in one place.
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# Project root = the folder that contains this `src/` package
ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DATA_DIR = ROOT / "data"
LEGAL_DIR = DATA_DIR / "legal"
CASES_DIR = DATA_DIR / "cases"
REPORTS_DIR = ROOT / "reports"
CHROMA_DIR = ROOT / "chroma_db"

# --- LLM provider: "ollama" (local, default) or "gemini" (hosted) ---
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "ollama").lower()

# Local model served by Ollama (https://ollama.com)
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

# Optional hosted model
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemini-2.5-flash")

# --- Embeddings (local, runs on the CPU, no API call) ---
# ChromaDB's built-in model (all-MiniLM-L6-v2): small, fast, English-oriented,
# which is why the legal texts are indexed in their official English version.
EMBED_MODEL = "all-MiniLM-L6-v2 (local, ChromaDB default)"

# Low temperature = stable, reproducible answers (important for an audit tool)
TEMPERATURE = 0.1
# Number of legal passages retrieved for each data flow
TOP_K = 5
