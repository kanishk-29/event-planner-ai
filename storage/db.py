"""SQLite persistence. One row per saved plan, stored as JSON."""
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from core.models import Plan

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "planner.db"


@contextmanager
def _conn(path=None):
    c = sqlite3.connect(path or DB_PATH)
    c.row_factory = sqlite3.Row
    try:
        yield c
        c.commit()
    finally:
        c.close()


def init_db(path=None) -> None:
    with _conn(path) as c:
        c.execute("""CREATE TABLE IF NOT EXISTS plans (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            updated TEXT NOT NULL,
            data TEXT NOT NULL)""")


def save_plan(plan: Plan, name: str | None = None, plan_id: int | None = None, path=None) -> int:
    """Insert a new plan, or update the existing one if plan_id is given."""
    now = datetime.now().isoformat(timespec="seconds")
    with _conn(path) as c:
        if plan_id is not None:
            c.execute("UPDATE plans SET data=?, updated=?, name=COALESCE(?, name) WHERE id=?",
                      (plan.model_dump_json(), now, name, plan_id))
            return plan_id
        cur = c.execute("INSERT INTO plans (name, updated, data) VALUES (?, ?, ?)",
                        (name or "Untitled plan", now, plan.model_dump_json()))
        return cur.lastrowid


def list_plans(path=None) -> list[tuple[int, str, str]]:
    with _conn(path) as c:
        rows = c.execute("SELECT id, name, updated FROM plans ORDER BY updated DESC").fetchall()
    return [(r["id"], r["name"], r["updated"]) for r in rows]


def load_plan(plan_id: int, path=None) -> Plan:
    with _conn(path) as c:
        row = c.execute("SELECT data FROM plans WHERE id=?", (plan_id,)).fetchone()
    if row is None:
        raise KeyError(f"No plan with id {plan_id}")
    return Plan.model_validate_json(row["data"])


def delete_plan(plan_id: int, path=None) -> None:
    with _conn(path) as c:
        c.execute("DELETE FROM plans WHERE id=?", (plan_id,))
