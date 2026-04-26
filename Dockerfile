FROM python:3.11-slim-bookworm

WORKDIR /app

# System deps: gcc + libpq for psycopg2, and Playwright browser dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright's Chromium + its system dependencies (needed for Blick scraper)
RUN playwright install chromium --with-deps

COPY src/ ./src/
COPY run_pipeline.py .
COPY scheduler.py .
COPY start.sh .
RUN chmod +x start.sh

CMD ["./start.sh"]
