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

# Make `src` importable regardless of how the entrypoint is launched
# (streamlit run src/frontend/app.py does not add /app to sys.path)
ENV PYTHONPATH=/app

# Keep package lists fresh so Jelastic can install its tooling (ssh, cron etc.) on first start
RUN apt-get update

# Publish the Streamlit port so the Jelastic load balancer maps the environment
# URL to it. Without this the image declares no web port, so the public
# *.jcloud.ik-server.com address refuses to connect (Streamlit listens on 8501,
# while Jelastic otherwise defaults to looking for a web app on 8080).
EXPOSE 8501

CMD ["./start.sh"]
