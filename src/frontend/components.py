"""
HTML-building components for the dashboard.

Each render_* function returns an HTML string for st.markdown(...,
unsafe_allow_html=True); the small helpers above them are pure functions.
"""

import re

# CSS variable shorthands shared across components
T1  = "var(--text-primary)"
T2  = "var(--text-secondary)"
T3  = "var(--text-muted)"
BD  = "var(--border)"
BDL = "var(--border-light)"

FIELD_LABELS = {
    "curiosity_gap":          "Curiosity Gap",
    "conflict_staging":       "Conflict Staging",
    "emotional_inflation":    "Emotional Inflation",
    "narrative_exploitation": "Narrative Exploitation",
}

SUB_SCORES = [
    ("curiosity_gap",          "Curiosity Gap"),
    ("conflict_staging",       "Conflict Staging"),
    ("emotional_inflation",    "Emotional Inflation"),
    ("narrative_exploitation", "Narrative Exploitation"),
]


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


def render_section_label(batch_stats: dict) -> str:
    if batch_stats["total"] > 0:
        batch_time = batch_stats["batch_time"]
        batch_time_str = batch_time.strftime("%H:%M UTC") if batch_time else "—"
        label = (
            f'Höchster Ragebait-Score im letzten Batch &nbsp;·&nbsp; '
            f'{batch_stats["total"]} Artikel gescreent ({batch_time_str})'
            f'&nbsp;·&nbsp; Aktualisierung stündlich'
        )
    else:
        label = "Höchster Ragebait-Score"
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

    # ── Row 2: the Ragebait dimension (score, bars, reasoning)
    dim_data  = d.get("ragebait", {})
    big_score = dim_data.get("score", latest.get("ragebait_score") or 0)

    # Sub-score bars
    bars_html = (
        f'<div style="font-size:0.68rem;font-weight:600;color:{RB};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">Ragebait Index</div>'
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
        f'Ragebait</div>'
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

    if not (facts_cell or stake_cell or action_cell):
        return ""

    return (
        f'<div class="reader-service-wrap">'
        f'<div class="reader-service-header">Kern des Themas</div>'
        f'<div class="reader-service-body">{facts_cell}{stake_cell}{action_cell}</div>'
        f'</div>'
    )


def render_empty_state() -> str:
    return (
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;">'
        f'Kein Ragebait-Kandidat gefunden — Pipeline ausführen oder Threshold prüfen.</div>'
    )


# ═══════════════════════════════════════════════════════════════════
# FACT-CHECK TRACK (Irreführungs-Index)
# ═══════════════════════════════════════════════════════════════════

FC_SUB_SCORES = [
    ("factual_accuracy",   "Sachliche Richtigkeit"),
    ("misleading_framing", "Verzerrte Darstellung"),
    ("missing_context",    "Fehlender Kontext"),
]


def render_factcheck_section_label(batch_stats: dict) -> str:
    if batch_stats["total"] > 0:
        bt = batch_stats["batch_time"]
        bt_str = bt.strftime("%H:%M UTC") if bt else "—"
        label = (
            f'Höchster Irreführungs-Index &nbsp;·&nbsp; '
            f'{batch_stats["total"]} Artikel vor-eingestuft ({bt_str})'
            f'&nbsp;·&nbsp; ein Faktencheck pro Durchlauf'
        )
    else:
        label = "Höchster Irreführungs-Index"
    return f'<div class="section-label">{label}</div>'


def render_factcheck_highlight(fc: dict) -> str:
    """Main fact-check card: Irreführungs-Index | sub-score bars | reasoning."""
    ss     = fc.get("sub_scores", {})
    score  = fc.get("fact_check_score") or 0
    FC     = ragebait_color(score)
    ts     = fc["fact_check_at"].strftime("%d.%m.%Y %H:%M UTC") if fc.get("fact_check_at") else "—"
    label  = ss.get("factual_accuracy_label", "NEI")
    counted = ss.get("accuracy_counted", label != "NEI")

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
        f'text-transform:uppercase;letter-spacing:0.06em;">Scores</div></div>'
        f'<div style="{C2h}{ROW_BORDER}"><div class="highlight-title">{fc["title"]}</div></div>'
        f'<div style="{C3h}{ROW_BORDER}">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{T3};'
        f'text-transform:uppercase;letter-spacing:0.06em;">Begründung</div></div>'
    )

    # Sub-score bars
    bars_html = (
        f'<div style="font-size:0.68rem;font-weight:600;color:{FC};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:6px;">Irreführungs-Index</div>'
    )
    for sk, sl in FC_SUB_SCORES:
        if sk == "factual_accuracy" and not counted:
            # Accuracy abstained (NEI) — show honestly, no fabricated bar.
            bars_html += (
                f'<div class="sub-row"><span class="sub-label">{sl}</span>'
                f'<span class="sub-score-val" style="color:{T3};">NEI</span></div>'
                f'<div style="font-size:var(--fs-meta);color:{T3};margin:0 0 8px 0;">'
                f'nicht abschliessend prüfbar — fliesst nicht in den Index</div>'
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
            f'<div class="reasoning-text">{extract_verdict(sr)}</div></div>'
        )

    dim_row = (
        f'<div style="{C1}vertical-align:top;">'
        f'<div style="font-size:0.68rem;font-weight:600;color:{FC};'
        f'text-transform:uppercase;letter-spacing:0.05em;margin-bottom:4px;">Irreführung</div>'
        f'<div style="font-size:3rem;font-weight:600;line-height:1;color:{FC};">{score:.1f}</div></div>'
        f'<div style="{C2}">{bars_html}</div>'
        f'<div style="{C3}">{reasoning_html}</div>'
    )

    row3 = (
        f'<div style="{C1}display:flex;flex-direction:column;justify-content:center;'
        f'padding-top:0.8rem;padding-bottom:0.8rem;">'
        f'<div><span class="tag">{fc["category"]}</span>'
        f'<span class="tag">{fc["word_count"]}w</span></div>'
        f'<div style="font-size:0.65rem;color:{T3};margin-top:0.4rem;">{ts}</div></div>'
        f'<div style="{C2}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;"></div>'
        f'<div style="{C3}display:flex;align-items:center;padding-top:0.8rem;padding-bottom:0.8rem;'
        f'font-size:0.68rem;color:{T3};">'
        f'{fc["fact_check_model"]} &nbsp;·&nbsp; {fc["fact_check_version"]}'
        f'&nbsp;&nbsp;<a href="{fc["url"]}" target="_blank" '
        f'style="color:{FC};text-decoration:none;font-weight:500;">Artikel öffnen ↗</a></div>'
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
            pub = r.get("publisher") or r.get("site") or "Faktencheck"
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
                        f'keine externen Belege gefunden</div>')

        rows += (
            f'<div class="reader-service-cell" style="grid-column:1/-1;border-right:none;'
            f'border-top:1px solid {BDL};">'
            f'<div class="reader-service-cell-label">Behauptung {i+1}</div>'
            f'<div style="margin-bottom:0.4rem;">{claim}</div>{src_html}</div>'
        )

    note = ("" if any_evidence else
            f'<div class="reader-service-cell" style="grid-column:1/-1;border-right:none;'
            f'font-size:var(--fs-meta);color:{T3};">'
            f'Keine externen Belege gefunden — die <em>Sachliche Richtigkeit</em> bleibt '
            f'enthaltsam (NEI). Bewertet wurden nur Darstellung und Kontext.</div>')

    return (
        f'<div class="reader-service-wrap">'
        f'<div class="reader-service-header">Geprüfte Behauptungen &amp; Belege</div>'
        f'<div class="reader-service-body" style="grid-template-columns:1fr;">{rows}{note}</div>'
        f'</div>'
    )


