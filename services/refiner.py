"""Chat refinement. The LLM proposes a PATCH; this code validates and applies it."""
import json
import re

from core.models import BudgetLine, Plan, PlanPatch, Task, Vendor
from services.budget_calc import build_budget
from services.planner import _ask
from services.timeline_dates import assign_dates, weeks_available


def _match(name: str, items: list, key):
    """Find the item whose name overlaps `name` (case-insensitive)."""
    n = name.strip().lower()
    for it in items:
        k = key(it).lower()
        if n and (n == k or n in k or k in n):
            return it
    return None


def plan_summary(plan: Plan) -> str:
    """Compact view of the plan sent to the LLM (cheaper than the full JSON)."""
    b = plan.brief
    return json.dumps({
        "event_type": b.event_type, "guests": b.guests, "total_budget_inr": b.budget,
        "city": b.city, "traditions": b.traditions,
        "weeks_available": weeks_available(b.event_date),
        "budget": [{"category": i.category, "percent": i.percent, "covers": i.note[:90]} for i in plan.budget],
        "timeline": [{"title": t.title, "weeks_before": t.weeks_before} for t in plan.timeline],
        "vendors": [v.category for v in plan.vendors],
        "ideas": [i[:70] for i in plan.ideas],
    }, ensure_ascii=False)


def apply_patch(plan: Plan, patch: PlanPatch) -> tuple[Plan, list[str]]:
    """Validate and apply a patch to a COPY of the plan. Returns (new_plan, change_log)."""
    p = plan.model_copy(deep=True)
    changes: list[str] = []
    old_total = plan.brief.budget
    old_amounts = {i.category: i.amount for i in plan.budget}

    # --- guests ---
    if 1 <= patch.new_guests <= 5000 and patch.new_guests != p.brief.guests:
        changes.append(f"Guests: {p.brief.guests} → {patch.new_guests}")
        p.brief.guests = patch.new_guests

    # --- total budget (sanity check: stay within 0.3x to 3x) ---
    total_changed = False
    if patch.new_budget_total > 0 and patch.new_budget_total != old_total:
        ratio = patch.new_budget_total / old_total
        if 0.3 <= ratio <= 3:
            p.brief.budget = patch.new_budget_total
            total_changed = True
        else:
            changes.append("Ignored an unrealistic budget change (more than 3x or less than 0.3x).")

    # --- traditions ---
    existing = [t.lower() for t in p.brief.traditions]
    for t in patch.add_traditions:
        if t.strip() and t.strip().lower() not in existing:
            p.brief.traditions.append(t.strip())
            changes.append(f"Added function: {t.strip()}")

    # --- budget lines ---
    lines = [BudgetLine(category=i.category, percent=i.amount / old_total * 100, note=i.note)
             for i in plan.budget]
    edited = False
    for name in patch.remove_budget_categories:
        m = _match(name, lines, lambda l: l.category)
        if m and "contingency" not in m.category.lower():     # always keep a safety buffer
            lines.remove(m)
            edited = True
    for ch in patch.budget_changes:
        m = _match(ch.category, lines, lambda l: l.category)
        if m and ch.new_percent > 0:
            m.percent = ch.new_percent
            edited = True
    for l in patch.add_budget_lines:
        if l.percent > 0 and not _match(l.category, lines, lambda x: x.category):
            lines.append(l)
            edited = True
    if lines and (edited or total_changed):
        p.budget = build_budget(lines, p.brief.budget)
        new_amounts = {i.category: i.amount for i in p.budget}
        if total_changed:
            changes.append(f"Total budget: ₹{old_total:,} → ₹{p.brief.budget:,}")
        if edited:
            for cat, amt in new_amounts.items():
                if cat not in old_amounts:
                    changes.append(f"Added budget line: {cat} (₹{amt:,})")
                elif amt != old_amounts[cat]:
                    changes.append(f"{cat}: ₹{old_amounts[cat]:,} → ₹{amt:,}")
            for cat in old_amounts:
                if cat not in new_amounts:
                    changes.append(f"Removed budget line: {cat}")
        elif total_changed:
            changes.append("All budget categories scaled proportionally.")

    # --- tasks ---
    for title in patch.remove_task_titles:
        m = _match(title, p.timeline, lambda t: t.title)
        if m:
            p.timeline.remove(m)
            changes.append(f"Removed task: {m.title}")
    for t in patch.add_tasks:
        if not _match(t.title, p.timeline, lambda x: x.title):
            p.timeline.append(Task(title=t.title, weeks_before=max(t.weeks_before, 0)))
            changes.append(f"Added task: {t.title}")
    p.timeline = assign_dates(p.timeline, p.brief.event_date)

    # --- vendors ---
    for cat in patch.remove_vendor_categories:
        m = _match(cat, p.vendors, lambda v: v.category)
        if m:
            p.vendors.remove(m)
            changes.append(f"Removed vendor: {m.category}")
    for v in patch.add_vendors:
        if not _match(v.category, p.vendors, lambda x: x.category):
            new_vendor = Vendor(**v.model_dump())
            if not re.search(r"\d", new_vendor.est_cost_range):      # LLM gave no real number
                new_vendor.est_cost_range = "Get 2-3 quotes first"
            p.vendors.append(new_vendor)
            changes.append(f"Added vendor: {v.category}")

    # --- ideas ---
    for frag in patch.remove_ideas:
        m = next((i for i in p.ideas if frag.strip().lower() in i.lower()), None) if frag.strip() else None
        if m:
            p.ideas.remove(m)
            changes.append("Removed an idea")
    for idea in patch.add_ideas:
        if idea.strip() and idea not in p.ideas:
            p.ideas.append(idea)
            changes.append(f"Added idea: {idea[:60]}")

    if changes:
        p.version += 1
    return p, changes


def refine(plan: Plan, message: str, provider) -> tuple[Plan, list[str], str]:
    """Returns (new_plan, change_log, reply_text). Plan is unchanged if the LLM fails."""
    msg = f"Current plan:\n{plan_summary(plan)}\n\nUser request: {message}"
    patch = _ask(provider, "refine", msg, PlanPatch)
    if patch is None:
        return plan, [], "Sorry, I couldn't process that request. Please try rephrasing it."
    new_plan, changes = apply_patch(plan, patch)
    reply = patch.reply or ("Done." if changes else "I didn't change anything.")
    return new_plan, changes, reply
