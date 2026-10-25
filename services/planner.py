"""Orchestrator: 2 LLM calls per plan (budget, then details), each with retry + template fallback."""
import json
import time
from pathlib import Path

from core.models import (
    EventBrief, Plan, BudgetLine, BudgetItem, BudgetSuggestion, Task, Vendor, DetailsSuggestion,
)
from services.budget_calc import build_budget
from services.timeline_dates import assign_dates, weeks_available

ROOT = Path(__file__).resolve().parent.parent
RETRY_DELAY = 2.0     # seconds; tests set this to 0
LAST_ERROR = {"msg": ""}   # most recent LLM failure, shown in the UI
AI_LOG: list[dict] = []    # last prompts and responses, shown in the AI Inspector tab
DAILY_QUOTA_MSG = ("Daily free-tier quota used up (resets at midnight Pacific time). "
                   "Add more models to GEMINI_MODELS in .env, or try again tomorrow.")


def load_template(event_type: str) -> dict:
    path = ROOT / "data" / "templates" / f"{event_type}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_prompt(name: str) -> str:
    return (ROOT / "prompts" / f"{name}.md").read_text(encoding="utf-8")


def _brief_text(brief: EventBrief) -> str:
    return (
        f"Event: {brief.event_type}\n"
        f"Guests: {brief.guests}\n"
        f"Total budget: INR {brief.budget}\n"
        f"City: {brief.city}\n"
        f"Vibe: {brief.vibe or 'not specified'}\n"
        f"Traditions/functions: {', '.join(brief.traditions) or 'none'}\n"
        f"Weeks available until the event: {weeks_available(brief.event_date)}"
    )


def _budget_text(budget: list[BudgetItem] | None) -> str:
    """The decided budget, shown to the details call so all sections agree."""
    if not budget:
        return ""
    rows = "\n".join(f"- {i.category}: INR {i.amount:,} ({i.percent}%)" for i in budget)
    return "\n\nBudget allocation (already decided; stay consistent with it):\n" + rows


def _ask(provider, prompt_name: str, user_msg: str, schema, system: str | None = None):
    """One try + one retry with the error fed back. Returns None if it fails.
    A daily-quota error is never retried (waiting a few seconds cannot fix it)."""
    system = system or load_prompt(prompt_name)
    error = ""
    for attempt in range(2):
        msg = user_msg
        if error:
            msg += f"\n\nYour previous answer was rejected because: {error}. Fix it."
        try:
            t0 = time.time()
            result = provider.generate(system, msg, schema)
            AI_LOG.append({"step": prompt_name, "model": getattr(provider, "last_model", ""),
                           "seconds": round(time.time() - t0, 1), "prompt": msg,
                           "response": result.model_dump_json(indent=2)})
            del AI_LOG[:-10]                  # keep the last 10 calls
            return result
        except Exception as e:               # bad JSON, schema fail, API hiccup
            full = str(e)
            error = full[:200]
            print(f"[LLM error: {prompt_name}] {error}")
            if "PerDay" in full:
                LAST_ERROR["msg"] = DAILY_QUOTA_MSG
                return None
            LAST_ERROR["msg"] = error
            if attempt == 0:
                busy = any(k in error for k in ("429", "503", "RESOURCE_EXHAUSTED", "UNAVAILABLE"))
                time.sleep(RETRY_DELAY * (4 if busy else 1))   # wait longer when the service is busy
    return None


# ---------------- generators ----------------
def generate_budget(brief: EventBrief, provider) -> tuple[list[BudgetItem], str]:
    """Returns (budget items, 'ai' | 'template')."""
    template = load_template(brief.event_type)
    msg = _brief_text(brief) + "\n\nDefault categories to start from:\n" + json.dumps(template["default_budget_split"])
    result = _ask(provider, "budget", msg, BudgetSuggestion)
    if result:
        try:
            return build_budget(result.items, brief.budget), "ai"
        except Exception as e:
            print(f"[budget math error] {e}")
    lines = [BudgetLine(**l) for l in template["default_budget_split"]]
    return build_budget(lines, brief.budget), "template"


def _details_system() -> str:
    """Reuse the three section prompts as one system prompt."""
    return (
        "You plan the details of an event in one go. Return three sections: tasks (the planning "
        "timeline), vendors, and ideas. Follow the rules for each section below.\n\n"
        "## tasks (timeline)\n" + load_prompt("timeline") +
        "\n\n## vendors\n" + load_prompt("vendors") +
        "\n\n## ideas\n" + load_prompt("ideas")
    )


def generate_details(brief: EventBrief, provider, budget):
    """ONE call for timeline + vendors + ideas. Each section falls back to its template on its own.
    Returns (tasks, vendors, ideas, sources)."""
    msg = _brief_text(brief) + _budget_text(budget)
    result = _ask(provider, "details", msg, DetailsSuggestion, system=_details_system())

    tasks = vendors = ideas = None
    if result:
        if result.tasks:
            tasks = [Task(title=t.title, weeks_before=t.weeks_before) for t in result.tasks]
        if result.vendors:
            vendors = [Vendor(**v.model_dump()) for v in result.vendors]
        if result.ideas:
            ideas = list(result.ideas)

    sources = {
        "timeline": "ai" if tasks else "template",
        "vendors": "ai" if vendors else "template",
        "ideas": "ai" if ideas else "template",
    }
    template = load_template(brief.event_type)
    tasks = tasks or [Task(**t) for t in template["default_timeline"]]
    vendors = vendors or [Vendor(**v) for v in template["default_vendors"]]
    ideas = ideas or list(template["default_ideas"])
    return assign_dates(tasks, brief.event_date), vendors, ideas, sources


def build_plan(brief: EventBrief, provider) -> Plan:
    """Call 1: budget. Call 2: timeline + vendors + ideas, shown the finished budget."""
    LAST_ERROR["msg"] = ""
    budget, budget_source = generate_budget(brief, provider)
    timeline, vendors, ideas, sources = generate_details(brief, provider, budget)
    return Plan(brief=brief, budget=budget, timeline=timeline, vendors=vendors, ideas=ideas,
                sources={"budget": budget_source, **sources})
