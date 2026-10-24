"""Gemini adapter (free tier) with a model fallback chain.

Free-tier quota is counted per model, per day. If one model is out of quota (429) or
missing (404), we move on to the next one in GEMINI_MODELS.
"""
import time

from google import genai
from google.genai import types

from core import config

MOVE_ON = ("429", "404", "NOT_FOUND", "503", "UNAVAILABLE")   # errors where another model may work


class GeminiProvider:
    def __init__(self, api_key: str | None = None, models: list[str] | None = None):
        key = api_key or config.GEMINI_API_KEY
        if not key:
            raise RuntimeError("GEMINI_API_KEY missing. Copy .env.example to .env and add it.")
        self.client = genai.Client(api_key=key)
        self.models = models or config.GEMINI_MODELS
        self.exhausted: dict[str, float] = {}      # model -> time its daily quota ran out

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
            try:
                return self._call(model, system, user, schema)
            except Exception as e:
                text = str(e)
                if not any(k in text for k in MOVE_ON):
                    raise                                           # bad key, bad JSON, etc.
                if "PerDay" in text:
                    self.exhausted[model] = time.time()
                last = e
        raise last or RuntimeError(
            "429 RESOURCE_EXHAUSTED: GenerateRequestsPerDay quota used up on every configured model")
