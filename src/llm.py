"""The ONLY module that talks to the LLM.

Everything else calls `ask()`. Two providers are supported:
  - "ollama" (default): a small open model running locally, on the CPU.
    No account, no API key, no cost, and no data leaves the machine.
  - "gemini": Google's hosted API (needs GEMINI_API_KEY).
Switching provider = one line in .env (LLM_PROVIDER=...).
"""
import time

import requests

from src.config import (CHAT_MODEL, GEMINI_API_KEY, LLM_PROVIDER, OLLAMA_MODEL,
                        OLLAMA_URL, TEMPERATURE)


class LLMError(RuntimeError):
    """Raised with a human-readable message when the model cannot answer."""


def _ask_ollama(prompt: str, system: str | None, json_output: bool) -> str:
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    messages.append({"role": "user", "content": prompt})
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "stream": False,
        # num_ctx: room for the prompt (policy + legal passages). Ollama's default
        # window is small and would silently cut the beginning of long prompts.
        "options": {"temperature": TEMPERATURE, "num_ctx": 8192},
    }
    if json_output:
        payload["format"] = "json"  # Ollama constrains the output to valid JSON
    try:
        r = requests.post(f"{OLLAMA_URL}/api/chat", json=payload, timeout=300)
    except requests.ConnectionError:
        raise LLMError("Ollama is not running. Open the Ollama app, then retry.")
    if r.status_code == 404:
        raise LLMError(f"Model '{OLLAMA_MODEL}' not found. Run: ollama pull {OLLAMA_MODEL}")
    r.raise_for_status()
    return r.json()["message"]["content"]


def _ask_gemini(prompt: str, system: str | None, json_output: bool,
                max_retries: int = 5) -> str:
    from google import genai
    from google.genai import errors, types

    if not GEMINI_API_KEY:
        raise LLMError("GEMINI_API_KEY is missing in .env")
    client = genai.Client(api_key=GEMINI_API_KEY)
    config = types.GenerateContentConfig(
        temperature=TEMPERATURE,
        system_instruction=system,
        response_mime_type="application/json" if json_output else None,
    )
    wait = 2
    for attempt in range(1, max_retries + 1):
        try:
            resp = client.models.generate_content(model=CHAT_MODEL, contents=prompt, config=config)
            return resp.text or ""
        except errors.APIError as exc:
            # 429 = rate limit, 5xx = temporary server error -> wait and retry
            retryable = exc.code == 429 or (exc.code or 0) >= 500
            if not retryable or attempt == max_retries:
                raise LLMError(f"Gemini HTTP {exc.code}: {exc.message}")
            print(f"  API busy (HTTP {exc.code}), retry {attempt} in {wait}s...")
            time.sleep(wait)
            wait *= 2  # exponential backoff: 2s, 4s, 8s, 16s
    return ""


def ask(prompt: str, system: str | None = None, json_output: bool = False) -> str:
    """Send a prompt to the configured model and return its text answer."""
    if LLM_PROVIDER == "gemini":
        return _ask_gemini(prompt, system, json_output)
    return _ask_ollama(prompt, system, json_output)


def model_name() -> str:
    return CHAT_MODEL if LLM_PROVIDER == "gemini" else OLLAMA_MODEL
