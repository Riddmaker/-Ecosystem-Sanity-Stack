"""
Hourly scheduler — runs the pipeline once immediately on startup,
then at the top of every hour (:00).

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

from src import config
from src.pipeline import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence per-request logs
log = logging.getLogger("scheduler")


def job():
    log.info("Starting pipeline run...")
    try:
        run(hours=config.SCHEDULE_LOOKBACK_HOURS)
    except Exception as e:
        log.error(f"Pipeline run failed: {e}", exc_info=True)
    next_run = schedule.next_run()
    log.info(f"Next run scheduled at {next_run.strftime('%H:%M UTC') if next_run else '?'}")


# Register schedule first so next_run() is populated inside job()
schedule.every().hour.at(":00").do(job)

log.info("Scheduler starting — running pipeline immediately, then every 60 minutes.")
job()

while True:
    schedule.run_pending()
    time.sleep(30)   # check every 30 s — low overhead, responsive to schedule
