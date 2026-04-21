"""
Migration v4 -> v5

Changes:
  - Add column: pre_score FLOAT
  - Add column: pre_score_model VARCHAR(100)
  - Add column: pre_score_at TIMESTAMP WITH TIME ZONE
  - Add index: ix_articles_pre_score

Run with:
  .venv/Scripts/python migrate_v4_to_v5.py
"""

from dotenv import load_dotenv
load_dotenv()

from sqlalchemy import text
from src.db.connection import build_engine

engine = build_engine()

print("Migrating v4 -> v5: adding pre-score columns...")

with engine.connect() as conn:
    conn.execute(text(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS pre_score FLOAT;"
    ))
    conn.execute(text(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS pre_score_model VARCHAR(100);"
    ))
    conn.execute(text(
        "ALTER TABLE articles ADD COLUMN IF NOT EXISTS pre_score_at TIMESTAMP WITH TIME ZONE;"
    ))
    conn.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_articles_pre_score ON articles (pre_score);"
    ))
    conn.commit()

print("OK: pre_score, pre_score_model, pre_score_at added.")
print("Run run_pipeline.py to pre-score existing articles.")
