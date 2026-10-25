"""Gemini adapter (free tier) with a model fallback chain and fail-fast networking.

Free-tier quota is counted per model, per day. If a model is out of quota (429), missing (404),
overloaded (503) or too slow (timeout), we move on to the next model in GEMINI_MODELS.
"""
import time

from google import genai
from google.genai import types

from core import config

TIMEOUT_MS = 75_000
# Errors where trying another model may help.
MOVE_ON = ("429", "404", "NOT_FOUND", "503", "504", "UNAVAILABLE", "DEADLINE", "INTERNAL",
           "timed out", "Timeout", "timeout")


def _http_options():
    """Fail fast. A hung or silently retrying request is worse than a quick fallback."""
    try:
        return types.HttpOptions(timeout=TIMEOUT_MS, retry_options=types.HttpRetryOptions(attempts=1))
    except Exception:                       # older SDK without retry_options
        return types.HttpOptions(timeout=TIMEOUT_MS)


class GeminiProvider:
    def __init__(self, api_key: str | None = None, models: list[str] | None = None):
        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY missing. Copy .env.example to .env and add it.")
        self.client = genai.Client(api_key=key, http_options=_http_options())
        self.models = models or config.GEMINI_MODELS
        self.exhausted: dict[str, float] = {}      # model -> time its daily quota ran out
        self.last_model = ""

    def _call(self, model, system, user, schema):
        resp = self.client.models.generate_content(
            model=model,
            contents=user,
            config=types.GenerateContentConfig(
                system_instruction=system,
                response_mime_type="application/json",
                response_schema=schema,
                temperature=0.7,
            ),
        )
        return schema.model_validate_json(resp.text)

    def generate(self, system, user, schema):
        last = None
        for model in self.models:
            if time.time() - self.exhausted.get(model, 0) < 3600:   # skip models known to be spent
                continue
            t0 = time.time()
            try:
                out = self._call(model, system, user, schema)
                self.last_model = model
                print(f"[Gemini] {model} ok in {time.time() - t0:.1f}s")
                return out
            except Exception as e:
                text = str(e)
                print(f"[Gemini] {model} failed after {time.time() - t0:.1f}s: {text[:90]}")
                if not any(k in text for k in MOVE_ON):
                    raise                                           # bad key, bad JSON, etc.
                if "PerDay" in text:
                    self.exhausted[model] = time.time()
                last = e
        raise last or RuntimeError(
            "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDay quota used up on every configured model")
