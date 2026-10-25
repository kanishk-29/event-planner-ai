"""Streamlit UI. Run: streamlit run app.py"""
from datetime import date, timedelta

import pandas as pd
import streamlit as st

from core.models import EventBrief, Plan
from llm import get_provider
from export.pdf import build_pdf
from services.planner import AI_LOG, LAST_ERROR, build_plan
from services.refiner import refine
from services.timeline_dates import weeks_available
from services.validators import check_plan
from storage import db

st.set_page_config(page_title="AI Event Planner", page_icon="🎉", layout="wide")
db.init_db()
ss = st.session_state
for key, default in [("plan", None), ("plan_id", None), ("chat", []), ("undo", []), ("nonce", 0)]:
    ss.setdefault(key, default)

EMOJI = {"wedding": "💍", "birthday": "🎂", "community": "🪔"}

st.markdown("""
<style>
.block-container {padding-top: 2rem; max-width: 1200px;}
.hero {padding: 2.2rem 2rem; border-radius: 18px; margin-bottom: 1.2rem;
       background: linear-gradient(135deg, #B3261E 0%, #E8590C 55%, #F5A623 100%);}
.hero h1 {color: #fff; margin: 0 0 .5rem 0; font-size: 2.3rem; padding: 0;}
.hero p {color: #fff; opacity: .95; font-size: 1.05rem; margin: 0;}
div[data-testid="stMetric"] {background: rgba(128,128,128,.10); border-radius: 12px; padding: .8rem 1rem;}
</style>
""", unsafe_allow_html=True)

# Form defaults live in session_state so the example buttons can pre-fill the form.
FORM_DEFAULTS = {"f_type": "wedding", "f_date": date.today() + timedelta(weeks=12), "f_guests": 100,
                 "f_budget": 500_000, "f_city": "", "f_vibe": "", "f_notes": ""}
for _k, _v in FORM_DEFAULTS.items():
    ss.setdefault(_k, _v)

EXAMPLES = {
    "💍 Royal wedding, Lucknow": dict(f_type="wedding", f_guests=150, f_budget=1_200_000, f_city="Lucknow",
                                      f_vibe="royal", f_notes="mehendi, sangeet"),
    "🎂 Kid's birthday, Kanpur": dict(f_type="birthday", f_guests=40, f_budget=100_000, f_city="Kanpur",
                                      f_vibe="balloons, flowers, kids theme", f_notes="8th birthday, magic show"),
    "🪔 Diwali meetup, Bengaluru": dict(f_type="community", f_guests=300, f_budget=500_000, f_city="Bengaluru",
                                        f_vibe="traditional lamps, white theme", f_notes="Diwali celebration"),
}


def fill_example(values: dict):
    """Button callback: pre-fill the sidebar form (does NOT call the AI)."""
    for k, v in values.items():
        ss[k] = v
    ss["f_date"] = date.today() + timedelta(weeks=12)


def set_plan(plan: Plan, plan_id: int | None = None):
    """Switch to a different plan. Bumping nonce resets widget state (checkboxes etc.)."""
    ss.plan, ss.plan_id = plan, plan_id
    ss.chat, ss.undo = [], []
    ss.nonce += 1


# ---------------- Sidebar: intake form + saved plans ----------------
with st.sidebar:
    st.header("Event details")
    with st.form("intake"):
        event_type = st.selectbox("Event type", ["wedding", "birthday", "community"], key="f_type",
                                  format_func=lambda x: f"{EMOJI[x]} {x.title()}")
        event_date = st.date_input("Event date", min_value=date.today(), key="f_date")
        guests = st.number_input("Guests", min_value=1, max_value=5000, key="f_guests")
        budget = st.number_input("Total budget (₹)", min_value=10000, max_value=100_000_000,
                                 step=10_000, key="f_budget")
        city = st.text_input("City", placeholder="e.g. Lucknow", key="f_city")
        vibe = st.text_input("Vibe / theme", placeholder="royal, minimalist, eco-friendly...", key="f_vibe")
        traditions = st.text_input("Functions / special notes",
                                   placeholder="mehendi, sangeet, 8th birthday (comma separated)", key="f_notes")
        go = st.form_submit_button("✨ Generate plan", type="primary", use_container_width=True)

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
        with st.spinner("Gemini is planning your event (usually 15-40 seconds)..."):
            set_plan(build_plan(brief, provider))
    except Exception as e:
        st.error(f"Could not generate the plan: {e}")

if not ss.plan:
    st.markdown(
        '<div class="hero"><h1>🎉 AI Event Planning Assistant</h1>'
        '<p>Tell us about your wedding, birthday or community event. Gemini builds your budget, '
        'timeline, vendor checklist and ideas, and you refine it just by chatting.</p></div>',
        unsafe_allow_html=True)
    cards = [("💰 Smart budget", "AI suggests the split, code computes exact rupees. It always adds up."),
             ("📅 Dated timeline", "Tasks worked backwards from your event date."),
             ("🧾 Vendor checklist", "What to ask each vendor, with cost ranges that fit your budget.")]
    for col, (title, text) in zip(st.columns(3), cards):
        with col:
            with st.container(border=True):
                st.markdown(f"**{title}**")
                st.caption(text)
    st.markdown("#### How it works")
    st.markdown("1. **Fill in the form** on the left\n2. **Generate** and explore the tabs\n"
                "3. **Chat** to edit it: *make it cheaper*, *add a magic show*, *increase guests to 200*")
    st.markdown("#### Or start from an example")
    for col, (label, vals) in zip(st.columns(len(EXAMPLES)), EXAMPLES.items()):
        col.button(label, on_click=fill_example, args=(vals,), use_container_width=True)
    st.caption("Examples only fill the form. Press **Generate plan** to call the AI.")
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
st.subheader(f"{EMOJI.get(b.event_type, '🎉')} {b.event_type.title()} · {b.city.title()} · {b.event_date:%d %b %Y}")

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

tab_over, tab_budget, tab_time, tab_vendor, tab_ideas, tab_chat, tab_ai = st.tabs(
    ["Overview", "Budget", "Timeline", "Vendors", "Ideas", "Chat history", "AI Inspector"])

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

# ---------------- AI Inspector: proof of GenAI in action ----------------
with tab_ai:
    st.caption("Exactly what was sent to Gemini and what came back. The instructions for each step "
               "live in the prompts/ folder; Python then does the math and dates.")
    if not AI_LOG:
        st.info("No AI calls yet in this session. Generate a plan or use the chat box.")
    for entry in reversed(AI_LOG):
        with st.expander(f"Step: {entry['step']}  ·  {entry['model'] or 'gemini'}  ·  {entry['seconds']}s"):
            st.markdown("**Prompt sent (your input):**")
            st.code(entry["prompt"], language="text")
            st.markdown("**AI response (JSON):**")
            st.code(entry["response"], language="json")
