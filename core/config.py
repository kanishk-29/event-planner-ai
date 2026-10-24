"""Central config. Reads from .env so keys never live in code."""
import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
# Models are tried in order. Free-tier quota is per model, so a list multiplies your daily allowance.
_raw = os.getenv("GEMINI_MODELS") or os.getenv("GEMINI_MODEL") or "gemini-3.8-flash,gemini-3.6-flash,gemini-3.5-flash-lite"
GEMINI_MODELS = [m.strip() for m in _raw.split(",") if m.strip()]
GEMINI_MODEL = GEMINI_MODELS[0]
