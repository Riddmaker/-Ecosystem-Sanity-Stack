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

exec streamlit run src/frontend/app.py \
    --server.port=8501 \
    --server.headless=true \
    --server.address=0.0.0.0
