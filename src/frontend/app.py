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
  --weight:           #3182CE;
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
  --weight:           #63B3ED;
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
.sub-label {{ font-size: 0.68rem; color: var(--text-secondary); }}
.sub-score-val {{ font-size: 0.82rem; font-weight: 600; }}
.sub-row {{ display:flex; justify-content:space-between; align-items:baseline; margin: 3px 0; }}
.reasoning-text {{
    font-size: 0.75rem; color: var(--text-secondary); line-height: 1.65;
    border-left: 3px solid var(--border-light); padding-left: 12px;
}}
.tag {{
    font-size: 0.68rem; background: var(--tag-bg); color: var(--tag-color);
    border-radius: 4px; padding: 2px 8px; margin-right: 4px;
    display: inline-block;
}}
.section-label {{
    font-size: 0.72rem; font-weight: 600; color: var(--text-secondary);
    text-transform: uppercase; letter-spacing: 0.06em;
    margin: 1.8rem 0 0.6rem 0; padding-bottom: 0.6rem;
    border-bottom: 1px solid var(--border);
}}

/* ── Quadrant legend ── */
.quadrant-item {{
    font-size: 0.7rem; color: var(--text-secondary);
    background: var(--bg-card); border: 1px solid var(--border);
    border-radius: 6px; padding: 6px 12px;
}}

/* ── Research footer ── */
.research-footer {{
    margin-top: 3rem; padding-top: 1.2rem; border-top: 1px solid var(--border);
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
from src.db.connection import build_engine, get_session
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
                "emotional_weight": r.emotional_weight,
                "pre_score":        r.pre_score,
                "details":          r.score_details or {},
                "score_model":      r.score_model or "—",
                "score_version":    r.score_version or "—",
            }
            for r in rows
        ]

def pick_highlight(articles: list[dict]) -> dict | None:
    """
    From the latest scoring batch (articles scored within 10 min of the most
    recent score_computed_at), return the one with the highest
    ragebait - emotional_weight discrepancy.
    """
    scored = [a for a in articles if a["score_computed_at"] is not None]
    if not scored:
        return None
    latest_ts = max(a["score_computed_at"] for a in scored)
    window_start = latest_ts - timedelta(minutes=10)
    batch = [a for a in scored if a["score_computed_at"] >= window_start]
    return max(batch, key=lambda a: (a["ragebait_score"] or 0) - (a["emotional_weight"] or 0))

@st.cache_data(ttl=60)
def load_batch_stats():
    with get_session() as session:
        latest_scraped = session.scalar(
            select(func.max(ArticleModel.scraped_at)).where(ArticleModel.pre_score.isnot(None))
        )
        if not latest_scraped:
            return {"total": 0, "flagged": 0, "batch_time": None}
        window_start = latest_scraped - timedelta(minutes=75)
        batch_articles = list(session.scalars(
            select(ArticleModel).where(
                ArticleModel.pre_score.isnot(None),
                ArticleModel.scraped_at >= window_start,
            )
        ))
        total   = len(batch_articles)
        flagged = sum(1 for a in batch_articles if (a.pre_score or 0) >= 5.0)
        return {"total": total, "flagged": flagged, "batch_time": latest_scraped}

all_articles = load_articles()
batch_stats  = load_batch_stats()
latest       = pick_highlight(all_articles)


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
import re

FIELD_LABELS = {
    "curiosity_gap":       "Curiosity Gap",
    "conflict_staging":    "Conflict Staging",
    "emotional_inflation": "Emotional Inflation",
    "topic_gravity":       "Topic Gravity",
    "emotional_exposure":  "Emotional Exposure",
    "reader_burden":       "Reader Burden",
}

def format_reasoning(text: str) -> str:
    """Bold field name labels and add line breaks between reasoning sections."""
    for key, label in FIELD_LABELS.items():
        text = text.replace(f"{key}-", f"<strong>{label}:</strong> ")
        text = text.replace(key, label)
    # Insert line break only before field label headings (avoids false splits on dates like "28. Februar")
    text = re.sub(r'(\S)\s+(?=<strong>)', r'\1<br><br>', text)
    return text

def score_bar(val, css_var):
    pct = min(100, (val / 10) * 100)
    return (f'<div class="score-bar-wrap">'
            f'<div class="score-bar-fill" style="width:{pct:.0f}%;background:{css_var};"></div>'
            f'</div>')


# ─────────────────────────────────────────────────────────────
# HEADER + THEME TOGGLE
# ─────────────────────────────────────────────────────────────
col_title, col_toggle = st.columns([5, 1])

