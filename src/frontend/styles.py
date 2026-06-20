"""
CSS and theme definitions for the dashboard.

Pure string-building — no Streamlit imports, so it stays unit-testable.
"""

THEME_OPTIONS = ["system", "dark", "light"]
THEME_EMOJIS  = ["⚙️", "🌙", "☀️"]

LIGHT_VARS = """
  --bg:               #F8F9FA;
  --bg-card:          #FFFFFF;
  --text-primary:     #1A202C;
  --text-secondary:   #718096;
  --text-muted:       #A0AEC0;
  --border:           #E2E8F0;
  --border-light:     #EDF2F7;
  --tag-bg:           #EDF2F7;
  --tag-color:        #4A5568;
  --ragebait:         #E53E3E;
  --bar-track:        #EDF2F7;
"""

DARK_VARS = """
  --bg:               #0F1117;
  --bg-card:          #1A1D2E;
  --text-primary:     #E2E8F0;
  --text-secondary:   #94A3B8;
  --text-muted:       #64748B;
  --border:           #2D3748;
  --border-light:     #1E293B;
  --tag-bg:           #2D3748;
  --tag-color:        #CBD5E0;
  --ragebait:         #FC8181;
  --bar-track:        #2D3748;
"""


def base_css(theme: str) -> str:
    """Full <style> body for the given theme ("system" | "dark" | "light")."""
    if theme == "light":
        root_vars = f":root {{ {LIGHT_VARS} }}"
    elif theme == "dark":
        root_vars = f":root {{ {DARK_VARS} }}"
    else:  # system
        root_vars = f"""
:root {{ {LIGHT_VARS} }}
@media (prefers-color-scheme: dark) {{ :root {{ {DARK_VARS} }} }}
"""

    return f"""
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap');

{root_vars}

:root {{
  --fs-body:  0.82rem;
  --fs-label: 0.72rem;
  --fs-meta:  0.65rem;
}}

html, body,
[data-testid="stAppViewContainer"],
[data-testid="stApp"],
[data-testid="stHeader"],
.stApp, section.main, .main > div,
[class*="css"] {{
    background-color: var(--bg) !important;
    color: var(--text-primary) !important;
    font-family: 'Inter', system-ui, sans-serif;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.block-container {{ padding: 2rem 2.5rem 4rem 2.5rem; max-width: 1400px; }}

/* Expanders get the same top gap as the cards (reader-service-wrap margin),
   so the "Wissenschaftliche Grundlagen" footer doesn't stick to the last card. */
[data-testid="stExpander"] {{ margin-top: 1.2rem; }}

/* ── Theme toggle (segmented_control) ── */
/* Unselected buttons */
[data-testid="stBaseButton-segmented_control"] {{
    background: var(--bg-card) !important;
    color: var(--text-primary) !important;
    border-color: var(--border) !important;
}}
[data-testid="stBaseButton-segmented_control"]:hover {{
    background: var(--border-light) !important;
}}
/* Selected button */
[data-testid="stBaseButton-segmented_controlActive"] {{
    background: var(--border-light) !important;
    border-color: var(--ragebait) !important;
    color: var(--text-primary) !important;
}}

/* ── Score bar ── */
.score-bar-wrap {{
    background: var(--bar-track); border-radius: 2px;
    height: 4px; width: 100%; margin: 3px 0 8px 0;
}}
.score-bar-fill {{ height: 100%; border-radius: 2px; }}

/* ── Article highlight ── */
.highlight-wrap {{
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    box-shadow: 0 1px 3px rgba(0,0,0,0.12);
    padding: 1.5rem 1.8rem;
    margin-top: 0.5rem;
}}
.highlight-title {{
    font-size: 1.05rem; font-weight: 600;
    color: var(--text-primary); line-height: 1.45; margin-bottom: 0.6rem;
}}
.sub-label {{ font-size: var(--fs-meta); color: var(--text-secondary); }}
.sub-score-val {{ font-size: var(--fs-body); font-weight: 600; }}
.sub-row {{ display:flex; justify-content:space-between; align-items:baseline; margin: 3px 0; }}
.reasoning-text {{
    font-size: var(--fs-body); color: var(--text-secondary); line-height: 1.6;
    border-left: 3px solid var(--border-light); padding-left: 12px;
}}
.tag {{
    font-size: var(--fs-meta); background: var(--tag-bg); color: var(--tag-color);
    border-radius: 4px; padding: 2px 8px; margin-right: 4px;
    display: inline-block;
}}
.section-label {{
    font-size: var(--fs-label); font-weight: 600; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin: 0 0 0.6rem 0; padding-bottom: 0.6rem;
    border-bottom: 1px solid var(--border);
}}

/* ── Reader service card ── */
.reader-service-wrap {{
    margin-top: 1.2rem;
    background: var(--bg-card);
    border: 1px solid var(--border);
    border-radius: 8px;
    overflow: hidden;
}}
.reader-service-header {{
    padding: 0.6rem 1.1rem;
    border-bottom: 1px solid var(--border);
    font-size: var(--fs-label); font-weight: 600;
    color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.06em;
}}
.reader-service-body {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 0;
}}
.reader-service-cell {{
    padding: 0.9rem 1.1rem;
    border-right: 1px solid var(--border);
    font-size: var(--fs-body); color: var(--text-secondary); line-height: 1.6;
}}
.reader-service-cell:last-child {{ border-right: none; }}
.reader-service-cell-label {{
    font-size: var(--fs-meta); font-weight: 600;
    color: var(--text-muted);
    text-transform: uppercase; letter-spacing: 0.05em;
    margin-bottom: 0.3rem;
}}

/* ── Quadrant legend ── */
.quadrant-item {{
    font-size: 0.7rem; color: var(--text-secondary);
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 12px;
}}

/* ── Research footer ── */
.research-footer {{
    margin-top: 1.2rem; padding-top: 1.2rem; border-top: 1px solid var(--border);
    font-size: 0.7rem; color: var(--text-muted); line-height: 2.2;
}}
.research-footer a {{ color: var(--text-muted); text-decoration: none; }}
.research-footer a:hover {{ color: var(--text-secondary); }}
"""


def segmented_control_override(theme: str) -> str:
    """
    Late-injected override so it wins over Streamlit's own component CSS
    (later in cascade = higher priority). Only needed for explicit
    light/dark; system mode is handled by the media query in base_css().
    Returns "" for system — render it anyway so the DOM structure stays
    identical across theme switches.
    """
    if theme == "light":
        return """
[data-testid="stBaseButton-segmented_control"] {
    background-color: #FFFFFF !important;
    color: #1A202C !important;
    border-color: #E2E8F0 !important;
}
[data-testid="stBaseButton-segmented_control"]:hover {
    background-color: #EDF2F7 !important;
}
[data-testid="stBaseButton-segmented_controlActive"] {
    background-color: #EDF2F7 !important;
    border-color: #E53E3E !important;
    color: #1A202C !important;
}"""
    if theme == "dark":
        return """
[data-testid="stBaseButton-segmented_control"] {
    background-color: #1A1D2E !important;
    color: #E2E8F0 !important;
    border-color: #2D3748 !important;
}
[data-testid="stBaseButton-segmented_control"]:hover {
    background-color: #1E293B !important;
}
[data-testid="stBaseButton-segmented_controlActive"] {
    background-color: #1E293B !important;
    border-color: #E53E3E !important;
    color: #E2E8F0 !important;
}"""
    return ""
