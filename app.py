"""Streamlit UI. Run: streamlit run app.py"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.models import EventBrief, Plan
from llm import get_provider
from export.pdf import build_pdf
from services.planner import LAST_ERROR, build_plan
from services.refiner import refine
from services.timeline_dates import weeks_available
from services.validators import check_plan
from storage import db

st.set_page_config(page_title="AI Event Planner", page_icon="🎉", layout="wide")
db.init_db()
ss = st.session_state
for key, default in [("plan", None), ("plan_id", None), ("chat", []), ("undo", []), ("nonce", 0)]:
    ss.setdefault(key, default)


def set_plan(plan: Plan, plan_id: int | None = None):
    """Switch to a different plan. Bumping nonce resets widget state (checkboxes etc.)."""
    ss.plan, ss.plan_id = plan, plan_id
    ss.chat, ss.undo = [], []
    ss.nonce += 1


st.title("🎉 AI Event Planning Assistant")
st.caption("Budgets, timelines, vendor checklists and ideas for weddings, birthdays and community events.")

# ---------------- Sidebar: intake form + saved plans ----------------
with st.sidebar:
    st.header("Event details")
    event_type = st.selectbox("Event type", ["wedding", "birthday", "community"])
    event_date = st.date_input("Event date", value=date.today() + timedelta(weeks=12), min_value=date.today())
    guests = st.number_input("Guests", min_value=1, max_value=5000, value=100)
    budget = st.number_input("Total budget (₹)", min_value=10000, max_value=100_000_000, value=500_000, step=10_000)
    city = st.text_input("City", value="Lucknow")
    vibe = st.text_input("Vibe / theme", placeholder="royal, minimalist, eco-friendly...")
    traditions = st.text_input("Functions / special notes", placeholder="mehendi, sangeet, 8th birthday (comma separated)")
    go = st.button("Generate plan", type="primary", use_container_width=True)

    st.divider()
    st.header("Saved plans")
    saved = db.list_plans()
    if saved:
        labels = {f"{name} ({upd[:10]})": pid for pid, name, upd in saved}
        choice = st.selectbox("Your plans", list(labels))
        c1, c2 = st.columns(2)
        if c1.button("Load", use_container_width=True):
            set_plan(db.load_plan(labels[choice]), labels[choice])
            st.rerun()
        if c2.button("Delete", use_container_width=True):
            db.delete_plan(labels[choice])
            if ss.plan_id == labels[choice]:
                ss.plan_id = None
            st.rerun()
    else:
        st.caption("Nothing saved yet.")

if go:
    try:
        brief = EventBrief(
            event_type=event_type, event_date=event_date, guests=int(guests), budget=int(budget),
            city=city.strip() or "India", vibe=vibe.strip(),
            traditions=[t.strip() for t in traditions.split(",") if t.strip()],
        )
        provider = get_provider()
        with st.spinner("Your planning team is working..."):
            set_plan(build_plan(brief, provider))
    except Exception as e:
        st.error(f"Could not generate the plan: {e}")

if not ss.plan:
    st.info("Fill in the details on the left and click **Generate plan**, or load a saved plan.")
    st.stop()

# ---------------- Chat input: edits the plan (pinned to page bottom) ----------------
prompt = st.chat_input("Edit your plan: 'make it cheaper', 'add a mehendi function', 'increase guests to 150'...")
if prompt:
    ss.chat.append({"role": "user", "content": prompt, "changes": []})
    try:
        with st.spinner("Updating your plan..."):
            new_plan, changes, reply = refine(ss.plan, prompt, get_provider())
        if changes:
            ss.undo.append(ss.plan.model_dump_json())
            ss.plan = new_plan
            ss.nonce += 1
            if ss.plan_id:
                db.save_plan(ss.plan, plan_id=ss.plan_id)
        ss.chat.append({"role": "assistant", "content": reply, "changes": changes})
    except Exception as e:
        st.error(f"Could not update the plan: {e}")

plan = ss.plan
b = plan.brief

fallbacks = [k for k, v in plan.sources.items() if v == "template"]
if fallbacks:
    st.warning(f"AI was unavailable for: {', '.join(fallbacks)}. Showing standard templates for those sections.")
    if LAST_ERROR["msg"]:
        st.caption(f"Reason: {LAST_ERROR['msg']}")

# Latest chat result, visible on every tab
last = next((m for m in reversed(ss.chat) if m["role"] == "assistant"), None)
if last:
    with st.container(border=True):
        st.markdown(f"💬 **{last['content']}**")
        for c in last["changes"]:
            st.markdown(f"- {c}")
        if ss.undo and st.button("↩ Undo last change"):
            ss.plan = Plan.model_validate_json(ss.undo.pop())
            ss.nonce += 1
            ss.chat.append({"role": "assistant", "content": "Reverted to the previous version.", "changes": []})
            st.rerun()

tab_over, tab_budget, tab_time, tab_vendor, tab_ideas, tab_chat = st.tabs(
    ["Overview", "Budget", "Timeline", "Vendors", "Ideas", "Chat history"])

# ---------------- Overview ----------------
with tab_over:
    done = sum(t.done for t in plan.timeline)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Budget", f"₹{b.budget:,}")
    c2.metric("Per guest", f"₹{b.budget // b.guests:,}")
    c3.metric("Weeks left", weeks_available(b.event_date))
    c4.metric("Tasks done", f"{done}/{len(plan.timeline)}")
    st.progress(done / max(len(plan.timeline), 1))
    st.caption(f"Plan version {plan.version} · {b.event_type.title()} in {b.city.title()} · {b.guests} guests")
    for w in check_plan(plan):
        st.warning(w)

    default_name = f"{b.event_type.title()} · {b.city.title()} · {b.event_date}"
    name = st.text_input("Plan name", value=default_name, key=f"name_{ss.nonce}")
    s1, s2, s3 = st.columns(3)
    if s1.button("💾 Save plan", use_container_width=True):
        ss.plan_id = db.save_plan(plan, name, ss.plan_id)
        st.success("Saved. You can reload it from the sidebar.")
    s2.download_button("⬇ Download JSON", plan.model_dump_json(indent=2),
                       file_name="event_plan.json", mime="application/json", use_container_width=True)
    try:
        s3.download_button("⬇ Download PDF", build_pdf(plan), file_name="event_plan.pdf",
                           mime="application/pdf", use_container_width=True)
    except Exception as e:
        s3.caption(f"PDF unavailable: {e}")

# ---------------- Budget ----------------
with tab_budget:
    df = pd.DataFrame([{"Category": i.category, "Share %": i.percent, "Amount (₹)": i.amount, "Why": i.note}
                       for i in plan.budget])
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.bar_chart(df.set_index("Category")["Amount (₹)"])
    st.caption(f"Total allocated: ₹{sum(i.amount for i in plan.budget):,}")

# ---------------- Timeline ----------------
with tab_time:
    for idx, t in enumerate(plan.timeline):
        t.done = st.checkbox(f"{t.title}  ·  {t.due_date:%d %b %Y}", value=t.done, key=f"task_{ss.nonce}_{idx}")

# ---------------- Vendors ----------------
with tab_vendor:
    states = ["to-contact", "booked", "paid"]
    for idx, v in enumerate(plan.vendors):
        with st.expander(f"{v.category}  ·  {v.est_cost_range}"):
            v.status = st.selectbox("Status", states, index=states.index(v.status) if v.status in states else 0,
                                    key=f"vendor_{ss.nonce}_{idx}")
            st.markdown("**Ask them:**")
            for q in v.what_to_ask:
                st.markdown(f"- {q}")

# ---------------- Ideas ----------------
with tab_ideas:
    for idea in plan.ideas:
        st.markdown(f"- {idea}")

# ---------------- Chat history ----------------
with tab_chat:
    if not ss.chat:
        st.caption("Use the chat box at the bottom of the page to edit your plan.")
    for m in ss.chat:
        with st.chat_message(m["role"]):
            st.write(m["content"])
            for c in m.get("changes", []):
                st.markdown(f"- {c}")
