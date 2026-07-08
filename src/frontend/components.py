"""
HTML-building components for the dashboard.

Each render_* function returns an HTML string for st.markdown(...,
unsafe_allow_html=True); the small helpers above them are pure functions.

All human-facing copy lives in `src/strings.py` (single source of truth, with a
commented-out English mirror for forkers). This module only assembles HTML around
those strings and fills in the dynamic values (titles, scores, dates).
"""

import re

from src import strings

# CSS variable shorthands shared across components
T1  = "var(--text-primary)"
T2  = "var(--text-secondary)"
T3  = "var(--text-muted)"
BD  = "var(--border)"
BDL = "var(--border-light)"

# Sub-score label tables (centralised in strings.py)
FIELD_LABELS  = strings.FIELD_LABELS
SUB_SCORES    = strings.SUB_SCORES
FC_SUB_SCORES = strings.FC_SUB_SCORES


def extract_verdict(reasoning: str) -> str:
    """For reasoning that contains →: show only the verdict after the LAST arrow.
    Ragebait reasonings carry a single → (unchanged); the fact-check accuracy
    reasoning may carry one → per claim, so the last segment is the final verdict.
    Falls back to full text for older versions that don't use this format."""
    if "→" in reasoning:
        return reasoning.rsplit("→", 1)[1].strip()
    return reasoning


def clip_reasoning(reasoning: str, limit: int = 450) -> str:
    """Frontend-only safety cap: the prompt produces a short 2–3 sentence verdict
    after `→` (full reasoning stays in the DB). We show that verdict; the limit
    only trims runaway text (never mid-word)."""
    text = extract_verdict(reasoning or "").strip()
    # Strip raw markdown emphasis and a leading "1." / "2)" enumeration the model
    # sometimes emits — they render literally in the card.
    text = text.replace("**", "").replace("##", "").strip()
    text = re.sub(r'^\s*\d+[.)]\s*', '', text)
    if len(text) <= limit:
        return text
    cut = text[:limit]
    for sep in (". ", "! ", "? "):
        idx = cut.rfind(sep)
        if idx > limit * 0.5:
            return cut[:idx + 1].strip()
    sp = cut.rfind(" ")
    return (cut[:sp] if sp > 0 else cut).rstrip(" ,;:") + " …"


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


def render_section_label(batch_stats: dict) -> str:
    if batch_stats["total"] > 0:
        batch_time = batch_stats["batch_time"]
        batch_time_str = batch_time.strftime("%H:%M UTC") if batch_time else "—"
        label = strings.UI_RB_SECTION_LABEL.format(
            total=batch_stats["total"], time=batch_time_str
        )
    else:
        label = strings.UI_RB_SECTION_LABEL_EMPTY
    return f'<div class="section-label">{label}</div>'


