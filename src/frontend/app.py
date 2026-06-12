import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import streamlit as st
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(
    page_title="Media Sanity Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Auto-refresh every 5 minutes so the card updates after each pipeline run
# without the user having to reload manually.
from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=5 * 60 * 1000, key="pipeline_refresh")

# ─────────────────────────────────────────────────────────────
# THEME STATE
# ─────────────────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "system"

THEME_OPTIONS  = ["system", "dark", "light"]
THEME_EMOJIS   = ["⚙️", "🌙", "☀️"]

# ─────────────────────────────────────────────────────────────
# CSS — CSS variables + theme switching
# ─────────────────────────────────────────────────────────────
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

theme = st.session_state.theme

if theme == "light":
    root_vars = f":root {{ {LIGHT_VARS} }}"
elif theme == "dark":
    root_vars = f":root {{ {DARK_VARS} }}"
else:  # system
    root_vars = f"""
:root {{ {LIGHT_VARS} }}
@media (prefers-color-scheme: dark) {{ :root {{ {DARK_VARS} }} }}
"""

st.markdown(f"""
<style>
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
    margin: 1.8rem 0 0.6rem 0; padding-bottom: 0.6rem;
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
</style>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────
from datetime import timedelta
from sqlalchemy import func, select
from src.db.connection import get_session
from src.db.models import ArticleModel

@st.cache_data(ttl=60)
def load_articles():
    with get_session() as session:
        rows = list(session.scalars(
            select(ArticleModel)
            .where(ArticleModel.ragebait_score.isnot(None))
            .order_by(ArticleModel.scraped_at.desc())
        ))
        return [
            {
                "id":               str(r.id),
                "title":            r.title or "",
                "url":              r.url,
                "category":         r.category or "—",
                "word_count":       r.word_count or 0,
                "scraped_at":       r.scraped_at,
                "score_computed_at": r.score_computed_at,
                "ragebait_score":   r.ragebait_score,
                "pre_score":        r.pre_score,
                "details":          r.score_details or {},
                "judge_reasoning":  (r.score_details or {}).get("judge", {}).get("reasoning"),
                "judge_selected":   (r.score_details or {}).get("judge", {}).get("selected", False),
                "score_model":      r.score_model or "—",
                "score_version":    r.score_version or "—",
            }
            for r in rows
        ]

def pick_highlight(articles: list[dict]) -> dict | None:
    """
    Pick the most notable article to highlight.
    Relies exclusively on the judge LLM call:
    1. Judge-selected article in the latest batch (10-min window).
    2. Fallback: most recent judge-selected article in the last 24h.
    """
    scored = [a for a in articles if a["score_computed_at"] is not None]
    if not scored:
        return None

    latest_ts = max(a["score_computed_at"] for a in scored)
    batch    = [a for a in scored if a["score_computed_at"] >= latest_ts - timedelta(minutes=10)]
    last_24h = [a for a in scored if a["score_computed_at"] >= latest_ts - timedelta(hours=24)]

    # 1. Judge pick in latest batch
    judge_batch = [a for a in batch if a.get("judge_selected") and a.get("judge_reasoning")]
    if judge_batch:
        return judge_batch[0]

    # 2. Judge pick from last 24h
    judge_24h = [a for a in last_24h if a.get("judge_selected") and a.get("judge_reasoning")]
    if judge_24h:
        return max(judge_24h, key=lambda a: a["score_computed_at"])

    return None

@st.cache_data(ttl=60)
def load_batch_stats():
    with get_session() as session:
        latest_scored = session.scalar(
            select(func.max(ArticleModel.pre_score_at))
        )
        if not latest_scored:
            return {"total": 0, "batch_time": None}
        window_start = latest_scored - timedelta(minutes=75)
        batch_articles = list(session.scalars(
            select(ArticleModel).where(
                ArticleModel.pre_score_at >= window_start,
            )
        ))
        total = len(batch_articles)
        return {"total": total, "batch_time": latest_scored}

all_articles = load_articles()
batch_stats  = load_batch_stats()
latest       = pick_highlight(all_articles)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
import re

FIELD_LABELS = {
    "curiosity_gap":          "Curiosity Gap",
    "conflict_staging":       "Conflict Staging",
    "emotional_inflation":    "Emotional Inflation",
    "narrative_exploitation": "Narrative Exploitation",
}

def extract_verdict(reasoning: str) -> str:
    """For v8 reasoning (contains →): show only the verdict after the arrow.
    Falls back to full text for older versions that don't use this format."""
    if "→" in reasoning:
        return reasoning.split("→", 1)[1].strip()
    return reasoning

def format_reasoning(text: str) -> str:
    """Bold field name labels and add line breaks between reasoning sections."""
    for key, label in FIELD_LABELS.items():
        text = text.replace(f"{key}-", f"<strong>{label}:</strong> ")
        text = text.replace(key, label)
    # Insert line break only before field label headings (avoids false splits on dates like "28. Februar")
    text = re.sub(r'(\S)\s+(?=<strong>)', r'\1<br><br>', text)
    return text

def ragebait_color(score: float) -> str:
    """
    Green → yellow → red pastel gradient for scores 0–10.
    Anchors match the Chakra-UI 500-level palette so score 10
    renders as the existing --ragebait red (#E53E3E).
      1  → #38A169  (green-500)
      5  → #D69E2E  (yellow-600)
      10 → #E53E3E  (red-500)
    """
    t = max(0.0, min(10.0, float(score))) / 10.0
    GREEN  = (0x38, 0xA1, 0x69)
    YELLOW = (0xD6, 0x9E, 0x2E)
    RED    = (0xE5, 0x3E, 0x3E)
    if t <= 0.5:
        s = t / 0.5
        a, b_ = GREEN, YELLOW
    else:
        s = (t - 0.5) / 0.5
        a, b_ = YELLOW, RED
    r = int(a[0] + (b_[0] - a[0]) * s)
    g = int(a[1] + (b_[1] - a[1]) * s)
    b = int(a[2] + (b_[2] - a[2]) * s)
    return f"#{r:02X}{g:02X}{b:02X}"


def score_bar(val: float, color: str) -> str:
    pct = min(100, (val / 10) * 100)
    return (f'<div class="score-bar-wrap">'
            f'<div class="score-bar-fill" style="width:{pct:.0f}%;background:{color};"></div>'
            f'</div>')


# ─────────────────────────────────────────────────────────────
# HEADER + THEME TOGGLE
# ─────────────────────────────────────────────────────────────
col_title, col_toggle = st.columns([5, 1])

with col_title:
    st.markdown("""
<div style="margin-bottom:0.15rem;">
  <span style="font-size:1.4rem;font-weight:600;color:var(--text-primary);">Media Sanity Dashboard</span>
</div>
<div style="font-size:0.82rem;color:var(--text-secondary);margin-bottom:0.1rem;">
  Misst fabrizierte Emotion in Schweizer Nachrichtenmedien — stündlich aktualisiert.
</div>
<div style="font-size:0.65rem;color:var(--text-muted);">
  KI-generiert · keine menschliche Prüfung ·
  <a href="https://github.com/Riddmaker/-Ecosystem-Sanity-Stack/issues" target="_blank"
     style="color:var(--text-muted);text-decoration:underline;">Feedback via GitHub</a>
</div>
""", unsafe_allow_html=True)

with col_toggle:
    chosen = st.segmented_control(
        "Theme",
        THEME_EMOJIS,
        default=THEME_EMOJIS[THEME_OPTIONS.index(st.session_state.theme)],
        selection_mode="single",
        label_visibility="collapsed",
    )
    if chosen is not None:
        new_theme = THEME_OPTIONS[THEME_EMOJIS.index(chosen)]
        if new_theme != st.session_state.theme:
            st.session_state.theme = new_theme
            st.rerun()

with st.expander("Was misst dieses Dashboard?"):
    st.markdown("""
Dieses Werkzeug misst, ob der emotionale Gehalt eines Artikels aus den berichteten Fakten
entsteht — oder ob Hinweise auf sprachliche und strukturelle Muster vorliegen, die Klicks
und Empörung fördern können. Kein Urteil über Medien oder Journalist:innen, sondern ein
Instrument zur eigenen Orientierung.

**Ragebait Index (0–10, höher = schlechter):** Vier Dimensionen, je ein Sprachmodell-Aufruf.

**Curiosity Gap** (Blom & Hansen 2015) — Hält die Headline Kerninformationen zurück, um den Klick zu erzwingen?
**Conflict Staging** (Rony et al. 2017) — Konstruiert die Redaktion einen Gruppenkonflikt ohne Faktenbasis?
**Emotional Inflation** (Potthast et al. 2016) — Überwiegen emotionale Behauptungen gegenüber verifizierbaren Fakten?
**Narrative Exploitation** (Brady et al. 2017) — Wird eine Geschichte primär aufgegriffen, um Empörung auszulösen — ohne Handlungsbezug?

Fabrizierte Emotion hat messbare Kosten: Sie verzerrt die Wahrnehmung der Welt, baut eine falsche
Dringlichkeit auf und erschöpft mit der Zeit die Fähigkeit, auf echte Missstände zu reagieren
(McLaughlin et al. 2022, Crockett 2017). Ziel des Projekts ist ein bewussterer Medienkonsum.

*Sarkasmus und Satire werden gelegentlich falsch eingestuft. Code und Prompts sind Open Source (Apache 2.0).*
""")


# ─────────────────────────────────────────────────────────────
# ARTICLE HIGHLIGHT
# ─────────────────────────────────────────────────────────────
T1  = "var(--text-primary)"
T2  = "var(--text-secondary)"
T3  = "var(--text-muted)"
BD  = "var(--border)"
BDL = "var(--border-light)"

if latest:
    d  = latest["details"]
    ts = latest["scraped_at"].strftime("%d.%m.%Y %H:%M UTC") if latest["scraped_at"] else "—"

    rb_detail = d.get("ragebait", {})
    rb_score  = rb_detail.get("score", latest.get("ragebait_score") or 0)
    RB        = ragebait_color(rb_score)

    bs = batch_stats
    if bs["total"] > 0:
        batch_time_str = bs["batch_time"].strftime("%H:%M UTC") if bs["batch_time"] else "—"
        section_label = (
            f'Höchster Ragebait-Score im letzten Batch &nbsp;·&nbsp; '
            f'{bs["total"]} Artikel gescreent ({batch_time_str})'
            f'&nbsp;·&nbsp; Aktualisierung stündlich'
        )
    else:
        section_label = "Höchster Ragebait-Score"

    st.markdown(f'<div class="section-label">{section_label}</div>', unsafe_allow_html=True)

    DIMS = [
        ("ragebait", RB, "Ragebait Index", [
            ("curiosity_gap",          "Curiosity Gap"),
            ("conflict_staging",       "Conflict Staging"),
            ("emotional_inflation",    "Emotional Inflation"),
            ("narrative_exploitation", "Narrative Exploitation"),
        ]),
    ]

    # Shared cell styles
    C1 = f'padding:1rem 1rem 1rem 0;border-right:1px solid {BD};text-align:center;'
    C2 = f'padding:1rem 1.4rem;border-right:1px solid {BD};'
    C3 = f'padding:1rem 0 1rem 1.4rem;'
    ROW_BORDER = f'border-bottom:1px solid {BDL};'

    # Compact cell styles for the title row (less vertical padding)
    C1h = f'padding:0.5rem 1rem 0.5rem 0;border-right:1px solid {BD};text-align:center;'
    C2h = f'padding:0.5rem 1.4rem;border-right:1px solid {BD};'
    C3h = f'padding:0.5rem 0 0.5rem 1.4rem;'

    # ── Row 1: title | Begründung header
    row1 = (
        f'<div style="{C1h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">Scores</div>'
        f'</div>'
        f'<div style="{C2h}{ROW_BORDER}">'
        f'<div class="highlight-title">{latest["title"]}</div>'
        f'</div>'
        f'<div style="{C3h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">Begründung</div>'
        f'</div>'
    )

    # ── Rows 2 & 3: one per scoring dimension
    dim_rows = ""
    for i, (dk, c, lbl, subs) in enumerate(DIMS):
        dim_data  = d.get(dk, {})
        big_score = dim_data.get("score", latest.get("ragebait_score") or 0)

        is_last = (i == len(DIMS) - 1)
        row_border = "" if is_last else ROW_BORDER

        # Sub-score bars
        bars_html = (
            f'<div style="font-size:0.68rem;font-weight:600;color:{c};'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{lbl}</div>'
        )
        for sk, sl in subs:
            sv  = dim_data.get(sk, 0)
            sc  = ragebait_color(sv)
            bars_html += (
                f'<div class="sub-row">'
                f'<span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{sc};">{sv:.1f}</span>'
                f'</div>'
                + score_bar(sv, sc)
            )

        # Reasoning: per-sub-score blocks (v7) or combined fallback (v6)
        has_per_sub = any(dim_data.get(f"{sk}_reasoning") for sk, _ in subs)
        if has_per_sub:
            reasoning_html = ""
            for sk, sl in subs:
                sv = dim_data.get(sk, 0)
                sc = ragebait_color(sv)
                sr = dim_data.get(f"{sk}_reasoning", "")
                if sr:
                    reasoning_html += (
                        f'<div style="margin-bottom:0.75rem;">'
                        f'<div style="font-size:var(--fs-meta);font-weight:600;color:{sc};'
                        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">{sl}</div>'
                        f'<div class="reasoning-text">{extract_verdict(sr)}</div>'
                        f'</div>'
                    )
        else:
            reasoning_html = (
                f'<div class="reasoning-text">'
                f'{format_reasoning(dim_data.get("reasoning", "—"))}'
                f'</div>'
            )

        dim_rows += (
            f'<div style="{C1}{row_border}vertical-align:top;">'
            f'<div style="font-size:0.68rem;font-weight:600;color:{c};'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">'
            f'Ragebait</div>'
            f'<div style="font-size:3rem;font-weight:600;line-height:1;color:{c};">'
            f'{big_score:.1f}</div>'
            f'</div>'
            f'<div style="{C2}{row_border}">{bars_html}</div>'
            f'<div style="{C3}{row_border}">{reasoning_html}</div>'
        )

    # ── Row 4: meta footer
    row4 = (
        f'<div style="{C1}display:flex;flex-direction:column;justify-content:center;padding-top:0.8rem;padding-bottom:0.8rem;">'
        f'<div><span class="tag">{latest["category"]}</span>'
        f'<span class="tag">{latest["word_count"]}w</span></div>'
        f'<div style="font-size:0.65rem;color:{T3};margin-top:0.4rem;">{ts}</div>'
        f'</div>'
        f'<div style="{C2}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;"></div>'
        f'<div style="{C3}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;font-size:0.68rem;color:{T3};">'
        f'{latest["score_model"]} &nbsp;·&nbsp; {latest["score_version"]}'
        f'&nbsp;&nbsp;<a href="{latest["url"]}" target="_blank" '
        f'style="color:{RB};text-decoration:none;font-weight:500;">Artikel öffnen ↗</a>'
        f'</div>'
    )

    st.markdown(
        f'<div class="highlight-wrap">'
        f'<div style="display:grid;grid-template-columns:110px 1fr 1fr;gap:0;">'
        f'{row1}{dim_rows}{row4}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

    # ── Reader service ──
    reader_service = d.get("reader_service")
    if reader_service:
        facts  = reader_service.get("facts", "").strip()
        stake  = reader_service.get("stake", "").strip()
        action = reader_service.get("action", "").strip()

        facts_cell = (
            f'<div class="reader-service-cell">'
            f'<div class="reader-service-cell-label">Was bekannt ist</div>'
            f'{facts}'
            f'</div>'
        ) if facts else ""

        stake_cell = (
            f'<div class="reader-service-cell">'
            f'<div class="reader-service-cell-label">Was auf dem Spiel steht</div>'
            f'{stake}'
            f'</div>'
        ) if stake else ""

        action_cell = (
            f'<div class="reader-service-cell" style="grid-column:1/-1;'
            f'border-top:1px solid var(--border);border-right:none;">'
            f'<div class="reader-service-cell-label">Was du tun kannst</div>'
            f'{action}'
            f'</div>'
        ) if action else ""

        body_cols = f'<div class="reader-service-body">{facts_cell}{stake_cell}{action_cell}</div>'

        st.markdown(
            f'<div class="reader-service-wrap">'
            f'<div class="reader-service-header">Kern des Themas</div>'
            f'{body_cols}'
            f'</div>',
            unsafe_allow_html=True,
        )


else:
    st.markdown(
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;">'
        f'Kein Ragebait-Kandidat gefunden — Pipeline ausführen oder Threshold prüfen.</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# SEGMENTED CONTROL OVERRIDE — injected late so it wins over
# Streamlit's own component CSS (later in cascade = higher priority)
# Only needed for explicit light/dark; system mode is handled by
# the media-query in root_vars above.
# ─────────────────────────────────────────────────────────────
if theme == "light":
    _btn_override = """
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
elif theme == "dark":
    _btn_override = """
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
else:
    _btn_override = ""  # system: handled by CSS variables + media query above

# Always render — even empty — so DOM structure stays identical across theme switches
st.markdown(f"<style>{_btn_override}</style>", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# RESEARCH FOOTER
# ─────────────────────────────────────────────────────────────
with st.expander("Wissenschaftliche Grundlagen"):
    st.markdown("""
<div class="research-footer">

  <div style="font-size:0.68rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;
              letter-spacing:0.06em;margin-bottom:0.6rem;">Wissenschaftliche Grundlagen</div>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin-bottom:0.3rem;">Scoring-Grundlage</div>

  <a href="https://doi.org/10.1080/17512786.2014.976939" target="_blank">
    Blom &amp; Hansen (2015) — Click bait: Forward-reference as lure in online news headlines
  </a>
  <span style="color:var(--text-muted);">
    — Headlines die Informationen absichtlich zurückhalten um Klicks zu erzwingen (Forward-reference).
    Grundlage für <em>Curiosity Gap</em>.
  </span><br>

  <a href="https://doi.org/10.1145/3091478.3091487" target="_blank">
    Rony, Hassan &amp; Yousuf (2017) — Diving Deep into Clickbaits
  </a>
  <span style="color:var(--text-muted);">
    — Engagement Farming durch Controversy Manufacturing: Gruppen werden ohne sachliche Basis
    gegeneinander aufgestellt um Kommentare zu ernten.
    Grundlage für <em>Conflict Staging</em>.
  </span><br>

  <a href="https://doi.org/10.1007/978-3-319-30671-1_72" target="_blank">
    Potthast et al. (2016) — Clickbait Detection
  </a>
  <span style="color:var(--text-muted);">
    — Clickbait korreliert mit hohem Verhältnis emotionaler Adjektive zu verifizierbaren Fakten.
    Grundlage für <em>Emotional Inflation</em>.
  </span><br>

  <a href="https://doi.org/10.1073/pnas.1618923114" target="_blank">
    Brady et al. (2017) — Emotion shapes the diffusion of moralized content in social networks
  </a>
  <span style="color:var(--text-muted);">
    — Moralisch-emotionale Sprache erhöht die Verbreitung von Inhalten in sozialen Netzwerken messbar.
    Geschichten werden primär deshalb aufgegriffen, um moralische Empörung auszulösen — unabhängig
    vom Informationswert. Grundlage für <em>Narrative Exploitation</em>.
  </span>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin:0.7rem 0 0.3rem 0;">Warum das wichtig ist</div>

  <a href="https://doi.org/10.1080/10410236.2022.2106086" target="_blank">
    McLaughlin, Gotlieb &amp; Mills (2022) — Problematic News Consumption
  </a>
  <span style="color:var(--text-muted);">
    — Problematischer Nachrichtenkonsum korreliert mit Angst, Depression und Schlafstörungen.
    Mit der Zeit müssen wir immer mehr Energie aufwenden, um nicht noch mehr zu konsumieren.
  </span><br>

  <a href="https://doi.org/10.1002/smi.916" target="_blank">
    McNaughton-Cassill &amp; Smith (2002) — Optimism Gap
  </a>
  <span style="color:var(--text-muted);">
    — Nachrichtenkonsument:innen überschätzen nationale Bedrohungen systematisch gegenüber
    der eigenen Lebenserfahrung. Warum emotionale Inflation die Weltwahrnehmung verzerrt.
  </span><br>

  <a href="https://doi.org/10.1038/s41562-017-0213-3" target="_blank">
    Crockett (2017) — Moral Outrage in the Digital Age
  </a>
  <span style="color:var(--text-muted);">
    — Near-zero cost of online outrage führt zu Habituation und Moral Licensing:
    Online-Empörung ersetzt echtes Handeln. Warum fabrizierte Empörung moralische
    Handlungskapazität aufbraucht.
  </span>

  <div style="margin-top:1rem;padding-top:0.8rem;border-top:1px solid var(--border-light);
              font-size:0.68rem;color:var(--text-muted);line-height:1.7;">
    <strong style="color:var(--text-secondary);">Zur Einordnung:</strong>
    Alle Studien sind peer-reviewed und in ihren Fachgebieten etabliert. Methodisch bewegen sie
    sich mehrheitlich auf der Ebene von Beobachtungs- und Querschnittsstudien — geeignet für
    Muster- und Korrelationsaussagen, nicht für Kausalaussagen. Crockett (2017) ist ein
    theoretisches Synthesepapier (<em>Perspective</em>), keine Primärstudie. McLaughlin et al.
    (2022) wurde 2024 repliziert, was die Befunde stärkt. Eine übergreifende Metaanalyse
    die speziell fabrizierte Emotion in Nachrichten und ihre psychologischen Kosten verbindet,
    liegt bisher nicht vor — das Themenfeld ist zu jung und zu spezifisch.
  </div>

</div>
""", unsafe_allow_html=True)

