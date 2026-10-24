"""Deterministic budget math. The LLM suggests percentages; this computes money."""
from core.models import BudgetLine, BudgetItem


def build_budget(lines: list[BudgetLine], total: int) -> list[BudgetItem]:
    """Normalize percentages to 100%, convert to rupees, fix rounding drift."""
    clean = [l for l in lines if l.percent > 0]
    if not clean:
        raise ValueError("No budget lines with a positive percentage")

    pct_sum = sum(l.percent for l in clean)
    items = []
    for l in clean:
        share = l.percent / pct_sum          # normalized 0..1
        items.append(BudgetItem(
            category=l.category,
            percent=round(share * 100, 1),
            amount=int(round(share * total)),
            note=l.note,
        ))

    # Rounding can leave us a few rupees off. Put the drift on the biggest line.
    drift = total - sum(i.amount for i in items)
    biggest = max(items, key=lambda i: i.amount)
    biggest.amount += drift
    return items
