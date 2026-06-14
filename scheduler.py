"""
Hourly scheduler — runs the pipeline once immediately on startup,
then at the top of every hour (:00).

Each run is launched as a SUBPROCESS (run_pipeline.py) that exits when it
finishes, so the memory peak of a scrape + score cycle is reclaimed by the OS
between runs. Running the pipeline in-process kept ~280 MiB resident at idle
(Python does not return a grown heap to the OS), which pinned the container at
its cloudlet ceiling. A one-shot subprocess keeps the long-lived daemon tiny.

Usage:
  .venv/Scripts/python scheduler.py

Via Docker (long-running daemon):
  docker compose up -d scheduler
"""

from dotenv import load_dotenv
load_dotenv()

import logging
import os
import subprocess
import sys
import time

import schedule

from src import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence per-request logs
log = logging.getLogger("scheduler")

# Absolute path so the subprocess resolves regardless of the daemon's CWD.
RUN_PIPELINE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "run_pipeline.py")


def job():
    """Run one pipeline cycle in a child process so its memory is freed on exit."""
    log.info("Starting pipeline run (subprocess)...")
    try:
        result = subprocess.run(
            [sys.executable, "-u", RUN_PIPELINE,
             "--hours", str(config.SCHEDULE_LOOKBACK_HOURS)],
            check=False,
        )
        if result.returncode == 0:
            log.info("Pipeline subprocess finished cleanly.")
        else:
            log.error("Pipeline subprocess exited with code %d", result.returncode)
    except Exception:
        log.exception("Failed to launch pipeline subprocess")
    next_run = schedule.next_run()
    log.info("Next run scheduled at %s",
             next_run.strftime("%H:%M UTC") if next_run else "?")


# Register schedule first so next_run() is populated inside job()
schedule.every().hour.at(":00").do(job)

log.info("Scheduler starting — running pipeline immediately, then at the top of every hour.")
job()

while True:
    schedule.run_pending()
    time.sleep(30)   # check every 30 s — low overhead, responsive to schedule
