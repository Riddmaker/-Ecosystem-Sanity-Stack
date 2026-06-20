#!/bin/sh
set -e

echo "[start.sh] Waiting for PostgreSQL at ${POSTGRES_HOST}:${POSTGRES_PORT}..."
until python -c "
import os, sys, psycopg2
try:
    conn = psycopg2.connect(os.environ['DATABASE_URL'])
    conn.close()
    sys.exit(0)
except Exception as e:
    print(f'  not ready: {e}', flush=True)
    sys.exit(1)
"; do
    sleep 2
done
echo "[start.sh] PostgreSQL is ready."

# Patch Streamlit's static index.html so link-preview crawlers (which don't run
# JS) see our title + description instead of the default "Streamlit". set_page_config
# only updates the title client-side, which social/chat unfurlers never execute.
# Idempotent (guarded by a marker) and non-fatal if Streamlit's markup changes.
python - <<'PY' || echo "[start.sh] index.html meta patch skipped"
import pathlib, re, streamlit
from src.strings import UI_PAGE_TITLE, UI_SHARE_DESCRIPTION

path = pathlib.Path(streamlit.__file__).parent / "static" / "index.html"
html = path.read_text(encoding="utf-8")
MARK = "<!-- media-sanity-meta -->"
if MARK in html:
    print("[start.sh] index.html meta already patched")
else:
    html = re.sub(r"<title>.*?</title>", f"<title>{UI_PAGE_TITLE}</title>",
                  html, count=1, flags=re.S)
    meta = (
        f'{MARK}'
        f'<meta name="description" content="{UI_SHARE_DESCRIPTION}"/>'
        f'<meta property="og:title" content="{UI_PAGE_TITLE}"/>'
        f'<meta property="og:description" content="{UI_SHARE_DESCRIPTION}"/>'
        f'<meta property="og:type" content="website"/>'
        f'<meta name="twitter:card" content="summary"/>'
    )
    html = re.sub(r"(<head[^>]*>)", lambda m: m.group(1) + meta, html, count=1)
    path.write_text(html, encoding="utf-8")
    print("[start.sh] patched Streamlit index.html meta tags")
PY

python -u scheduler.py &

# Cloudflare Tunnel: only when a token is provided (prod). Without TUNNEL_TOKEN
# this is a no-op, so local dev / docker-compose runs are unaffected. The tunnel
# is outbound-only; its public hostname is mapped to http://localhost:8080 in
# the Cloudflare Zero Trust dashboard, letting the env run with no public IP.
if [ -n "${TUNNEL_TOKEN}" ]; then
    echo "[start.sh] Starting Cloudflare Tunnel..."
    cloudflared tunnel --no-autoupdate run --token "${TUNNEL_TOKEN}" &
else
    echo "[start.sh] TUNNEL_TOKEN not set — Cloudflare Tunnel disabled."
fi

# Serve on 8080 — the port Jelastic's load balancer routes the environment
# URL to (JELASTIC_PRIORITY_PORTS=8080). Locally, docker-compose maps host
# 8501 → container 8080 so http://localhost:8501 still works in dev.
exec streamlit run src/frontend/app.py \
    --server.port=8080 \
    --server.headless=true \
    --server.address=0.0.0.0
