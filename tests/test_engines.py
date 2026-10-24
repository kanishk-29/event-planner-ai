from datetime import date
from core.models import BudgetLine, Task
from services.budget_calc import build_budget
from services.timeline_dates import assign_dates
from services.planner import generate_budget
from core.models import EventBrief, BudgetSuggestion


def test_budget_sums_exactly():
    lines = [BudgetLine(category="A", percent=33.3), BudgetLine(category="B", percent=33.3),
             BudgetLine(category="C", percent=33.3)]
    items = build_budget(lines, 1_000_000)
    assert sum(i.amount for i in items) == 1_000_000


def test_budget_normalizes_bad_percentages():
    lines = [BudgetLine(category="A", percent=60), BudgetLine(category="B", percent=90)]
    items = build_budget(lines, 100_000)       # LLM said 150%, we fix it
    assert sum(i.amount for i in items) == 100_000
    assert round(sum(i.percent for i in items)) == 100


def test_budget_drops_zero_lines():
    lines = [BudgetLine(category="A", percent=100), BudgetLine(category="B", percent=0)]
    assert len(build_budget(lines, 500)) == 1


def test_timeline_dates_and_sorting():
    tasks = [Task(title="late", weeks_before=1), Task(title="early", weeks_before=12)]
    out = assign_dates(tasks, date(2026, 12, 20), today=date(2026, 10, 23))
    assert [t.title for t in out] == ["early", "late"]
    assert out[0].due_date == date(2026, 9, 27) or out[0].due_date >= date(2026, 10, 23)


def test_timeline_never_in_past():
    tasks = [Task(title="x", weeks_before=20)]
    out = assign_dates(tasks, date(2026, 11, 20), today=date(2026, 10, 23))
    assert out[0].due_date == date(2026, 10, 23)


class BrokenProvider:
    def generate(self, *a, **k):
        raise ValueError("bad json")


class FakeProvider:
    def generate(self, system, user, schema):
        from core.models import BudgetLine
        return BudgetSuggestion(items=[BudgetLine(category="Venue", percent=50),
                                       BudgetLine(category="Food", percent=50)])


BRIEF = EventBrief(event_type="wedding", event_date=date(2026, 12, 20), guests=200,
                   budget=1_500_000, city="Lucknow")


def test_fallback_when_llm_fails():
    items, source = generate_budget(BRIEF, BrokenProvider())
    assert source == "template"
    assert sum(i.amount for i in items) == BRIEF.budget


def test_ai_path():
    items, source = generate_budget(BRIEF, FakeProvider())
    assert source == "ai"
    assert sum(i.amount for i in items) == BRIEF.budget