def render_factcheck_empty_state() -> str:
    return (
        f'<div style="color:{T3};text-align:center;padding:2.5rem;font-size:0.85rem;line-height:1.7;">'
        f'Noch kein Faktencheck vorhanden.<br>'
        f'<span style="font-size:0.78rem;">Der Faktencheck-Track ist optional und läuft, sobald '
        f'<code>FACTCHECK_ENABLED</code> gesetzt und die Retrieval-Schlüssel hinterlegt sind.</span></div>'
    )


PINO_SHOUTOUT_HTML = """
<div class="reader-service-wrap">
  <div class="reader-service-header">Was du sonst tun kannst</div>
  <div class="reader-service-body" style="grid-template-columns:1fr;">
    <div class="reader-service-cell" style="border-right:none;">
      <div class="reader-service-cell-label">Selbst gegenprüfen</div>
      Dieses Dashboard prüft pro Durchlauf nur ein Beispiel. Wenn dich beim Lesen eine
      konkrete Behauptung stutzig macht, kannst du sie sofort selbst gegenchecken:
      <a href="https://chromewebstore.google.com/detail/pino-fact-checker/olfaipihfeomkedngnkkmappbojmlmml"
         target="_blank" style="color:var(--text-primary);font-weight:500;">Pino – Fact Checker ↗</a>
      ist eine Browser-Erweiterung, die markierten Text per Rechtsklick KI-gestützt prüft und
      Quellen dazu anzeigt. Wie dieses Werkzeug ersetzt sie keine eigene Urteilskraft — sie ist
      ein schneller erster Anhaltspunkt, den du an den verlinkten Quellen selbst überprüfst.
    </div>
  </div>
</div>
"""

