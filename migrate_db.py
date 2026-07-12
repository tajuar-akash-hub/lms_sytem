"""One-time data migration: old Neon DB -> new Neon DB.

Reads all rows from the 4 app tables on the OLD DB (from .env's DATABASE_URL)
and inserts them into the NEW DB (from .env's NEW_DATABASE_URL).

PREREQUISITES (run once on the new DB before this script):
    alembic upgrade head

This creates the videos, transcript_chunks, video_summaries, and
chat_messages tables (plus the LMS app's other tables). Without the
migration, this script will fail with "relation does not exist".

Run with:
    OLD_DATABASE_URL=... DATABASE_URL=... python migrate_db.py

Or just set both in .env and run: python migrate_db.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).parent / ".env")

OLD_URL = os.getenv("OLD_DATABASE_URL")
NEW_URL = os.getenv("DATABASE_URL")

if not OLD_URL or not NEW_URL:
    print("Set both OLD_DATABASE_URL and NEW_DATABASE_URL in .env")
    print("OLD_DATABASE_URL is the current database; NEW_DATABASE_URL is where to copy to.")
    sys.exit(1)

if OLD_URL == NEW_URL:
    print("OLD and NEW URLs are identical — nothing to do.")
    sys.exit(1)

TABLES = ["videos", "transcript_chunks", "video_summaries", "chat_messages"]


def get_columns(cur, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [r[0] for r in cur.fetchall()]


def get_columns_with_types(cur, table: str) -> list[tuple[str, str]]:
    cur.execute(
        """
        SELECT column_name, data_type FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [(r[0], r[1]) for r in cur.fetchall()]


def copy_table(table: str) -> int:
    src = psycopg2.connect(OLD_URL)
    dst = psycopg2.connect(NEW_URL)
    try:
        src_cur = src.cursor()
        dst_cur = dst.cursor()

        # Get all rows from source
        col_types = get_columns_with_types(src_cur, table)
        cols = [c[0] for c in col_types]
        cols_sql = ", ".join(cols)
        jsonb_cols = {c[0] for c in col_types if c[1] == "jsonb"}
        src_cur.execute(f'SELECT {cols_sql} FROM {table};')
        rows = src_cur.fetchall()
        print(f"  source: {len(rows)} rows")

        if not rows:
            return 0

        # Build insert with ON CONFLICT DO NOTHING. For jsonb columns,
        # wrap the value in psycopg2.extras.Json so it serializes as JSON
        # instead of text/array.
        placeholders = ", ".join(["%s"] * len(cols))
        insert_sql = (
            f"INSERT INTO {table} ({cols_sql}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO NOTHING;"
        )

        inserted = 0
        for row in rows:
            # Convert jsonb values to Json so psycopg2 sends proper JSON
            adapted = [
                psycopg2.extras.Json(v) if cols[i] in jsonb_cols else v
                for i, v in enumerate(row)
            ]
            dst_cur.execute(insert_sql, adapted)
            inserted += dst_cur.rowcount

        dst.commit()
        print(f"  inserted: {inserted}")
        return inserted
    finally:
        src.close()
        dst.close()


def main() -> None:
    for table in TABLES:
        print(f"\n[{table}]")
        try:
            copy_table(table)
        except Exception as e:
            print(f"  ERROR: {e!r}")
            raise


if __name__ == "__main__":
    print(f"OLD: {OLD_URL.split('@')[-1]}")
    print(f"NEW: {NEW_URL.split('@')[-1]}")
    print()
    main()
    print("\nDone.")