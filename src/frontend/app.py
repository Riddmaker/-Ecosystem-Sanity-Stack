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

from src.frontend import components, data, styles

# ─────────────────────────────────────────────────────────────
# THEME STATE + CSS
# ─────────────────────────────────────────────────────────────
if "theme" not in st.session_state:
    st.session_state.theme = "system"

theme = st.session_state.theme
st.markdown(f"<style>{styles.base_css(theme)}</style>", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# DATA
# ─────────────────────────────────────────────────────────────
all_articles = data.load_articles()
batch_stats  = data.load_batch_stats()
latest       = data.pick_highlight(all_articles)

# ─────────────────────────────────────────────────────────────
# HEADER + THEME TOGGLE
# ─────────────────────────────────────────────────────────────
col_title, col_toggle = st.columns([5, 1])

with col_title:
    st.markdown(components.HEADER_HTML, unsafe_allow_html=True)

with col_toggle:
    chosen = st.segmented_control(
        "Theme",
        styles.THEME_EMOJIS,
        default=styles.THEME_EMOJIS[styles.THEME_OPTIONS.index(theme)],
        selection_mode="single",
        label_visibility="collapsed",
    )
    if chosen is not None:
        new_theme = styles.THEME_OPTIONS[styles.THEME_EMOJIS.index(chosen)]
        if new_theme != theme:
            st.session_state.theme = new_theme
            st.rerun()

with st.expander("Was misst dieses Dashboard?"):
    st.markdown(components.EXPLAINER_MD)

# ─────────────────────────────────────────────────────────────
# ARTICLE HIGHLIGHT
# ─────────────────────────────────────────────────────────────
if latest:
    st.markdown(components.render_section_label(batch_stats), unsafe_allow_html=True)
    st.markdown(components.render_highlight(latest), unsafe_allow_html=True)

    reader_service = latest["details"].get("reader_service")
    if reader_service:
        reader_html = components.render_reader_service(reader_service)
        if reader_html:
            st.markdown(reader_html, unsafe_allow_html=True)
else:
    st.markdown(components.render_empty_state(), unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────
# SEGMENTED CONTROL OVERRIDE — injected late so it wins over
# Streamlit's own component CSS (later in cascade = higher priority).
# Always rendered — even empty — so the DOM structure stays identical
# across theme switches.
# ─────────────────────────────────────────────────────────────
st.markdown(
    f"<style>{styles.segmented_control_override(theme)}</style>",
    unsafe_allow_html=True,
)

# ─────────────────────────────────────────────────────────────
# RESEARCH FOOTER
# ─────────────────────────────────────────────────────────────
with st.expander("Wissenschaftliche Grundlagen"):
    st.markdown(components.RESEARCH_FOOTER_HTML, unsafe_allow_html=True)