FACTCHECK_EXPLAINER_MD = """
Dieser Track prüft **nicht**, ob ein Artikel emotionalisiert — sondern ob seine *überprüfbaren
Sachbehauptungen* tragen. Pro Durchlauf wird der verdächtigste Artikel ausgewählt, seine Behauptungen
extrahiert und gegen externe Belege geprüft (zuerst Faktencheck-Datenbanken, dann Websuche).

**Irreführungs-Index (0–10, höher = schlechter):** Mittel aus drei Teil-Scores, je ein Sprachmodell-Aufruf.
Der Begriff stammt aus der Faktencheck-Praxis: «irreführend» ist dort die Standard-Bewertung für Inhalte,
die einen falschen Eindruck erzeugen, ohne frei erfunden zu sein.

**Sachliche Richtigkeit** (FEVER, Thorne et al. 2018) — Stützen oder widerlegen externe Belege die Kernbehauptungen? *Open-Book.*
**Verzerrte Darstellung** (Entman 1993) — Drängt die Rahmung eine Deutung auf, die über die Fakten hinausgeht?
**Fehlender Kontext** (Rogers et al. 2017) — Erzeugen technisch korrekte Aussagen durch Auslassung einen irreführenden Eindruck?

**Enthaltsamkeit (NEI):** Reichen die Belege nicht, urteilt die *Sachliche Richtigkeit* mit «NEI» (Not Enough Info)
und fliesst dann **nicht** in den Index ein. Das Werkzeug behauptet nie, ein Medium «lüge», ohne Beleg — im Zweifel
enthält es sich. So bleibt der Index auch dann ehrlich, wenn nur Darstellung und Kontext bewertet werden können.

*KI-generiert, keine menschliche Prüfung. Belege immer an den verlinkten Quellen selbst überprüfen. Open Source (Apache 2.0).*
"""

HEADER_HTML = """
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
"""

EXPLAINER_MD = """
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
"""

RESEARCH_FOOTER_HTML = """
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
"""


