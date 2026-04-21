FROM python:3.11-slim

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

# Default: run the frontend. Override with `command:` in docker-compose for the worker.
CMD ["streamlit", "run", "src/frontend/app.py", \
     "--server.port=8501", \
     "--server.headless=true", \
     "--server.address=0.0.0.0"]
