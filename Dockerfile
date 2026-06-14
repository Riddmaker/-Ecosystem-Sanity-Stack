FROM python:3.11-slim-bookworm

WORKDIR /app

# System deps: gcc + libpq for psycopg2
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Note: the Blick scraper needs Playwright + Chromium, but Blick is disabled in
# production (config.DISABLED_SOURCES — Akamai 403s datacenter IPs), so this
# image ships WITHOUT them to stay small. Playwright is imported lazily, so the
# pipeline runs fine without it. To scrape Blick locally:
#   pip install playwright && playwright install chromium

COPY src/ ./src/
COPY run_pipeline.py .
COPY scheduler.py .
COPY start.sh .
RUN chmod +x start.sh

# Make `src` importable regardless of how the entrypoint is launched
# (streamlit run src/frontend/app.py does not add /app to sys.path)
ENV PYTHONPATH=/app

# Keep package lists fresh so Jelastic can install its tooling (ssh, cron etc.) on first start
RUN apt-get update

# Publish the web port. Jelastic routes the environment URL to 8080
# (JELASTIC_PRIORITY_PORTS=8080), so start.sh serves Streamlit there.
EXPOSE 8080

CMD ["./start.sh"]
