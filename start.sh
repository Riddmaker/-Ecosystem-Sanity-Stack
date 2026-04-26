#!/bin/sh
set -e

python -u scheduler.py &

exec streamlit run src/frontend/app.py \
    --server.port=8501 \
    --server.headless=true \
    --server.address=0.0.0.0
