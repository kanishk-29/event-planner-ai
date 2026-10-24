"""Sanity checks on a finished plan. Returns human-readable warnings."""
from core.models import Plan
from services.timeline_dates import weeks_available


def check_plan(plan: Plan) -> list[str]:
    warnings = []
    b = plan.brief
    for item in plan.budget:
        if item.percent > 45 and "contingency" not in item.category.lower():
            warnings.append(f"{item.category} takes {item.percent:.0f}% of the budget. That is very high.")
    if b.budget / b.guests < 500:
        warnings.append(f"Rs {b.budget // b.guests} per guest is tight. Expect to cut scope.")
    if weeks_available(b.event_date) < 4:
        warnings.append("Less than 4 weeks to the event. Book venue and caterer immediately.")
    if not any("contingency" in i.category.lower() for i in plan.budget):
        warnings.append("No contingency line. Keep 5 to 10% aside for surprises.")
    return warnings
