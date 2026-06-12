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

python -u scheduler.py &

# Serve on 8080 — the port Jelastic's load balancer routes the environment
# URL to (JELASTIC_PRIORITY_PORTS=8080). Locally, docker-compose maps host
# 8501 → container 8080 so http://localhost:8501 still works in dev.
exec streamlit run src/frontend/app.py \
    --server.port=8080 \
    --server.headless=true \
    --server.address=0.0.0.0
