import os, sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))

import streamlit as st
from dotenv import load_dotenv
load_dotenv()

st.set_page_config(
    page_title="Ecosystem Sanity Stack",
    page_icon="📡",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ─────────────────────────────────────────────────────────────
# CSS
# ─────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&family=VT323:wght@400&family=Share+Tech+Mono&display=swap');

html, body, [class*="css"] {
    background-color: #080808;
    color: #E0E0E0;
    font-family: 'Share Tech Mono', monospace;
}
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding: 1.5rem 2rem 4rem 2rem; max-width: 1400px; }
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-thumb { background: #FF6B2B; }

.scanline {
    position: fixed; top:0; left:0; width:100%; height:100%;
    background: repeating-linear-gradient(0deg,transparent,transparent 2px,rgba(0,0,0,0.04) 2px,rgba(0,0,0,0.04) 4px);
    pointer-events: none; z-index: 9999;
}

/* ── Dimension cards ── */
.dim-card {
    background: #0C0C0C;
    border: 2px solid #1C1C1C;
    padding: 1.4rem 1.5rem 1.2rem 1.5rem;
    height: 100%;
}
.dim-eyebrow {
    font-size: 0.5rem; text-transform: uppercase;
    letter-spacing: 3px; margin-bottom: 0.6rem;
}
.dim-main {
    font-family: 'VT323', monospace;
    font-size: 5.5rem; line-height: 1; margin-bottom: 0.1rem;
}
.dim-sublabel {
    font-size: 0.52rem; color: #2A2A2A; letter-spacing: 2px;
    text-transform: uppercase; margin-bottom: 0.7rem;
}
.dim-stat { font-size: 0.58rem; color: #444; margin-top: 0.3rem; }
.dim-stat b { font-size: 0.68rem; }
.dim-study {
    font-size: 0.5rem; color: #222;
    border-top: 1px solid #111; padding-top: 0.6rem; margin-top: 0.5rem; line-height: 1.9;
}
.dim-study a { text-decoration: none; }
.dim-interp {
    font-size: 0.48rem; color: #1E1E1E; line-height: 1.8;
    border-top: 1px solid #0E0E0E; margin-top: 0.5rem; padding-top: 0.5rem;
}

/* ── Pixel bar ── */
.px-bar-wrap { background:#111; border:1px solid #191919; height:5px; width:100%; margin:2px 0 7px 0; }
.px-bar-fill { height:100%; image-rendering:pixelated; }

/* ── Highlight card ── */
.highlight-wrap {
    background: #0C0C0C;
    border: 2px solid #1C1C1C;
    box-shadow: 5px 5px 0px #FF6B2B33;
    padding: 1.4rem 1.6rem;
    margin-top: 1.2rem;
}
.highlight-title { font-size: 1rem; color: #F0F0F0; line-height: 1.4; margin-bottom: 0.4rem; }
.highlight-meta  { font-size: 0.6rem; color: #444; margin-bottom: 1rem; }

.sub-label    { font-size: 0.5rem; color: #383838; text-transform: uppercase; letter-spacing: 1px; }
.sub-score-val { font-family: 'VT323', monospace; font-size: 1.05rem; }
.sub-row      { display:flex; justify-content:space-between; align-items:baseline; margin: 2px 0; }
.reasoning-text { font-size: 0.65rem; color: #666; line-height: 1.55; border-left: 2px solid #161616; padding-left: 10px; }

.px-tag { font-size: 0.5rem; background:#0C0C0C; border:1px solid #1A1A1A; padding:2px 6px;
           margin-right:3px; display:inline-block; text-transform:uppercase; letter-spacing:1px; color:#444; }

.section-head {
    font-family: 'Press Start 2P', monospace;
    font-size: 0.45rem; color: #222; letter-spacing: 3px; text-transform: uppercase;
    margin: 1.6rem 0 0.7rem 0; padding-bottom: 0.5rem; border-bottom: 1px solid #0F0F0F;
}

/* ── Research footer ── */
.research-footer {
    margin-top: 3rem; padding-top: 1rem; border-top: 1px solid #0C0C0C;
    font-size: 0.5rem; color: #1E1E1E; line-height: 2.3;
}
.research-footer a { color: #252525; text-decoration: none; }
.research-footer a:hover { color: #FF6B2B; }

/* ── Radio as segmented control ── */
div[data-testid="stHorizontalBlock"] .stRadio > div { flex-direction: row; gap: 0; }
div[data-testid="stHorizontalBlock"] .stRadio > div > label {
    background: #0A0A0A; border: 1px solid #181818;
    padding: 4px 14px; margin: 0; font-size: 0.6rem; color: #383838;
    cursor: pointer; font-family: 'Share Tech Mono', monospace;
}
div[data-testid="stHorizontalBlock"] .stRadio > div > label[data-selected="true"] {
    background: #FF6B2B18; border-color: #FF6B2B; color: #FF6B2B;
}
</style>
<div class="scanline"></div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────
import plotly.graph_objects as go
from datetime import datetime, timedelta, timezone
from sqlalchemy import select
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
                "author":           r.author or "—",
                "category":         r.category or "—",
                "word_count":       r.word_count or 0,
                "article_type":     r.article_type or "standard",
                "scraped_at":       r.scraped_at,
                "published_at":     r.published_at,
                "ragebait_score":   r.ragebait_score,
                "emotional_weight": r.emotional_weight,
                "pre_score":        r.pre_score,
                "details":          r.score_details or {},
                "score_model":      r.score_model or "—",
                "score_version":    r.score_version or "—",
            }
            for r in rows
        ]

@st.cache_data(ttl=60)
def load_batch_stats():
    """Stats for the most recent scrape batch (last 90 min window around latest scraped_at)."""
    from datetime import timedelta as td
    from sqlalchemy import func
    with get_session() as session:
        # Find latest scraped_at among pre-scored articles
        latest_scraped = session.scalar(
            select(func.max(ArticleModel.scraped_at)).where(ArticleModel.pre_score.isnot(None))
        )
        if not latest_scraped:
            return {"total": 0, "flagged": 0, "top_pre_score": None, "batch_time": None}

        # Batch window: ±45 min around latest scrape
        window_start = latest_scraped - td(minutes=45)
        batch_articles = list(session.scalars(
            select(ArticleModel)
            .where(
                ArticleModel.pre_score.isnot(None),
                ArticleModel.scraped_at >= window_start,
            )
        ))
        total   = len(batch_articles)
        flagged = sum(1 for a in batch_articles if (a.pre_score or 0) >= 5.0)
        top_pre = max((a.pre_score or 0 for a in batch_articles), default=None)
        return {
            "total":         total,
            "flagged":       flagged,
            "top_pre_score": top_pre,
            "batch_time":    latest_scraped,
        }

all_articles = load_articles()
batch_stats  = load_batch_stats()


# ─────────────────────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────────────────────
RAGEBAIT_COLOR  = "#FF6B2B"
WEIGHT_COLOR    = "#6B8EFF"

RANGES = {"24H": timedelta(hours=24), "7D": timedelta(days=7),
          "30D": timedelta(days=30),  "1Y": timedelta(days=365), "ALL": None}


# ─────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────
def field_avg(articles, field):
    vals = [a[field] for a in articles if a.get(field) is not None]
    return round(sum(vals) / len(vals), 2) if vals else 0.0

def pixel_bar(val, color):
    pct = min(100, (val / 10) * 100)
    return (f'<div class="px-bar-wrap">'
            f'<div class="px-bar-fill" style="width:{pct:.0f}%;background:{color};"></div>'
            f'</div>')

def trend_parts(avg, prev_articles, field):
    if not prev_articles:
        return None, "—", "#444", ""
    p = field_avg(prev_articles, field)
    tv = round(avg - p, 2)
    ts = (f"+{tv}" if tv > 0 else str(tv))
    tc = "#EF4444" if tv > 0 else "#22C55E" if tv < 0 else "#444"
    arr = "&#9650;" if tv > 0 else "&#9660;" if tv < 0 else ""
    return tv, ts, tc, arr


# ─────────────────────────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;align-items:baseline;gap:1.2rem;margin-bottom:1.8rem;">
  <span style="font-family:'Press Start 2P',monospace;font-size:0.9rem;color:#FF6B2B;letter-spacing:1px;">
    ECOSYSTEM SANITY STACK
  </span>
  <span style="font-family:'Share Tech Mono',monospace;font-size:0.6rem;color:#242424;letter-spacing:2px;">
    // 20MIN.CH &nbsp; MEDIA HYGIENE MONITOR
  </span>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# TIME RANGE
# ─────────────────────────────────────────────────────────────
_, rc = st.columns([3, 1])
with rc:
    time_range = st.radio("RANGE", list(RANGES.keys()), horizontal=True,
                          index=0, label_visibility="collapsed")

now   = datetime.now(timezone.utc)
delta = RANGES[time_range]

if delta:
    cutoff   = now - delta
    filtered = [a for a in all_articles
                if a["scraped_at"] and a["scraped_at"].replace(tzinfo=timezone.utc) >= cutoff]
else:
    filtered = all_articles

prev = []
if delta and filtered:
    prev_cutoff = cutoff - delta
    prev = [a for a in all_articles
            if a["scraped_at"]
            and prev_cutoff <= a["scraped_at"].replace(tzinfo=timezone.utc) < cutoff]


# ─────────────────────────────────────────────────────────────
# CARD ROW — Ragebait left | Emotional Weight right
# ─────────────────────────────────────────────────────────────
rb_avg = field_avg(filtered, "ragebait_score") if filtered else 0.0
ew_avg = field_avg(filtered, "emotional_weight") if filtered else 0.0

_, rb_ts, rb_tc, rb_arr = trend_parts(rb_avg, prev, "ragebait_score")
_, ew_ts, ew_tc, ew_arr = trend_parts(ew_avg, prev, "emotional_weight")

c_rb, c_sep, c_ew = st.columns([1, 0.06, 1], gap="small")

with c_rb:
    st.markdown(
        f'<div class="dim-card" style="box-shadow:4px 4px 0 {RAGEBAIT_COLOR}22;">'
        f'<div class="dim-eyebrow" style="color:{RAGEBAIT_COLOR};">Ragebait Index</div>'
        f'<div class="dim-main" style="color:{RAGEBAIT_COLOR};">{rb_avg:.1f}</div>'
        f'<div class="dim-sublabel">/ 10.0 &nbsp; avg {time_range} &nbsp;·&nbsp; higher = more manufactured</div>'
        f'<div class="dim-stat"><b style="color:{RAGEBAIT_COLOR};">{len(filtered)}</b> articles &nbsp;'
        f'<span style="color:{rb_tc};">{rb_arr} {rb_ts} vs prev</span></div>'
        f'<div class="dim-study">'
        f'<span style="color:#2A2A2A;">Is this emotion manufactured or authentic?</span><br>'
        f'<a href="https://doi.org/10.1080/17512786.2014.976939" target="_blank" style="color:#222;">'
        f'Blom &amp; Hansen (2015) — Journalism Practice</a><br>'
        f'<a href="https://doi.org/10.1007/978-3-319-30671-1_72" target="_blank" style="color:#222;">'
        f'Potthast et al. (2016) — ECIR</a><br>'
        f'<a href="https://doi.org/10.1145/3091478.3091487" target="_blank" style="color:#222;">'
        f'Rony, Hassan &amp; Yousuf (2017) — ACM WebSci</a>'
        f'</div>'
        f'<div class="dim-interp">'
        f'0–2 &nbsp;Emotion emerges from facts &nbsp;·&nbsp; '
        f'5 &nbsp;Mixed signals &nbsp;·&nbsp; '
        f'8–10 Emotion is the product'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

with c_sep:
    st.markdown(
        '<div style="height:100%;min-height:200px;border-left:1px solid #111;margin:0.5rem 0;"></div>',
        unsafe_allow_html=True,
    )

with c_ew:
    st.markdown(
        f'<div class="dim-card" style="box-shadow:4px 4px 0 {WEIGHT_COLOR}22;">'
        f'<div class="dim-eyebrow" style="color:{WEIGHT_COLOR};">Emotional Weight</div>'
        f'<div class="dim-main" style="color:{WEIGHT_COLOR};">{ew_avg:.1f}</div>'
        f'<div class="dim-sublabel">/ 10.0 &nbsp; avg {time_range} &nbsp;·&nbsp; neutral descriptor</div>'
        f'<div class="dim-stat"><b style="color:{WEIGHT_COLOR};">{len(filtered)}</b> articles &nbsp;'
        f'<span style="color:{ew_tc};">{ew_arr} {ew_ts} vs prev</span></div>'
        f'<div class="dim-study">'
        f'<span style="color:#2A2A2A;">How heavy is this content to process?</span><br>'
        f'<span style="color:#1A1A1A;">No value judgment — purely contextual.</span><br>'
        f'<span style="color:#1A1A1A;">High weight + low ragebait = authentic heavy news.</span><br>'
        f'<span style="color:#1A1A1A;">High weight + high ragebait = exploitation.</span>'
        f'</div>'
        f'<div class="dim-interp">'
        f'0–2 &nbsp;Trivial/lifestyle &nbsp;·&nbsp; '
        f'5 &nbsp;Relevant but not threatening &nbsp;·&nbsp; '
        f'9–10 War / disaster'
        f'</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# QUADRANT LEGEND
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div style="display:flex;gap:1rem;margin-top:0.7rem;margin-bottom:0.2rem;flex-wrap:wrap;">
  <div style="font-size:0.45rem;color:#1C1C1C;border:1px solid #111;padding:4px 10px;">
    <span style="color:#22C55E44;">&#9632;</span> LOW ragebait + LOW weight &nbsp;=&nbsp; clean informational content
  </div>
  <div style="font-size:0.45rem;color:#1C1C1C;border:1px solid #111;padding:4px 10px;">
    <span style="color:#6B8EFF44;">&#9632;</span> LOW ragebait + HIGH weight &nbsp;=&nbsp; authentic heavy news — take breaks
  </div>
  <div style="font-size:0.45rem;color:#1C1C1C;border:1px solid #111;padding:4px 10px;">
    <span style="color:#FF6B2B44;">&#9632;</span> HIGH ragebait + LOW weight &nbsp;=&nbsp; pure clickbait — no substance
  </div>
  <div style="font-size:0.45rem;color:#1C1C1C;border:1px solid #111;padding:4px 10px;">
    <span style="color:#EF444444;">&#9632;</span> HIGH ragebait + HIGH weight &nbsp;=&nbsp; exploitation of real suffering
  </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────
# CHART — 2 lines: Ragebait (orange) + Emotional Weight (blue)
# ─────────────────────────────────────────────────────────────
st.markdown("<div style='height:0.4rem'></div>", unsafe_allow_html=True)

if not filtered:
    st.markdown('<div style="color:#141414;text-align:center;padding:3rem;font-size:0.7rem;">NO DATA FOR THIS PERIOD</div>',
                unsafe_allow_html=True)
else:
    chart_data = sorted(filtered, key=lambda a: a["scraped_at"])
    xs = [a["scraped_at"] for a in chart_data]

    fig = go.Figure()

    # Ragebait line
    rb_ys = [a["ragebait_score"] or 0 for a in chart_data]
    rb_labels = []
    for a in chart_data:
        rb_labels.append(f"<b>{a['title'][:52]}</b><br>Ragebait: {a['ragebait_score'] or 0:.1f}<br>{a['category']}")

    fig.add_trace(go.Scatter(x=xs, y=rb_ys, fill="tozeroy",
                             fillcolor="rgba(255,107,43,0.03)",
                             line=dict(color=RAGEBAIT_COLOR, width=1.5),
                             mode="lines", hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=rb_ys, mode="markers",
                             marker=dict(color=RAGEBAIT_COLOR, size=8, symbol="square",
                                         line=dict(color="#080808", width=1)),
                             name="Ragebait Index", text=rb_labels,
                             hovertemplate="<b>%{text}</b><extra></extra>"))

    # Emotional Weight line
    ew_ys = [a["emotional_weight"] or 0 for a in chart_data]
    ew_labels = []
    for a in chart_data:
        ew_labels.append(f"<b>{a['title'][:52]}</b><br>Emotional Weight: {a['emotional_weight'] or 0:.1f}<br>{a['category']}")

    fig.add_trace(go.Scatter(x=xs, y=ew_ys, fill="tozeroy",
                             fillcolor="rgba(107,142,255,0.03)",
                             line=dict(color=WEIGHT_COLOR, width=1.5),
                             mode="lines", hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=ew_ys, mode="markers",
                             marker=dict(color=WEIGHT_COLOR, size=8, symbol="diamond",
                                         line=dict(color="#080808", width=1)),
                             name="Emotional Weight", text=ew_labels,
                             hovertemplate="<b>%{text}</b><extra></extra>"))

    fig.update_layout(
        paper_bgcolor="#080808", plot_bgcolor="#080808",
        margin=dict(l=0, r=0, t=10, b=0), height=230,
        legend=dict(orientation="h", x=0, y=1.18,
                    font=dict(family="Share Tech Mono", size=9, color="#333"),
                    bgcolor="rgba(0,0,0,0)"),
        xaxis=dict(showgrid=False, zeroline=False,
                   tickfont=dict(family="Share Tech Mono", size=9, color="#2A2A2A"),
                   linecolor="#0F0F0F"),
        yaxis=dict(range=[0, 10.5], showgrid=True, gridcolor="#0D0D0D",
                   zeroline=False,
                   tickfont=dict(family="Share Tech Mono", size=9, color="#2A2A2A"),
                   linecolor="#0F0F0F", dtick=2),
        hoverlabel=dict(bgcolor="#111", bordercolor="#222",
                        font=dict(family="Share Tech Mono", size=11, color="#E0E0E0")),
    )
    st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})


# ─────────────────────────────────────────────────────────────
# LATEST ARTICLE HIGHLIGHT
# ─────────────────────────────────────────────────────────────
latest = filtered[0] if filtered else (all_articles[0] if all_articles else None)

if latest:
    d  = latest["details"]
    ts = latest["scraped_at"].strftime("%Y-%m-%d %H:%M UTC") if latest["scraped_at"] else "—"

    rb_detail = d.get("ragebait", {})
    ew_detail = d.get("emotional_weight", {})

    rb_score = rb_detail.get("score", latest.get("ragebait_score") or 0)
    ew_score = ew_detail.get("score", latest.get("emotional_weight") or 0)

    # Left meta — 2 dimension scores stacked
    meta_html = (
        f'<div style="min-width:120px;text-align:center;padding-right:1.2rem;border-right:1px solid #0F0F0F;">'
        f'<div style="font-size:0.42rem;color:#282828;letter-spacing:2px;text-transform:uppercase;margin-bottom:0.8rem;">LATEST SIGNAL</div>'
        f'<div style="margin-bottom:1rem;padding-top:0.4rem;">'
        f'<div style="font-size:0.45rem;color:{RAGEBAIT_COLOR};text-transform:uppercase;letter-spacing:2px;">Ragebait</div>'
        f'<div style="font-family:\'VT323\',monospace;font-size:3.5rem;line-height:1;color:{RAGEBAIT_COLOR};">{rb_score:.1f}</div>'
        f'</div>'
        f'<div style="margin-bottom:1rem;padding-top:0.4rem;border-top:1px solid #0F0F0F;">'
        f'<div style="font-size:0.45rem;color:{WEIGHT_COLOR};text-transform:uppercase;letter-spacing:2px;">Weight</div>'
        f'<div style="font-family:\'VT323\',monospace;font-size:3.5rem;line-height:1;color:{WEIGHT_COLOR};">{ew_score:.1f}</div>'
        f'</div>'
        f'<div style="margin-top:0.5rem;">'
        f'<span class="px-tag">{latest["category"]}</span><br style="margin:3px 0">'
        f'<span class="px-tag">{latest["article_type"]}</span>'
        f'<span class="px-tag">{latest["word_count"]}w</span>'
        f'</div>'
        f'<div style="font-size:0.42rem;color:#1E1E1E;margin-top:0.5rem;">{ts}</div>'
        f'</div>'
    )

    # Middle — sub-score bars
    DIMS = [
        ("ragebait", RAGEBAIT_COLOR, "Ragebait Index", [
            ("curiosity_gap",       "Curiosity gap"),
            ("conflict_staging",    "Conflict staging"),
            ("emotional_inflation", "Emotional inflation"),
        ]),
        ("emotional_weight", WEIGHT_COLOR, "Emotional Weight", [
            ("topic_gravity",      "Topic gravity"),
            ("emotional_exposure", "Emotional exposure"),
            ("reader_burden",      "Reader burden"),
        ]),
    ]

    mid_parts = []
    for dk, c, lbl, subs in DIMS:
        dim_data = d.get(dk, {})
        rows = ""
        for sk, sl in subs:
            sv = dim_data.get(sk, 0)
            bar = pixel_bar(sv, c)
            sv_str = f"{sv:.1f}"
            rows += (
                f'<div class="sub-row">'
                f'<span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{c};">{sv_str}</span>'
                f'</div>'
                + bar
            )
        mid_parts.append(
            f'<div style="margin-bottom:0.9rem;padding-bottom:0.8rem;border-bottom:1px solid #0C0C0C;">'
            f'<div style="font-size:0.48rem;color:{c};text-transform:uppercase;letter-spacing:2px;margin-bottom:3px;">{lbl}</div>'
            f'{rows}</div>'
        )

    middle_html = (
        f'<div style="flex:1;padding:0 1.3rem;">'
        f'<div class="highlight-title">{latest["title"]}</div>'
        f'<div class="highlight-meta">{latest["author"]}</div>'
        + "".join(mid_parts) +
        f'</div>'
    )

    # Right — reasoning per dimension
    right_parts = []
    for dk, c, lbl, _ in DIMS:
        reasoning = d.get(dk, {}).get("reasoning", "—")
        right_parts.append(
            f'<div style="margin-bottom:0.9rem;padding-bottom:0.7rem;border-bottom:1px solid #0C0C0C;">'
            f'<div style="font-size:0.45rem;color:{c};text-transform:uppercase;letter-spacing:2px;margin-bottom:3px;">{lbl}</div>'
            f'<div class="reasoning-text">{reasoning}</div>'
            f'</div>'
        )

    right_html = (
        f'<div style="flex:1;border-left:1px solid #0F0F0F;padding-left:1.3rem;">'
        f'<div style="font-size:0.45rem;color:#282828;text-transform:uppercase;letter-spacing:2px;margin-bottom:0.8rem;">Reasoning</div>'
        + "".join(right_parts) +
        f'<div style="padding-top:0.5rem;border-top:1px solid #0C0C0C;font-size:0.45rem;color:#1E1E1E;letter-spacing:1px;">'
        f'{latest["score_model"]} &nbsp;·&nbsp; {latest["score_version"]}'
        f'&nbsp;&nbsp;<a href="{latest["url"]}" target="_blank" style="color:#FF6B2B;text-decoration:none;">OPEN &#8599;</a>'
        f'</div></div>'
    )

    # Batch stats banner
    bs = batch_stats
    pre_score_val = latest.get("pre_score")
    if bs["total"] > 0:
        batch_time_str = bs["batch_time"].strftime("%H:%M UTC") if bs["batch_time"] else "—"
        pre_badge = (
            f'&nbsp;&nbsp;<span style="color:#FF6B2B;">pre {pre_score_val:.1f}</span>'
            if pre_score_val is not None else ""
        )
        section_label = (
            f'// STÄRKSTES RAGEBAIT-SIGNAL &nbsp;·&nbsp; '
            f'Mistral Small flaggte <span style="color:#FF6B2B;">{bs["flagged"]}</span> '
            f'von {bs["total"]} Artikeln im letzten Batch ({batch_time_str})'
            f'{pre_badge}'
        )
    else:
        section_label = "// LATEST SCORED ARTICLE"

    st.markdown(
        f'<div class="section-head">{section_label}</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        f'<div class="highlight-wrap">'
        f'<div style="display:flex;gap:0;align-items:flex-start;">'
        f'{meta_html}{middle_html}{right_html}'
        f'</div></div>',
        unsafe_allow_html=True,
    )

else:
    st.markdown(
        '<div style="color:#141414;text-align:center;padding:2rem;font-size:0.7rem;">'
        'NO SCORED ARTICLES YET — RUN run_pipeline.py</div>',
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────
# RESEARCH FOOTER
# ─────────────────────────────────────────────────────────────
st.markdown("""
<div class="research-footer">
  <span style="color:#181818;text-transform:uppercase;letter-spacing:3px;font-size:0.45rem;">// Research Foundation</span><br>
  <a href="https://doi.org/10.1080/17512786.2014.976939" target="_blank">
    Blom &amp; Hansen (2015) — Click bait: Forward-reference as lure in online news headlines — Journalism Practice
  </a><br>
  <a href="https://doi.org/10.1007/978-3-319-30671-1_72" target="_blank">
    Potthast et al. (2016) — Clickbait Detection — ECIR
  </a><br>
  <a href="https://doi.org/10.1145/3091478.3091487" target="_blank">
    Rony, Hassan &amp; Yousuf (2017) — Diving Deep into Clickbaits — ACM WebSci
  </a><br>
  <span style="color:#141414;">// Wellbeing Foundation (see THEORETICAL_FOUNDATION.md)</span><br>
  <a href="https://doi.org/10.1080/10410236.2022.2106086" target="_blank">
    McLaughlin, Gotlieb &amp; Mills (2022) — Problematic News Consumption — Health Communication
  </a><br>
  <a href="https://doi.org/10.1002/smi.916" target="_blank">
    McNaughton-Cassill &amp; Smith (2002) — Optimism Gap — Stress and Health
  </a><br>
  <a href="https://doi.org/10.1038/s41562-017-0213-3" target="_blank">
    Crockett (2017) — Moral Outrage in the Digital Age — Nature Human Behaviour
  </a>
</div>
""", unsafe_allow_html=True)
