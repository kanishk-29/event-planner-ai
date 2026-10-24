import pytest

pytest.importorskip("reportlab")
from datetime import date

from core.models import EventBrief
from export.pdf import build_pdf
from services.planner import build_plan


class Broken:
    def generate(self, *a, **k):
        raise RuntimeError("api down")


def test_pdf_is_valid_and_survives_odd_characters():
    brief = EventBrief(event_type="wedding", event_date=date(2030, 1, 1), guests=100,
                       budget=1_000_000, city="Delhi", vibe="royal ₹ → <b>test</b> & more",
                       traditions=["mehendi", "संगीत"])
    plan = build_plan(brief, Broken())            # template plan, no API needed
    data = build_pdf(plan)
    assert data.startswith(b"%PDF") and len(data) > 2000
