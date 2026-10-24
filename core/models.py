"""Single source of truth: every layer reads and writes these objects."""
from datetime import date
from pydantic import BaseModel, Field


class EventBrief(BaseModel):
    """What the user tells us."""
    event_type: str                      # wedding | birthday | community
    event_date: date
    guests: int = Field(gt=0)
    budget: int = Field(gt=0)            # INR
    city: str
    vibe: str = ""
    traditions: list[str] = []


# ---- What the LLM is allowed to return (no money amounts, no dates) ----
class BudgetLine(BaseModel):
    category: str
    percent: float                       # share of budget, e.g. 35 means 35%
    note: str = ""


class BudgetSuggestion(BaseModel):
    items: list[BudgetLine]


# ---- What the app stores/shows (amounts filled by code) ----
class BudgetItem(BaseModel):
    category: str
    percent: float
    amount: int = 0
    note: str = ""


class Task(BaseModel):
    title: str
    weeks_before: int
    due_date: date | None = None
    done: bool = False


class Vendor(BaseModel):
    category: str
    what_to_ask: list[str] = []
    est_cost_range: str = ""
    status: str = "to-contact"           # to-contact | booked | paid


class Plan(BaseModel):
    brief: EventBrief
    sources: dict[str, str] = {}         # section -> 'ai' | 'template'
    budget: list[BudgetItem] = []
    timeline: list[Task] = []
    vendors: list[Vendor] = []
    ideas: list[str] = []
    sources: dict[str, str] = {}         # section -> 'ai' | 'template'
    version: int = 1


# ---- More LLM-facing schemas ----
class TaskLine(BaseModel):
    title: str
    weeks_before: int


class TimelineSuggestion(BaseModel):
    tasks: list[TaskLine]


class VendorLine(BaseModel):
    category: str
    what_to_ask: list[str]
    est_cost_range: str


class VendorSuggestion(BaseModel):
    vendors: list[VendorLine]


class IdeasSuggestion(BaseModel):
    ideas: list[str]


# ---- LLM output schemas for the other generators ----
class TaskLine(BaseModel):
    title: str
    weeks_before: int


class TimelineSuggestion(BaseModel):
    tasks: list[TaskLine]


class VendorLine(BaseModel):
    category: str
    what_to_ask: list[str]
    est_cost_range: str


class VendorSuggestion(BaseModel):
    vendors: list[VendorLine]


class IdeasSuggestion(BaseModel):
    ideas: list[str]


# ---- Phase 3: LLM output schemas (no dates, no money; code fills those) ----
class TaskSuggestion(BaseModel):
    title: str
    weeks_before: int


class TimelineSuggestion(BaseModel):
    tasks: list[TaskSuggestion]


class VendorLine(BaseModel):
    category: str
    what_to_ask: list[str]
    est_cost_range: str


class VendorSuggestion(BaseModel):
    vendors: list[VendorLine]


class IdeasSuggestion(BaseModel):
    ideas: list[str]


# ---- Phase 4: what the chat LLM may ask us to change (a "patch") ----
class BudgetChange(BaseModel):
    category: str
    new_percent: float


class PlanPatch(BaseModel):
    reply: str = ""                                        # friendly 1-2 sentence answer
    new_budget_total: int = 0                              # 0 = unchanged
    new_guests: int = 0                                    # 0 = unchanged
    add_traditions: list[str] = Field(default_factory=list)
    budget_changes: list[BudgetChange] = Field(default_factory=list)
    add_budget_lines: list[BudgetLine] = Field(default_factory=list)
    remove_budget_categories: list[str] = Field(default_factory=list)
    add_tasks: list[TaskSuggestion] = Field(default_factory=list)
    remove_task_titles: list[str] = Field(default_factory=list)
    add_vendors: list[VendorLine] = Field(default_factory=list)
    remove_vendor_categories: list[str] = Field(default_factory=list)
    add_ideas: list[str] = Field(default_factory=list)
    remove_ideas: list[str] = Field(default_factory=list)


class DetailsSuggestion(BaseModel):
    """Timeline + vendors + ideas in ONE call (saves free-tier quota)."""
    tasks: list[TaskSuggestion]
    vendors: list[VendorLine]
    ideas: list[str]
