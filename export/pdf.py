"""PDF export with reportlab (pure Python, no system dependencies)."""
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from services.timeline_dates import weeks_available
from services.validators import check_plan

ACCENT = colors.HexColor("#B3261E")
LIGHT = colors.HexColor("#F4E9E8")


def _clean(text) -> str:
    """Built-in PDF fonts cover Latin-1 only, so swap or replace other characters."""
    s = str(text).replace("₹", "Rs ").replace("→", "->").replace("·", "-").replace("•", "-")
    s = s.encode("cp1252", errors="replace").decode("cp1252")
    return escape(s)


def _money(n: int) -> str:
    return f"Rs {n:,}"


def build_pdf(plan) -> bytes:
    """Render a Plan as a printable PDF and return the bytes."""
    b = plan.brief
    styles = getSampleStyleSheet()
    body = styles["BodyText"]
    h2 = ParagraphStyle("h2", parent=styles["Heading2"], textColor=ACCENT, spaceBefore=14, spaceAfter=6)
    cell = ParagraphStyle("cell", parent=body, fontSize=9, leading=11.5)
    bold = ParagraphStyle("bold", parent=cell, fontName="Helvetica-Bold")
    small = ParagraphStyle("small", parent=body, fontSize=9, leading=12, leftIndent=8)

    def P(text, style=cell):
        return Paragraph(_clean(text), style)

    def table(rows, widths, header=True):
        t = Table(rows, colWidths=[w * mm for w in widths], repeatRows=1 if header else 0)
        style = [
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#CCCCCC")),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]
        if header:
            style += [("BACKGROUND", (0, 0), (-1, 0), LIGHT)]
        t.setStyle(TableStyle(style))
        return t

    story = [Paragraph(_clean(f"{b.event_type.title()} Plan - {b.city.title()}"), styles["Title"])]

    # ---- summary ----
    meta = [
        ["Date", b.event_date.strftime("%d %b %Y"), "Guests", str(b.guests)],
        ["Budget", _money(b.budget), "Per guest", _money(b.budget // b.guests)],
        ["Weeks left", str(weeks_available(b.event_date)), "Plan version", str(plan.version)],
    ]
    story.append(table([[P(c, bold if i % 2 == 0 else cell) for i, c in enumerate(r)] for r in meta],
                       [28, 59, 28, 59], header=False))
    if b.vibe:
        story += [Spacer(1, 4), P(f"Vibe: {b.vibe}", body)]
    if b.traditions:
        story.append(P(f"Functions / notes: {', '.join(b.traditions)}", body))

    warnings = check_plan(plan)
    if warnings:
        story.append(Paragraph("Things to watch", h2))
        story += [P(f"- {w}", small) for w in warnings]

    # ---- budget ----
    story.append(Paragraph("Budget", h2))
    rows = [[P("Category", bold), P("Share", bold), P("Amount", bold), P("Why", bold)]]
    for i in plan.budget:
        rows.append([P(i.category), P(f"{i.percent:.1f}%"), P(_money(i.amount)), P(i.note)])
    rows.append([P("Total", bold), P("100%", bold), P(_money(sum(i.amount for i in plan.budget)), bold), P("")])
    story.append(table(rows, [50, 16, 30, 78]))

    # ---- timeline ----
    story.append(Paragraph("Timeline", h2))
    rows = [[P("Done", bold), P("Due", bold), P("Task", bold)]]
    for t in plan.timeline:
        due = t.due_date.strftime("%d %b %Y") if t.due_date else "-"
        rows.append([P("[x]" if t.done else "[ ]"), P(due), P(t.title)])
    story.append(table(rows, [14, 28, 132]))

    # ---- vendors ----
    story.append(Paragraph("Vendor checklist", h2))
    for v in plan.vendors:
        block = [P(f"{v.category}  |  {v.est_cost_range}  |  status: {v.status}", bold)]
        block += [P(f"- {q}", small) for q in v.what_to_ask]
        block.append(Spacer(1, 6))
        story.append(KeepTogether(block))

    # ---- ideas ----
    story.append(Paragraph("Ideas", h2))
    story += [P(f"- {idea}", small) for idea in plan.ideas]

    def footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawCentredString(A4[0] / 2, 10 * mm, f"AI Event Planner - page {doc.page}")
        canvas.restoreState()

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=18 * mm, title=f"{b.event_type.title()} plan")
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    return buf.getvalue()
