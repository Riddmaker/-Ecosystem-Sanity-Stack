"""
Hourly scheduler — runs the pipeline once immediately on startup,
then every 60 minutes.

Usage:
  .venv/Scripts/python scheduler.py

Via Docker (long-running daemon):
  docker compose up -d scheduler
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import time
import schedule
from datetime import datetime, timezone

from src.pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [scheduler] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger(__name__)


def job():
    log.info("Starting pipeline run...")
    try:
        # hours=1.5 — fetch articles published in the last 90 min (overlap guards
        # against articles that publish slightly before the previous run window)
        run(hours=1.5)
    except Exception as e:
        log.error(f"Pipeline run failed: {e}", exc_info=True)
    next_run = schedule.next_run()
    log.info(f"Next run scheduled at {next_run.strftime('%H:%M UTC') if next_run else '?'}")


# Register schedule first so next_run() is populated inside job()
schedule.every(60).minutes.do(job)

log.info("Scheduler starting — running pipeline immediately, then every 60 minutes.")
job()

while True:
    schedule.run_pending()
    time.sleep(30)   # check every 30 s — low overhead, responsive to schedule
