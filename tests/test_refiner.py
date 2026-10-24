from datetime import date
from core.models import (EventBrief, PlanPatch, BudgetLine, BudgetChange, TaskSuggestion, VendorLine)
from services.planner import build_plan
from services.refiner import refine, apply_patch
from storage import db


class Broken:
    def generate(self, *a, **k):
        raise RuntimeError("api down")


class PatchFake:
    def __init__(self, patch):
        self.patch = patch

    def generate(self, system, user, schema):
        return self.patch


BRIEF = EventBrief(event_type="wedding", event_date=date(2030, 1, 1), guests=100,
                   budget=1_000_000, city="Delhi")


def base_plan():
    return build_plan(BRIEF, Broken())      # template plan, no API needed


def test_cheaper_scales_budget_and_sums():
    plan = base_plan()
    new, changes, _ = refine(plan, "cheaper", PatchFake(PlanPatch(reply="ok", new_budget_total=800_000)))
    assert new.brief.budget == 800_000
    assert sum(i.amount for i in new.budget) == 800_000
    assert new.version == plan.version + 1
    assert any("Total budget" in c for c in changes)
    assert plan.brief.budget == 1_000_000            # original untouched


def test_add_mehendi_function():
    patch = PlanPatch(reply="added", add_traditions=["mehendi"],
                      add_budget_lines=[BudgetLine(category="Mehendi", percent=4)],
                      add_tasks=[TaskSuggestion(title="Book mehendi artist", weeks_before=6)],
                      add_vendors=[VendorLine(category="Mehendi artist", what_to_ask=["Rate?"], est_cost_range="3%")])
    new, changes, _ = refine(base_plan(), "add mehendi", PatchFake(patch))
    assert "Mehendi" in [i.category for i in new.budget]
    assert sum(i.amount for i in new.budget) == BRIEF.budget
    assert any(t.title == "Book mehendi artist" and t.due_date for t in new.timeline)
    assert "mehendi" in new.brief.traditions


def test_unrealistic_total_is_ignored():
    new, changes, _ = refine(base_plan(), "x", PatchFake(PlanPatch(new_budget_total=50_000_000)))
    assert new.brief.budget == BRIEF.budget
    assert any("Ignored" in c for c in changes)


def test_shift_money_between_categories():
    patch = PlanPatch(budget_changes=[BudgetChange(category="Catering", new_percent=45)])
    new, _, _ = refine(base_plan(), "more catering", PatchFake(patch))
    cat = next(i for i in new.budget if i.category == "Catering")
    assert cat.percent > 30
    assert sum(i.amount for i in new.budget) == BRIEF.budget


def test_cannot_remove_contingency():
    patch = PlanPatch(remove_budget_categories=["Contingency"])
    new, _, _ = refine(base_plan(), "drop it", PatchFake(patch))
    assert any("contingency" in i.category.lower() for i in new.budget)


def test_question_changes_nothing():
    plan = base_plan()
    new, changes, reply = refine(plan, "what is a baraat?", PatchFake(PlanPatch(reply="A groom's procession.")))
    assert changes == [] and new.version == plan.version and reply.startswith("A groom")


def test_llm_failure_keeps_plan():
    plan = base_plan()
    new, changes, reply = refine(plan, "anything", Broken())
    assert new == plan and changes == [] and "couldn't" in reply


def test_storage_roundtrip(tmp_path):
    path = tmp_path / "t.db"
    db.init_db(path)
    plan = base_plan()
    pid = db.save_plan(plan, "My wedding", path=path)
    assert db.list_plans(path)[0][1] == "My wedding"
    plan.timeline[0].done = True
    db.save_plan(plan, plan_id=pid, path=path)
    loaded = db.load_plan(pid, path)
    assert loaded.timeline[0].done is True and loaded.brief.budget == BRIEF.budget
    db.delete_plan(pid, path)
    assert db.list_plans(path) == []


def test_vendor_without_numbers_gets_placeholder():
    patch = PlanPatch(add_vendors=[VendorLine(category="Magician", what_to_ask=["Rate?"],
                                              est_cost_range="Standard rate")])
    new, _, _ = refine(base_plan(), "x", PatchFake(patch))
    v = next(v for v in new.vendors if v.category == "Magician")
    assert v.est_cost_range == "Get 2-3 quotes first"


def test_summary_includes_budget_notes():
    from services.refiner import plan_summary
    assert '"covers"' in plan_summary(base_plan())