def render_highlight(latest: dict) -> str:
    """The main highlight card: score | title + sub-score bars | reasoning."""
    d  = latest["details"]
    ts = latest["scraped_at"].strftime("%d.%m.%Y %H:%M UTC") if latest["scraped_at"] else "—"

    rb_detail = d.get("ragebait", {})
    rb_score  = rb_detail.get("score", latest.get("ragebait_score") or 0)
    RB        = ragebait_color(rb_score)

    # Shared cell styles
    C1 = f'padding:1rem 1rem 1rem 0;border-right:1px solid {BD};text-align:center;'
    C2 = f'padding:1rem 1.4rem;border-right:1px solid {BD};'
    C3 = 'padding:1rem 0 1rem 1.4rem;'
    ROW_BORDER = f'border-bottom:1px solid {BDL};'

    # Compact cell styles for the title row (less vertical padding)
    C1h = f'padding:0.5rem 1rem 0.5rem 0;border-right:1px solid {BD};text-align:center;'
    C2h = f'padding:0.5rem 1.4rem;border-right:1px solid {BD};'
    C3h = 'padding:0.5rem 0 0.5rem 1.4rem;'

    # ── Row 1: title | Begründung header
    row1 = (
        f'<div style="{C1h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">{strings.UI_LABEL_SCORES}</div>'
        f'</div>'
        f'<div style="{C2h}{ROW_BORDER}">'
        f'<div class="highlight-title">{latest["title"]}</div>'
        f'</div>'
        f'<div style="{C3h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">{strings.UI_LABEL_REASONING}</div>'
        f'</div>'
    )

    # ── Row 2: the Ragebait dimension (score, bars, reasoning)
    dim_data  = d.get("ragebait", {})
    big_score = dim_data.get("score", latest.get("ragebait_score") or 0)

    # Sub-score bars
    bars_html = (
        f'<div style="font-size:0.68rem;font-weight:600;color:{RB};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{strings.UI_LABEL_RAGEBAIT_INDEX}</div>'
    )
    for sk, sl in SUB_SCORES:
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
    has_per_sub = any(dim_data.get(f"{sk}_reasoning") for sk, _ in SUB_SCORES)
    if has_per_sub:
        reasoning_html = ""
        for sk, sl in SUB_SCORES:
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

    # No bottom border here — the meta footer row follows directly
    dim_row = (
        f'<div style="{C1}vertical-align:top;">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{RB};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">'
        f'{strings.UI_LABEL_RAGEBAIT}</div>'
        f'<div style="font-size:3rem;font-weight:600;line-height:1;color:{RB};">'
        f'{big_score:.1f}</div>'
        f'</div>'
        f'<div style="{C2}">{bars_html}</div>'
        f'<div style="{C3}">{reasoning_html}</div>'
    )

    # ── Row 3: meta footer
    row3 = (
        f'<div style="{C1}display:flex;flex-direction:column;justify-content:center;padding-top:0.8rem;padding-bottom:0.8rem;">'
        f'<div><span class="tag">{latest["category"]}</span>'
        f'<span class="tag">{latest["word_count"]}{strings.UI_WORD_SUFFIX}</span></div>'
        f'<div style="font-size:0.65rem;color:{T3};margin-top:0.4rem;">{ts}</div>'
        f'</div>'
        f'<div style="{C2}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;"></div>'
        f'<div style="{C3}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;font-size:0.68rem;color:{T3};">'
        f'{latest["score_model"]} &nbsp;·&nbsp; {latest["score_version"]}'
        f'&nbsp;&nbsp;<a href="{latest["url"]}" target="_blank" '
        f'style="color:{RB};text-decoration:none;font-weight:500;">{strings.UI_LABEL_OPEN_ARTICLE}</a>'
        f'</div>'
    )

    return (
        f'<div class="highlight-wrap">'
        f'<div style="display:grid;grid-template-columns:110px 1fr 1fr;gap:0;">'
        f'{row1}{dim_row}{row3}'
        f'</div></div>'
    )


def render_reader_service(reader_service: dict) -> str:
    """The 'Kern des Themas' card. Returns "" if all cells are empty."""
    facts  = reader_service.get("facts", "").strip()
    stake  = reader_service.get("stake", "").strip()
    action = reader_service.get("action", "").strip()

    facts_cell = (
        f'<div class="reader-service-cell">'
        f'<div class="reader-service-cell-label">{strings.UI_RS_FACTS_LABEL}</div>'
        f'{facts}'
        f'</div>'
    ) if facts else ""

    stake_cell = (
        f'<div class="reader-service-cell">'
        f'<div class="reader-service-cell-label">{strings.UI_RS_STAKE_LABEL}</div>'
        f'{stake}'
        f'</div>'
    ) if stake else ""

    action_cell = (
        f'<div class="reader-service-cell" style="grid-column:1/-1;'
        f'border-top:1px solid var(--border);border-right:none;">'
        f'<div class="reader-service-cell-label">{strings.UI_RS_ACTION_LABEL}</div>'
        f'{action}'
        f'</div>'
    ) if action else ""

    if not (facts_cell or stake_cell or action_cell):
        return ""

    return (
        f'<div class="reader-service-wrap">'
        f'<div class="reader-service-header">{strings.UI_RS_HEADER}</div>'
        f'<div class="reader-service-body">{facts_cell}{stake_cell}{action_cell}</div>'
        f'</div>'
    )


def render_empty_state() -> str:
    return (
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;line-height:1.7;">'
        f'{strings.UI_RB_EMPTY_STATE}</div>'
    )


# ═══════════════════════════════════════════════════════════════════
# FACT-CHECK TRACK (Irreführungs-Index)
# ═══════════════════════════════════════════════════════════════════

def render_factcheck_section_label(batch_stats: dict) -> str:
    if batch_stats["total"] > 0:
        bt = batch_stats["batch_time"]
        bt_str = bt.strftime("%H:%M UTC") if bt else "—"
        label = strings.UI_FC_SECTION_LABEL.format(
            total=batch_stats["total"], time=bt_str
        )
    else:
        label = strings.UI_FC_SECTION_LABEL_EMPTY
    return f'<div class="section-label">{label}</div>'


