"""Accessibility patch. Run ONCE from your project root:   python apply_a11y.py

It edits your own app.py, ui/style.css and README.md in place, skips anything already applied,
and adds a GitHub Actions workflow that runs your tests. Commit the result afterwards.
"""
from pathlib import Path

# ---- app.py: semantic HTML, an h1 on the plan page, a text alternative for the chart ----
APP_PAIRS = [
    ('<div class="hero"><div class="hero-label">', '<section class="hero" aria-labelledby="app-title"><div class="hero-label">'),
    ("<h1>🎉 AI Event Planning Assistant</h1>", '<h1 id="app-title"><span aria-hidden="true">🎉</span> AI Event Planning Assistant</h1>'),
    ("creative ideas with AI.</p></div>", "creative ideas with AI.</p></section>"),
    ('<div class="section-heading">Everything you need to plan</div>', '<h2 class="section-heading">Everything you need to plan</h2>'),
    ('<div class="section-heading">Need some inspiration?</div>', '<h2 class="section-heading">Need some inspiration?</h2>'),
    ('<div class="feature-card"><div class="feature-icon">{icon}</div>', '<article class="feature-card"><div class="feature-icon" aria-hidden="true">{icon}</div>'),
    ('<div class="feature-title">{title}</div>', '<h3 class="feature-title">{title}</h3>'),
    ('<div class="feature-description">{text}</div></div>', '<p class="feature-description">{text}</p></article>'),
    ("st.subheader(f\"{EMOJI.get(b.event_type", "st.title(f\"{EMOJI.get(b.event_type"),
    ('st.bar_chart(df.set_index("Category")["Amount (₹)"])',
     'st.bar_chart(df.set_index("Category")["Amount (₹)"])\n'
     '    st.caption("Bar chart of the rupee amount for each budget category. The table above lists the same values.")'),
]

# ---- CSS: contrast fixes (WCAG AA, 4.5:1) ----
CSS_PAIRS = [
    ("#657188", "#5a667c"),                                              # placeholder 4.19 -> 4.94 : 1
    ("#5145bd 58%, #8174ed 100%", "#5145bd 58%, #6a5fe0 100%"),          # hero gradient end 3.71 -> 4.85 : 1
    ("linear-gradient(135deg, #5145bd, #7468e8)", "linear-gradient(135deg, #5145bd, #6a5fe0)"),  # 4.30 -> 4.85 : 1
    ("background: rgba(255,255,255,0.08);", "background: rgba(255,255,255,0.04);"),
]
CSS_MARKER = "/* Accessibility (patch)"
CSS_BLOCK = '''

/* Accessibility (patch): headings, visible keyboard focus, reduced motion */
h2.section-heading { padding: 0; }
h3.feature-title { padding: 0; margin: 0 0 10px; }
p.feature-description { margin: 0; }
.stApp h1 { font-size: clamp(1.6rem, 2.6vw, 2.3rem); letter-spacing: -.5px; }
.stApp .hero h1 { font-size: clamp(1.8rem, 3vw, 2.7rem); letter-spacing: -1.2px; }
:focus-visible, button:focus-visible, input:focus-visible, textarea:focus-visible,
[role="tab"]:focus-visible, [data-baseweb="select"]:focus-within { outline: 3px solid #302c77 !important; outline-offset: 2px; }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { transition: none !important; animation: none !important; scroll-behavior: auto !important; }
  .feature-card:hover, .stButton > button:hover, [data-testid="stFormSubmitButton"] > button:hover { transform: none !important; }
}
'''

README_SECTION = '''## Accessibility

- Text and button colours meet WCAG AA contrast (4.5:1 or better): body text 13.3:1, secondary text 5.4:1,
  placeholders 4.9:1, white text on primary buttons 4.8:1 or better. Ratios were calculated, not guessed.
- Visible keyboard focus outline on every control, and all controls are at least 44 px tall.
- Semantic headings (one `h1`, `h2` sections, `h3` cards); decorative emoji are hidden from screen readers.
- Respects the "reduce motion" setting.
- The budget chart has a text alternative (the table plus a caption).
- Not yet tested with a screen reader.

'''

CI = '''name: tests
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python -m pytest -q          # tests use a fake AI: no API key or internet needed
'''


def patch_text(text, pairs):
    changed = 0
    for old, new in pairs:
        if new in text:
            continue                                   # already applied
        if old in text:
            text = text.replace(old, new)
            changed += 1
        else:
            print(f"   [warn] not found, skipped: {old[:55]!r}")
    return text, changed


def main(root="."):
    root = Path(root)

    app = root / "app.py"
    if app.exists():
        s, n = patch_text(app.read_text(encoding="utf-8"), APP_PAIRS)
        app.write_text(s, encoding="utf-8")
        print(f"app.py: {n} change(s)")
    else:
        print("app.py not found. Run this from your project root.")

    css = root / "ui" / "style.css"
    if css.exists():
        s, n = patch_text(css.read_text(encoding="utf-8"), CSS_PAIRS)
        if CSS_MARKER not in s:
            s += CSS_BLOCK
            n += 1
        css.write_text(s, encoding="utf-8")
        print(f"ui/style.css: {n} change(s)")
    else:
        print("ui/style.css not found, skipped")

    readme = root / "README.md"
    if readme.exists():
        s = readme.read_text(encoding="utf-8")
        if "## Accessibility" not in s:
            marker = "## Limitations (honest notes)"
            s = s.replace(marker, README_SECTION + marker, 1) if marker in s else s.rstrip() + "\n\n" + README_SECTION
            readme.write_text(s, encoding="utf-8")
            print("README.md: added Accessibility section")
        else:
            print("README.md: already has an Accessibility section")

    wf = root / ".github" / "workflows" / "tests.yml"
    if not wf.exists():
        wf.parent.mkdir(parents=True, exist_ok=True)
        wf.write_text(CI, encoding="utf-8")
        print(".github/workflows/tests.yml: created")

    print("Done. Restart Streamlit, then commit and push.")


if __name__ == "__main__":
    main()