FACTCHECK_RESEARCH_FOOTER_HTML = """
<div class="research-footer">

  <div style="font-size:0.68rem;font-weight:600;color:var(--text-secondary);text-transform:uppercase;
              letter-spacing:0.06em;margin-bottom:0.6rem;">Wissenschaftliche Grundlagen — Faktencheck</div>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin-bottom:0.3rem;">Scoring-Grundlage</div>

  <a href="https://aclanthology.org/N18-1074/" target="_blank">
    Thorne et al. (2018) — FEVER: a Large-scale Dataset for Fact Extraction and VERification
  </a>
  <span style="color:var(--text-muted);">
    — Belegbasierte Verifikation mit drei Urteilen: SUPPORTED / REFUTED / <em>NotEnoughInfo</em>.
    Grundlage für <em>Sachliche Richtigkeit</em> und das Enthaltsamkeits-Prinzip (NEI).
  </span><br>

  <a href="https://doi.org/10.1111/j.1460-2466.1993.tb01304.x" target="_blank">
    Entman (1993) — Framing: Toward Clarification of a Fractured Paradigm
  </a>
  <span style="color:var(--text-muted);">
    — Framing durch Auswahl und Betonung lenkt die Deutung, auch ohne falsche Fakten.
    Grundlage für <em>Verzerrte Darstellung</em>.
  </span><br>

  <a href="https://doi.org/10.1037/pspi0000081" target="_blank">
    Rogers et al. (2017) — Artful Paltering: Using Truthful Statements to Mislead Others
  </a>
  <span style="color:var(--text-muted);">
    — «Paltering»: mit technisch wahren Aussagen einen falschen Eindruck erzeugen — meist durch
    weggelassenen Kontext. Grundlage für <em>Fehlender Kontext</em>.
  </span><br>

  <a href="https://doi.org/10.1145/3097983.3098131" target="_blank">
    Hassan et al. (2017) — Toward Automated Fact-Checking (ClaimBuster)
  </a>
  <span style="color:var(--text-muted);">
    — Prüfwürdigkeit («check-worthiness») von Aussagen lässt sich automatisiert einstufen.
    Grundlage für die <em>Vor-Einstufung</em>, die den Artikel pro Durchlauf auswählt.
  </span><br>

  <a href="https://rm.coe.int/information-disorder-toward-an-interdisciplinary-framework-for-researc/168076277c" target="_blank">
    Wardle &amp; Derakhshan (2017) — Information Disorder (Council of Europe)
  </a>
  <span style="color:var(--text-muted);">
    — Typologie von Mis-, Des- und Mal-Information; ordnet ein, warum «irreführend» mehr ist
    als nur «falsch». Begrifflicher Rahmen des Tracks.
  </span>

  <div style="font-size:0.67rem;font-weight:600;color:var(--text-muted);text-transform:uppercase;
              letter-spacing:0.05em;margin:0.7rem 0 0.3rem 0;">Warum das wichtig ist</div>

  <a href="https://doi.org/10.1126/science.aap9559" target="_blank">
    Vosoughi, Roy &amp; Aral (2018) — The spread of true and false news online
  </a>
  <span style="color:var(--text-muted);">
    — Falschnachrichten verbreiten sich auf Twitter weiter, schneller und tiefer als wahre.
    Warum Irreführung gesellschaftliche Kosten hat.
  </span><br>

  <a href="https://doi.org/10.1177/1529100612451018" target="_blank">
    Lewandowsky et al. (2012) — Misinformation and Its Correction
  </a>
  <span style="color:var(--text-muted);">
    — Continued-Influence-Effekt: einmal aufgenommene Fehlinformation wirkt nach, auch nach
    Korrektur. Warum es sich lohnt, sie gar nicht erst ungeprüft zu übernehmen.
  </span><br>

  <a href="https://doi.org/10.1126/sciadv.abo6254" target="_blank">
    Roozenbeek &amp; van der Linden et al. (2022) — Psychological inoculation improves resilience
  </a>
  <span style="color:var(--text-muted);">
    — «Inoculation»: wer Manipulationsmuster kennt, erkennt sie selbst. Warum das eigene Üben
    (z.&nbsp;B. mit Pino) wirksamer ist als jedes fertige Urteil.
  </span>

  <div style="margin-top:1rem;padding-top:0.8rem;border-top:1px solid var(--border-light);
              font-size:0.68rem;color:var(--text-muted);line-height:1.7;">
    <strong style="color:var(--text-secondary);">Zur Einordnung:</strong>
    Faktencheck mit Sprachmodellen ist fehleranfällig. Darum gilt hier konsequent das
    Enthaltsamkeits-Prinzip: ohne ausreichende, belastbare Belege lautet das Urteil zur
    sachlichen Richtigkeit «NEI» und fliesst nicht in den Index ein. Das Werkzeug behauptet nie,
    ein benanntes Medium «lüge» — es weist auf Prüfwürdiges hin und verlinkt die Belege, damit
    du selbst urteilst.
  </div>

</div>
"""
