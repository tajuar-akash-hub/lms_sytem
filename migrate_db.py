"""One-time data migration: source Neon DB -> destination Neon DB.

Reads all rows from the 4 app tables on the SOURCE DB (from .env's OLD_DATABASE_URL)
and inserts them into the DESTINATION DB (from .env's DATABASE_URL).

PREREQUISITES (run once on the destination DB before this script):
    alembic upgrade head

This creates the videos, transcript_chunks, video_summaries, and
chat_messages tables (plus the LMS app's other tables). Without the
migration, this script will fail with "relation does not exist".

Run with:
    OLD_DATABASE_URL=... DATABASE_URL=... python migrate_db.py

Or just set both in .env and run: python migrate_db.py

NOTE: This script is now mostly historical. The default .env points at the
new Neon DB (ep-spring-shape) and OLD_DATABASE_URL is unset. To re-run a
migration you must explicitly set OLD_DATABASE_URL in .env or on the
command line.
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
    print("Set both OLD_DATABASE_URL and DATABASE_URL in .env")
    print("DATABASE_URL is the destination (where to copy to).")
    print("OLD_DATABASE_URL is the source (where to copy from).")
    sys.exit(1)

if OLD_URL == NEW_URL:
    print("OLD and NEW URLs are identical - nothing to do.")
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
        src_cur.execute(f"SELECT {cols_sql} FROM {table};")
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
    print(f"SOURCE: {OLD_URL.split('@')[-1]}")
    print(f"DEST:   {NEW_URL.split('@')[-1]}")
    print()
    main()
    print("\nDone.")
