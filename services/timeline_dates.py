"""Deterministic date math. The LLM says 'weeks before'; this makes real dates."""
from datetime import date, timedelta
from core.models import Task


def assign_dates(tasks: list[Task], event_date: date, today: date | None = None) -> list[Task]:
    """Fill due_date, clamp past dates to today, sort chronologically."""
    today = today or date.today()
    for t in tasks:
        due = event_date - timedelta(weeks=max(t.weeks_before, 0))
        t.due_date = max(due, today)         # never schedule in the past
    return sorted(tasks, key=lambda t: t.due_date)


def weeks_available(event_date: date, today: date | None = None) -> int:
    today = today or date.today()
    return max((event_date - today).days // 7, 0)
