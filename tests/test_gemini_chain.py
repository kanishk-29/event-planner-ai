import pytest

pytest.importorskip("google.genai")
from llm.gemini import GeminiProvider


def test_model_fallback_chain():
    prov = GeminiProvider.__new__(GeminiProvider)      # skip the real client
    prov.models = ["a", "b"]
    prov.exhausted = {}
    calls = []

    def fake_call(model, system, user, schema):
        calls.append(model)
        if model == "a":
            raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel")
        return "ok"

    prov._call = fake_call
    assert prov.generate("s", "u", None) == "ok"
    assert calls == ["a", "b"]
    prov.generate("s", "u", None)
    assert calls == ["a", "b", "b"]                    # 'a' is remembered as spent


def test_real_errors_are_not_swallowed():
    prov = GeminiProvider.__new__(GeminiProvider)
    prov.models = ["a", "b"]
    prov.exhausted = {}

    def bad_key(model, system, user, schema):
        raise RuntimeError("400 API key not valid")

    prov._call = bad_key
    with pytest.raises(RuntimeError):
        prov.generate("s", "u", None)
