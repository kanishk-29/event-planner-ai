from functools import lru_cache

from llm.gemini import GeminiProvider


@lru_cache(maxsize=1)
def get_provider():
    """One shared provider, so it remembers which models are out of quota."""
    return GeminiProvider()
