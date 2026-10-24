from datetime import date
from core.models import (EventBrief, BudgetSuggestion, BudgetLine, TimelineSuggestion,
                         TaskSuggestion, VendorSuggestion, VendorLine, IdeasSuggestion, DetailsSuggestion)
from services.planner import build_plan
from services.validators import check_plan


class SmartFake:
    """Returns a valid object for whichever schema is asked for."""
    def generate(self, system, user, schema):
        if schema is BudgetSuggestion:
            return BudgetSuggestion(items=[BudgetLine(category="Venue", percent=60),
                                           BudgetLine(category="Food", percent=40)])
        if schema is DetailsSuggestion:
            return DetailsSuggestion(
                tasks=[TaskSuggestion(title="Book venue", weeks_before=10)],
                vendors=[VendorLine(category="Caterer", what_to_ask=["Price?"], est_cost_range="INR 30,000")],
                ideas=["Photo wall"])
        if schema is TimelineSuggestion:
            return TimelineSuggestion(tasks=[TaskSuggestion(title="Book venue", weeks_before=10)])
        if schema is VendorSuggestion:
            return VendorSuggestion(vendors=[VendorLine(category="Caterer", what_to_ask=["Price?"], est_cost_range="30%")])
        return IdeasSuggestion(ideas=["Photo wall"])


class Broken:
    def generate(self, *a, **k):
        raise RuntimeError("api down")


BRIEF = EventBrief(event_type="birthday", event_date=date(2030, 1, 1), guests=50,
                   budget=100000, city="Lucknow")


def test_full_plan_ai():
    plan = build_plan(BRIEF, SmartFake())
    assert set(plan.sources.values()) == {"ai"}
    assert sum(i.amount for i in plan.budget) == BRIEF.budget
    assert plan.timeline[0].due_date is not None


def test_full_plan_all_fallbacks():
    plan = build_plan(BRIEF, Broken())
    assert set(plan.sources.values()) == {"template"}
    assert len(plan.vendors) > 0 and len(plan.ideas) > 0


def test_validator_flags_tight_budget():
    brief = BRIEF.model_copy(update={"budget": 10000})
    plan = build_plan(brief, Broken())
    assert any("per guest" in w for w in check_plan(plan))


class Recorder(SmartFake):
    def __init__(self):
        self.calls = {}

    def generate(self, system, user, schema):
        self.calls[schema.__name__] = user
        return super().generate(system, user, schema)


def test_other_sections_see_the_budget():
    r = Recorder()
    build_plan(BRIEF, r)
    for name in ("DetailsSuggestion",):
        assert "Budget allocation" in r.calls[name]
    assert "Budget allocation" not in r.calls["BudgetSuggestion"]


def test_error_reason_is_recorded():
    import services.planner as planner
    build_plan(BRIEF, Broken())
    assert "api down" in planner.LAST_ERROR["msg"]


class PartialDetails:
    """Budget works; the details call returns tasks but no ideas."""
    def generate(self, system, user, schema):
        if schema is DetailsSuggestion:
            return DetailsSuggestion(
                tasks=[TaskSuggestion(title="Book venue", weeks_before=10)],
                vendors=[VendorLine(category="Caterer", what_to_ask=["Price?"], est_cost_range="INR 30,000")],
                ideas=[])
        return SmartFake().generate(system, user, schema)


def test_each_section_falls_back_on_its_own():
    plan = build_plan(BRIEF, PartialDetails())
    assert plan.sources["timeline"] == "ai" and plan.sources["vendors"] == "ai"
    assert plan.sources["ideas"] == "template" and len(plan.ideas) > 0


class DailyQuota:
    def __init__(self):
        self.n = 0

    def generate(self, *a, **k):
        self.n += 1
        raise RuntimeError("429 RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")


def test_daily_quota_is_not_retried():
    import services.planner as planner
    p = DailyQuota()
    plan = build_plan(BRIEF, p)
    assert p.n == 2                                  # one call for budget, one for details, no retries
    assert set(plan.sources.values()) == {"template"}
    assert "quota" in planner.LAST_ERROR["msg"].lower()
