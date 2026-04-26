FROM python:3.11-slim-bookworm

WORKDIR /app

# System deps: gcc + libpq for psycopg2, and Playwright browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium + its system dependencies (needed for Blick scraper)
RUN playwright install chromium --with-deps

COPY src/ ./src/
COPY run_pipeline.py .
COPY scheduler.py .
COPY start.sh .
RUN chmod +x start.sh

# Keep package lists fresh so Jelastic can install its tooling (ssh, cron etc.) on first start
RUN apt-get update

CMD ["./start.sh"]