def render_factcheck_highlight(fc: dict) -> str:
    """Main fact-check card: Irreführungs-Index | sub-score bars | reasoning."""
    ss     = fc.get("sub_scores", {})
    score  = fc.get("fact_check_score") or 0
    FC     = ragebait_color(score)
    ts     = fc["fact_check_at"].strftime("%d.%m.%Y %H:%M UTC") if fc.get("fact_check_at") else "—"
    label  = ss.get("factual_accuracy_label", strings.UI_FC_NEI)
    counted = ss.get("accuracy_counted", label != strings.UI_FC_NEI)

    C1  = f'padding:1rem 1rem 1rem 0;border-right:1px solid {BD};text-align:center;'
    C2  = f'padding:1rem 1.4rem;border-right:1px solid {BD};'
    C3  = 'padding:1rem 0 1rem 1.4rem;'
    ROW_BORDER = f'border-bottom:1px solid {BDL};'
    C1h = f'padding:0.5rem 1rem 0.5rem 0;border-right:1px solid {BD};text-align:center;'
    C2h = f'padding:0.5rem 1.4rem;border-right:1px solid {BD};'
    C3h = 'padding:0.5rem 0 0.5rem 1.4rem;'

    # Row 1: Scores | title | Begründung
    row1 = (
        f'<div style="{C1h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">{strings.UI_LABEL_SCORES}</div></div>'
        f'<div style="{C2h}{ROW_BORDER}"><div class="highlight-title">{fc["title"]}</div></div>'
        f'<div style="{C3h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">{strings.UI_LABEL_REASONING}</div></div>'
    )

    # Sub-score bars
    bars_html = (
        f'<div style="font-size:0.68rem;font-weight:600;color:{FC};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">{strings.UI_LABEL_FC_INDEX}</div>'
    )
    for sk, sl in FC_SUB_SCORES:
        if sk == "factual_accuracy" and not counted:
            # Accuracy abstained (NEI) — show honestly, no fabricated bar.
            bars_html += (
                f'<div class="sub-row"><span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{T3};">{strings.UI_FC_NEI}</span></div>'
                f'<div style="font-size:var(--fs-meta);color:{T3};margin:0 0 8px 0;">'
                f'{strings.UI_FC_NEI_NOTE}</div>'
            )
        else:
            sv = ss.get(sk, 0)
            sc = ragebait_color(sv)
            bars_html += (
                f'<div class="sub-row"><span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{sc};">{sv:.1f}</span></div>'
                + score_bar(sv, sc)
            )

    # Reasoning per sub-score
    reasoning_html = ""
    for sk, sl in FC_SUB_SCORES:
        sr = ss.get(f"{sk}_reasoning", "")
        if not sr:
            continue
        if sk == "factual_accuracy":
            sc = T3 if not counted else ragebait_color(ss.get(sk, 0))
            head = f"{sl} · {label}"
        else:
            sc = ragebait_color(ss.get(sk, 0))
            head = sl
        reasoning_html += (
            f'<div style="margin-bottom:0.75rem;">'
            f'<div style="font-size:var(--fs-meta);font-weight:600;color:{sc};'
            f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:2px;">{head}</div>'
            f'<div class="reasoning-text">{clip_reasoning(sr)}</div></div>'
        )

    dim_row = (
        f'<div style="{C1}vertical-align:top;">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{FC};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">{strings.UI_LABEL_FC}</div>'
        f'<div style="font-size:3rem;font-weight:600;line-height:1;color:{FC};">{score:.1f}</div></div>'
        f'<div style="{C2}">{bars_html}</div>'
        f'<div style="{C3}">{reasoning_html}</div>'
    )

    row3 = (
        f'<div style="{C1}display:flex;flex-direction:column;justify-content:center;'
        f'padding-top:0.8rem;padding-bottom:0.8rem;">'
        f'<div><span class="tag">{fc["category"]}</span>'
        f'<span class="tag">{fc["word_count"]}{strings.UI_WORD_SUFFIX}</span></div>'
        f'<div style="font-size:0.65rem;color:{T3};margin-top:0.4rem;">{ts}</div></div>'
        f'<div style="{C2}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;"></div>'
        f'<div style="{C3}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;'
        f'font-size:0.68rem;color:{T3};">'
        f'{fc["fact_check_model"]} &nbsp;·&nbsp; {fc["fact_check_version"]}'
        f'&nbsp;&nbsp;<a href="{fc["url"]}" target="_blank" '
        f'style="color:{FC};text-decoration:none;font-weight:500;">{strings.UI_LABEL_OPEN_ARTICLE}</a></div>'
    )

    return (
        f'<div class="highlight-wrap">'
        f'<div style="display:grid;grid-template-columns:110px 1fr 1fr;gap:0;">'
        f'{row1}{dim_row}{row3}</div></div>'
    )


