"""Copy video RAG data from a source Neon DB into the current one.

Usage:
  OLD_DATABASE_URL=... python scripts/migrate_videos.py

OLD_DATABASE_URL must be set explicitly. If unset, the script aborts.
The legacy `ep-steep-glitter` host is no longer used.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import json

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

OLD_URL = os.getenv("OLD_DATABASE_URL")
NEW_URL = os.getenv("DATABASE_URL_UNPOOLED") or os.getenv("DATABASE_URL")

if not OLD_URL:
    print("Set OLD_DATABASE_URL in .env to the source Neon DB you want to migrate from.")
    sys.exit(1)

TABLES = ("videos", "transcript_chunks", "video_summaries", "chat_messages")


def get_columns(cur, table: str) -> list[str]:
    cur.execute(
        """
        SELECT column_name FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return [row[0] for row in cur.fetchall()]


def copy_videos(src_cur, dst_cur) -> dict[str, str]:
    """Return mapping old_video_id -> new_video_id for copied rows."""
    id_map: dict[str, str] = {}
    src_cols = get_columns(src_cur, "videos")
    dst_cols = get_columns(dst_cur, "videos")
    shared = [col for col in src_cols if col in dst_cols and col != "id"]
    src_cur.execute(
        f"SELECT id, {', '.join(c for c in shared if c != 'id')} FROM videos ORDER BY created_at;"
    )
    rows = src_cur.fetchall()
    dst_cur.execute("SELECT source_id, id FROM videos;")
    existing = {row[0]: str(row[1]) for row in dst_cur.fetchall()}

    copied = 0
    for row in rows:
        old_id = str(row[0])
        values = dict(zip([c for c in shared if c != "id"], row[1:]))
        source_id = values["source_id"]
        if source_id in existing:
            id_map[old_id] = existing[source_id]
            continue
        insert_cols = list(values.keys())
        placeholders = ", ".join(["%s"] * len(insert_cols))
        dst_cur.execute(
            f"""
            INSERT INTO videos (id, {', '.join(insert_cols)})
            VALUES (gen_random_uuid(), {placeholders})
            RETURNING id;
            """,
            tuple(values[col] for col in insert_cols),
        )
        new_id = str(dst_cur.fetchone()[0])
        id_map[old_id] = new_id
        copied += 1
        print(f"  + video {source_id}")

    print(f"  videos copied: {copied}, linked existing: {len(id_map) - copied}")
    return id_map


def get_column_types(cur, table: str) -> dict[str, str]:
    cur.execute(
        """
        SELECT column_name, data_type
        FROM information_schema.columns
        WHERE table_schema = 'public' AND table_name = %s
        ORDER BY ordinal_position
        """,
        (table,),
    )
    return {row[0]: row[1] for row in cur.fetchall()}


def copy_child_table(
    table: str,
    src_cur,
    dst_cur,
    id_map: dict[str, str],
    video_col: str = "video_id",
) -> int:
    src_cols = get_columns(src_cur, table)
    dst_cols = get_columns(dst_cur, table)
    dst_types = get_column_types(dst_cur, table)
    shared = [col for col in src_cols if col in dst_cols and col != "id"]
    src_cur.execute(f"SELECT {', '.join(['id'] + shared)} FROM {table};")
    rows = src_cur.fetchall()

    insert_cols = shared
    placeholders = ", ".join(["%s"] * len(insert_cols))
    insert_sql = f"INSERT INTO {table} ({', '.join(insert_cols)}) VALUES ({placeholders})"

    inserted = 0
    for row in rows:
        row_dict = dict(zip(["id"] + shared, row))
        old_video_id = str(row_dict[video_col])
        new_video_id = id_map.get(old_video_id)
        if not new_video_id:
            continue
        if table in ("transcript_chunks", "video_summaries"):
            dst_cur.execute(
                f"SELECT 1 FROM {table} WHERE {video_col} = %s LIMIT 1;",
                (new_video_id,),
            )
            if dst_cur.fetchone():
                continue
        values = []
        for col in insert_cols:
            value = row_dict[col]
            if col == video_col:
                value = new_video_id
            elif dst_types.get(col) == "jsonb":
                if isinstance(value, (list, dict)):
                    value = psycopg2.extras.Json(value)
                elif isinstance(value, str):
                    value = psycopg2.extras.Json(json.loads(value))
            values.append(value)
        dst_cur.execute(insert_sql, values)
        inserted += 1

    return inserted


def main() -> None:
    if not NEW_URL:
        print("DATABASE_URL is not set in .env")
        sys.exit(1)
    if OLD_URL == NEW_URL:
        print("OLD and NEW database URLs are identical.")
        sys.exit(1)

    print(f"Source: {OLD_URL.split('@')[1].split('/')[0]}")
    print(f"Target: {NEW_URL.split('@')[1].split('/')[0]}")

    src = psycopg2.connect(OLD_URL)
    dst = psycopg2.connect(NEW_URL)
    try:
        with src.cursor() as src_cur, dst.cursor() as dst_cur:
            print("\nMigrating videos...")
            id_map = copy_videos(src_cur, dst_cur)

            for table in ("transcript_chunks", "video_summaries", "chat_messages"):
                print(f"Migrating {table}...")
                count = copy_child_table(table, src_cur, dst_cur, id_map)
                print(f"  inserted {count} rows")

        dst.commit()
        print("\nDone.")
    except Exception:
        dst.rollback()
        raise
    finally:
        src.close()
        dst.close()


if __name__ == "__main__":
    main()
