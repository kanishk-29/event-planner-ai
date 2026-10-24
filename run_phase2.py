"""Phase 2 check: real Gemini call -> validated budget. Run: python run_phase2.py"""
from datetime import date
from core.models import EventBrief
from llm import get_provider
from services.planner import generate_budget

brief = EventBrief(event_type="wedding", event_date=date(2027, 2, 14), guests=250,
                   budget=1_500_000, city="Lucknow", vibe="royal",
                   traditions=["mehendi", "sangeet"])

items, source = generate_budget(brief, get_provider())
print(f"Source: {source}\n")
for i in items:
    print(f"{i.category:28} {i.percent:5.1f}%  Rs {i.amount:>9,}   {i.note}")
print(f"\nTotal: Rs {sum(i.amount for i in items):,}")
