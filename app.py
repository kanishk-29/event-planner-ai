"""Streamlit UI. Run: streamlit run app.py"""
import re
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import streamlit as st

from core.models import EventBrief, Plan
from export.pdf import build_pdf
from llm import get_provider
from services.planner import AI_LOG, LAST_ERROR, build_plan
from services.refiner import refine
from services.timeline_dates import weeks_available
from services.validators import check_plan
from storage import db

st.set_page_config(page_title="AI Event Planner", page_icon="🎉", layout="wide",
                   initial_sidebar_state="expanded")
db.init_db()
ss = st.session_state
for key, default in [("plan", None), ("plan_id", None), ("chat", []), ("undo", []), ("nonce", 0)]:
    ss.setdefault(key, default)

# ---------------- Theme ----------------
_css = (Path(__file__).parent / "ui" / "style.css").read_text(encoding="utf-8")
st.markdown(f"<style>{_css}</style>", unsafe_allow_html=True)

EVENT_TYPES = ["wedding", "birthday", "engagement", "anniversary",
               "corporate event", "college fest", "community event", "other"]
EMOJI = {"wedding": "💍", "birthday": "🎂", "engagement": "💎", "anniversary": "🥂",
         "corporate event": "🏢", "college fest": "🎓", "community event": "🪔", "other": "🎉"}
VENUES = ["Not decided", "Indoor", "Outdoor", "Hotel or banquet hall", "Garden or farmhouse",
          "Home", "Convention centre"]

# Form values live in session_state so the example cards can pre-fill the form.
FORM_DEFAULTS = {"f_type": "wedding", "f_date": date.today() + timedelta(weeks=12), "f_guests": 100,
                 "f_budget": 500_000, "f_city": "", "f_venue": "Not decided", "f_vibe": "", "f_notes": ""}
for _k, _v in FORM_DEFAULTS.items():
    ss.setdefault(_k, _v)

EXAMPLES = [
    ("💍 Royal Wedding", "Lucknow · 300 guests · Elegant and traditional", "Pre-fill wedding",
     dict(f_type="wedding", f_guests=300, f_budget=1_500_000, f_city="Lucknow",
          f_vibe="royal, elegant, traditional", f_notes="mehendi, sangeet")),
    ("🎂 Kids' Birthday", "Kanpur · 50 guests · Colourful and playful", "Pre-fill birthday",
     dict(f_type="birthday", f_guests=50, f_budget=100_000, f_city="Kanpur",
          f_vibe="colourful, playful, cartoon theme", f_notes="8th birthday, magic show")),
    ("🪔 Diwali Meetup", "Bengaluru · 100 guests · Festive and warm", "Pre-fill meetup",
     dict(f_type="community event", f_guests=100, f_budget=200_000, f_city="Bengaluru",
          f_vibe="festive, warm, traditional", f_notes="Diwali celebration")),
]


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


def footer():
    st.markdown('<div class="footer">Made for memorable moments ✨<br>'
                'AI Event Planning Assistant · Plan thoughtfully. Celebrate fully.</div>',
                unsafe_allow_html=True)


# ---------------- Sidebar: intake form + saved plans ----------------
with st.sidebar:
    st.markdown("## ✨ Event Studio")
    st.caption("Your event starts with a plan.")
    st.divider()
    st.markdown("### 📋 Event details")
    with st.form("intake"):
        event_type = st.selectbox("Event type", EVENT_TYPES, key="f_type",
                                  format_func=lambda x: f"{EMOJI[x]} {x.capitalize()}")
        event_date = st.date_input("Event date", min_value=date.today(), key="f_date")
        guests = st.number_input("Number of guests", min_value=1, max_value=5000, step=10, key="f_guests")
        budget = st.number_input("Total budget (₹)", min_value=10_000, max_value=100_000_000,
                                 step=5_000, key="f_budget")
        city = st.text_input("City", placeholder="e.g. Lucknow", key="f_city")
        venue = st.selectbox("Venue preference", VENUES, key="f_venue")
        vibe = st.text_input("Vibe / theme", placeholder="Royal, minimalist, eco-friendly...", key="f_vibe")
        notes = st.text_area("Functions / special notes", height=100, key="f_notes",
                             placeholder="Mehendi, sangeet, live music, dietary needs...")
        go = st.form_submit_button("✨ Generate my event plan", type="primary", use_container_width=True)

    st.divider()
    st.markdown("### 💾 Saved plans")
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

    st.divider()
    st.markdown("### 💡 Planning tip")
    st.info("Set aside 5-10% of your budget for unexpected expenses.")

if go:
    try:
        brief = EventBrief(
            event_type=event_type, event_date=event_date, guests=int(guests), budget=int(budget),
            city=city.strip() or "India", venue="" if venue == "Not decided" else venue,
            vibe=vibe.strip(), traditions=[t.strip() for t in re.split(r"[,\n]", notes) if t.strip()],
        )
        provider = get_provider()
        with st.spinner("Gemini is planning your event (usually 15-40 seconds)..."):
            set_plan(build_plan(brief, provider))
    except Exception as e:
        st.error(f"Could not generate the plan: {e}")

# ---------------- Landing page (no plan yet) ----------------
if not ss.plan:
    st.markdown(
        '<section class="hero" aria-labelledby="app-title"><div class="hero-label">PLAN SMARTER · CELEBRATE BETTER</div>'
        '<h1 id="app-title"><span aria-hidden="true">🎉</span> AI Event Planning Assistant</h1>'
        '<p>From the first idea to the final celebration, plan your event with confidence. '
        'Create a personalised budget, organised timeline, vendor checklist and creative ideas with AI.</p></section>',
        unsafe_allow_html=True)
    st.markdown('<h2 class="section-heading">Everything you need to plan</h2>'
                '<div class="section-description">One workspace. Every detail. A celebration that feels like yours.</div>',
                unsafe_allow_html=True)
    cards = [("💰", "Smart Budget", "AI suggests the split, code computes exact rupees, so it always adds up."),
             ("🗓️", "Dated Timeline", "Your event date becomes an actionable schedule with real deadlines."),
             ("🤝", "Vendor Checklist", "Venue, catering, decor and entertainment, with questions to ask each vendor.")]
    for col, (icon, title, text) in zip(st.columns(3, gap="large"), cards):
        col.markdown(f'<article class="feature-card"><div class="feature-icon" aria-hidden="true">{icon}</div>'
                     f'<h3 class="feature-title">{title}</h3>'
                     f'<p class="feature-description">{text}</p></article>', unsafe_allow_html=True)
    st.markdown('<h2 class="section-heading">Need some inspiration?</h2>'
                '<div class="section-description">Pre-fill the form with an example, then press '
                '<b>Generate my event plan</b>. Examples never call the AI by themselves.</div>',
                unsafe_allow_html=True)
    for col, (title, caption, label, vals) in zip(st.columns(3, gap="large"), EXAMPLES):
        with col:
            st.markdown(f"### {title}")
            st.caption(caption)
            st.button(label, key=f"ex_{label}", on_click=fill_example, args=(vals,), use_container_width=True)
    footer()
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
st.title(f"{EMOJI.get(b.event_type, '🎉')} {b.event_type.title()} · {b.city.title()} · {b.event_date:%d %b %Y}")

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
    st.caption("Bar chart of the rupee amount for each budget category. The table above lists the same values.")
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

footer()