with col_title:
    st.markdown("""
<div style="margin-bottom:0.4rem;">
  <span style="font-size:1.4rem;font-weight:600;color:var(--text-primary);">Media Sanity Dashboard</span>
</div>
<div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.8rem;max-width:680px;line-height:1.6;">
  Fabrizierte Emotion in Nachrichten hat messbare Kosten: Sie verzerrt die Wahrnehmung
  der Welt, baut eine falsche Dringlichkeit auf — und erschöpft mit der Zeit die Fähigkeit,
  auf echte Missstände zu reagieren. Wer diesen Inhalt bewusst konsumiert, zahlt trotzdem —
  denn es braucht mit der Zeit immer mehr Energie, nicht noch mehr davon zu konsumieren.
  <span style="display:block;margin-top:0.5rem;">
  Dieses Werkzeug misst, ob der emotionale Gehalt eines Artikels aus den berichteten Fakten
  entsteht — oder ob Hinweise auf sprachliche und strukturelle Muster vorliegen, die Klicks
  und Empörung fördern können. Kein Urteil über Medien oder Journalist:innen, sondern ein
  Instrument zur eigenen Orientierung.
  <span style="display:block;margin-top:0.5rem;font-weight:600;color:var(--text-primary);">
  Dieses Instrument veranschaulicht ein Framework das sich direkt auf den eigenen Medienkonsum
  übertragen lässt — es gibt ein Bewertungsraster an die Hand, mit dem sich auch im Alltag
  jeder Artikel selbst einordnen lässt. Das Ziel des Projektes ist es, einen bewussteren Medienkonsum zu fördern.
  </span>
  <span style="display:block;margin-top:0.2rem;">Wissenschaftliche Grundlagen ganz unten auf der Seite.</span>
  </span>
  <span style="display:block;margin-top:0.6rem;color:var(--text-muted);line-height:1.7;">
  Alle Bewertungen werden automatisiert durch ein Sprachmodell erstellt — ohne menschliche
  Prüfung. Das Modell bewertet ausschliesslich die sprachliche und strukturelle Architektur
  des Textes, nicht den Wahrheitsgehalt der Aussagen. Sarkasmus und Satire werden dabei
  aktuell manchmal fälschlicherweise als Conflict Staging interpretiert.
  Der Code und die Bewertungs-Prompts sind quelloffen unter der Apache-2.0-Lizenz einsehbar. Bei wahrgenommenen Fehlurteilen, fehlenden Nuancen oder Kritik an den Prompts
  ist Feedback via
  <a href="https://github.com/Riddmaker/-Ecosystem-Sanity-Stack/issues" target="_blank"
     style="color:var(--text-muted);text-decoration:underline;">GitHub Issues</a>
  jederzeit willkommen.
  </span>
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


# ─────────────────────────────────────────────────────────────
# ARTICLE HIGHLIGHT
# ─────────────────────────────────────────────────────────────
# CSS var references used in inline styles so theme switching works
RB  = "var(--ragebait)"
EW  = "var(--weight)"
T1  = "var(--text-primary)"
T2  = "var(--text-secondary)"
T3  = "var(--text-muted)"
BD  = "var(--border)"
BDL = "var(--border-light)"

if latest:
    d  = latest["details"]
    ts = latest["scraped_at"].strftime("%d.%m.%Y %H:%M UTC") if latest["scraped_at"] else "—"

    rb_detail = d.get("ragebait", {})
    ew_detail = d.get("emotional_weight", {})
    rb_score  = rb_detail.get("score", latest.get("ragebait_score") or 0)
    ew_score  = ew_detail.get("score", latest.get("emotional_weight") or 0)

    bs = batch_stats
    discrepancy = (latest.get("ragebait_score") or 0) - (latest.get("emotional_weight") or 0)
    if bs["total"] > 0:
        batch_time_str = bs["batch_time"].strftime("%H:%M UTC") if bs["batch_time"] else "—"
        section_label = (
            f'Höchste Ragebait-Diskrepanz im letzten Batch &nbsp;·&nbsp; '
            f'{bs["flagged"]} von {bs["total"]} Artikeln vorläufig markiert ({batch_time_str})'
            f' &nbsp;·&nbsp; Diskrepanz: {discrepancy:+.1f}'
        )
    else:
        section_label = "Höchste Ragebait-Diskrepanz"

    st.markdown(f'<div class="section-label">{section_label}</div>', unsafe_allow_html=True)

    DIMS = [
        ("ragebait", RB, "Ragebait Index", [
            ("curiosity_gap",       "Curiosity Gap"),
            ("conflict_staging",    "Conflict Staging"),
            ("emotional_inflation", "Emotional Inflation"),
        ]),
        ("emotional_weight", EW, "Emotionales Gewicht", [
            ("topic_gravity",      "Topic Gravity"),
            ("emotional_exposure", "Emotional Exposure"),
            ("reader_burden",      "Reader Burden"),
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
        big_score = dim_data.get("score", latest.get(
            "ragebait_score" if dk == "ragebait" else "emotional_weight") or 0)
        reasoning = format_reasoning(d.get(dk, {}).get("reasoning", "—"))

        is_last = (i == len(DIMS) - 1)
        row_border = "" if is_last else ROW_BORDER

        # Sub-score bars
        bars_html = (
            f'<div style="font-size:0.68rem;font-weight:600;color:{c};'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{lbl}</div>'
        )
        for sk, sl in subs:
            sv = dim_data.get(sk, 0)
            bars_html += (
                f'<div class="sub-row">'
                f'<span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{c};">{sv:.1f}</span>'
                f'</div>'
                + score_bar(sv, c)
            )

        dim_rows += (
            f'<div style="{C1}{row_border}vertical-align:top;">'
            f'<div style="font-size:0.68rem;font-weight:600;color:{c};'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">'
            f'{"Ragebait" if dk == "ragebait" else "Gewicht"}</div>'
            f'<div style="font-size:3rem;font-weight:600;line-height:1;color:{c};">'
            f'{big_score:.1f}</div>'
            f'</div>'
            f'<div style="{C2}{row_border}">{bars_html}</div>'
            f'<div style="{C3}{row_border}">'
            f'<div class="reasoning-text">{reasoning}</div>'
            f'</div>'
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

    RB_S = "color:var(--ragebait);font-weight:700;"
    EW_S = "color:var(--weight);font-weight:700;"
    SEP  = f'<span style="color:{BD};margin:0 0.7rem;">·</span>'
    st.markdown(
        # ── Legend ──
        f'<div style="display:flex;align-items:center;flex-wrap:wrap;'
        f'margin-top:0.6rem;font-size:0.78rem;color:{T2};gap:0;">'
        f'<span><span style="{RB_S}">↓</span><span style="{EW_S}">↓</span>'
        f'&nbsp;Sachlicher Artikel</span>{SEP}'
        f'<span><span style="{RB_S}">↓</span><span style="{EW_S}">↑</span>'
        f'&nbsp;Authentische Schwere</span>{SEP}'
        f'<span><span style="{RB_S}">↑</span><span style="{EW_S}">↓</span>'
        f'&nbsp;Zuspitzung ohne Substanz</span>{SEP}'
        f'<span><span style="{RB_S}">↑</span><span style="{EW_S}">↑</span>'
        f'&nbsp;Leid als Engagement-Aufhänger</span>'
        f'</div>'
        # ── Score definitions ──
        f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:1rem;margin-top:1.1rem;">'
        f'<div style="font-size:0.75rem;color:{T2};line-height:1.65;">'
        f'<span style="{RB_S}font-size:0.72rem;text-transform:uppercase;'
        f'letter-spacing:0.05em;">Ragebait Index</span>'
        f'<span style="color:{T3};font-size:0.72rem;"> — 0 bis 10, höher = schlechter</span><br>'
        f'Misst, ob der emotionale Gehalt eines Artikels aus den berichteten Fakten entsteht '
        f'— oder ob Hinweise auf sprachliche und strukturelle Muster vorliegen, '
        f'die zur Erzeugung von Klicks und Empörung eingesetzt werden können. '
        f'Tiefe Werte bedeuten authentische Berichterstattung. '
        f'Hohe Werte weisen auf fabrizierte Emotion hin.'
        f'</div>'
        f'<div style="font-size:0.75rem;color:{T2};line-height:1.65;">'
        f'<span style="{EW_S}font-size:0.72rem;text-transform:uppercase;'
        f'letter-spacing:0.05em;">Emotionales Gewicht</span>'
        f'<span style="color:{T3};font-size:0.72rem;"> — 0 bis 10, neutral</span><br>'
        f'Misst, wie schwer ein Artikel emotional zu verarbeiten ist — unabhängig davon, '
        f'ob das gerechtfertigt ist. Kein Qualitätsurteil. '
        f'Hohe Werte bei niedrigem Ragebait signalisieren authentisch schwere Nachrichten. '
        f'Hohe Werte bei hohem Ragebait deuten auf Instrumentalisierung realer Schwere hin.'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

else:
    st.markdown(
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;">'
        f'Noch keine analysierten Artikel — run_pipeline.py ausführen.</div>',
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
st.markdown("""
<div class="research-footer">

  <div style="font-size:0.68rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;
              letter-spacing:0.06em;margin-bottom:0.6rem;">Wissenschaftliche Grundlage</div>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin-bottom:0.3rem;">Scoring-Grundlage</div>

  <a href="https://doi.org/10.1080/17512786.2014.976939" target="_blank">
    Blom &amp; Hansen (2015) — Click bait: Forward-reference as lure in online news headlines
  </a>
  <span style="color:var(--text-muted);">
    — Headlines die Informationen absichtlich zurückhalten um Klicks zu erzwingen (Forward-reference).
    Grundlage für <em>Curiosity Gap</em>.
  </span><br>

  <a href="https://doi.org/10.1007/978-3-319-30671-1_72" target="_blank">
    Potthast et al. (2016) — Clickbait Detection
  </a>
  <span style="color:var(--text-muted);">
    — Clickbait korreliert mit hohem Verhältnis emotionaler Adjektive zu verifizierbaren Fakten.
    Grundlage für <em>Emotional Inflation</em>.
  </span><br>

  <a href="https://doi.org/10.1145/3091478.3091487" target="_blank">
    Rony, Hassan &amp; Yousuf (2017) — Diving Deep into Clickbaits
  </a>
  <span style="color:var(--text-muted);">
    — Engagement Farming durch Controversy Manufacturing: Gruppen werden ohne sachliche Basis
    gegeneinander aufgestellt um Kommentare zu ernten.
    Grundlage für <em>Conflict Staging</em>.
  </span>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin:0.7rem 0 0.3rem 0;">Theoretischer Hintergrund</div>

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
