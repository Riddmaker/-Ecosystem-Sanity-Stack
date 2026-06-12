"""
CLI entry point for a single pipeline run.

Usage:
  .venv/Scripts/python run_pipeline.py                     # enabled sources (no blick)
  .venv/Scripts/python run_pipeline.py --hours 2           # last 2 hours only
  .venv/Scripts/python run_pipeline.py --max-articles 20   # cap per source (test)
  .venv/Scripts/python run_pipeline.py --sources 20min     # single source
  .venv/Scripts/python run_pipeline.py --sources blick     # disabled source, run locally

Via Docker (one-shot):
  docker compose run --rm worker
  docker compose run --rm worker python run_pipeline.py --max-articles 10
"""

from dotenv import load_dotenv
load_dotenv()

import argparse
import logging

from src.pipeline import run, ALL_SOURCES, DEFAULT_SOURCES

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("httpx").setLevel(logging.WARNING)  # silence per-request logs

parser = argparse.ArgumentParser(description="Ecosystem Sanity Stack — single pipeline run")
parser.add_argument("--hours", type=float, default=None,
                    help="Only scrape articles published within the last N hours")
parser.add_argument("--max-articles", type=int, default=None,
                    help="Hard cap on articles scraped per source")
parser.add_argument("--sources", nargs="+", choices=ALL_SOURCES, default=DEFAULT_SOURCES,
                    help="Which sources to scrape (default: enabled sources only; "
                         "disabled ones like 'blick' can still be requested explicitly)")
args = parser.parse_args()

run(hours=args.hours, max_articles=args.max_articles, sources=args.sources)