def render_factcheck_evidence(fc: dict) -> str:
    """Per-claim evidence card: extracted claims with their fact-checks + web sources."""
    claims   = fc.get("claims", [])
    evidence = fc.get("evidence", [])
    if not claims:
        return ""

    # Map claim text → its evidence bundle (evidence list mirrors claims order).
    rows = ""
    any_evidence = False
    for i, claim in enumerate(claims):
        bundle = evidence[i] if i < len(evidence) else {}
        fcs = bundle.get("fact_checks", []) or []
        web = bundle.get("web_evidence", []) or []
        any_evidence = any_evidence or bool(fcs or web)

        src_html = ""
        for r in fcs:
            pub = r.get("publisher") or r.get("site") or strings.UI_FC_PUBLISHER_FALLBACK
            url = r.get("url", "")
            rating = r.get("rating", "")
            src_html += (
                f'<div style="margin:2px 0;font-size:var(--fs-meta);">'
                f'<span class="tag">{rating}</span> '
                f'<a href="{url}" target="_blank" style="color:{T2};">{pub} ↗</a></div>'
            )
        for w in web:
            url = w.get("url", "")
            title = w.get("title", "") or url
            src_html += (
                f'<div style="margin:2px 0;font-size:var(--fs-meta);">'
                f'<a href="{url}" target="_blank" style="color:{T2};">{title} ↗</a></div>'
            )
        if not src_html:
            src_html = (f'<div style="font-size:var(--fs-meta);color:{T3};">'
                        f'{strings.UI_FC_NO_EVIDENCE}</div>')

        rows += (
            f'<div class="reader-service-cell" style="grid-column:1/-1;border-right:none;'
            f'border-top:1px solid {BDL};">'
            f'<div class="reader-service-cell-label">{strings.UI_FC_CLAIM_LABEL} {i+1}</div>'
            f'<div style="margin-bottom:0.4rem;">{claim}</div>{src_html}</div>'
        )

    # Only claim these sources are "the basis for the verdict" when we actually
    # kept some. With no surviving evidence the note below carries the honest
    # explanation instead — never present rejected/empty evidence as the basis.
    intro = ("" if not any_evidence else
             f'<div class="reader-service-cell" style="grid-column:1/-1;border-right:none;'
             f'font-size:var(--fs-meta);color:{T3};line-height:1.6;">'
             f'{strings.UI_FC_EVIDENCE_INTRO.format(t2=T2)}</div>')

    note = ("" if any_evidence else
            f'<div class="reader-service-cell" style="grid-column:1/-1;border-right:none;'
            f'font-size:var(--fs-meta);color:{T3};">'
            f'{strings.UI_FC_EVIDENCE_NOTE}</div>')

    return (
        f'<div class="reader-service-wrap">'
        f'<div class="reader-service-header">{strings.UI_FC_EVIDENCE_HEADER}</div>'
        f'<div class="reader-service-body" style="grid-template-columns:1fr;">{intro}{rows}{note}</div>'
        f'</div>'
    )


def render_factcheck_empty_state() -> str:
    return (
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;line-height:1.7;">'
        f'{strings.UI_FC_EMPTY_STATE}</div>'
    )


# ── Large prose blocks (re-exported from strings.py for app.py) ──────────────
PINO_SHOUTOUT_HTML             = strings.PINO_SHOUTOUT_HTML
FACTCHECK_EXPLAINER_MD         = strings.FACTCHECK_EXPLAINER_MD
HEADER_HTML                    = strings.HEADER_HTML
EXPLAINER_MD                   = strings.EXPLAINER_MD
RESEARCH_FOOTER_HTML           = strings.RESEARCH_FOOTER_HTML
FACTCHECK_RESEARCH_FOOTER_HTML = strings.FACTCHECK_RESEARCH_FOOTER_HTML
