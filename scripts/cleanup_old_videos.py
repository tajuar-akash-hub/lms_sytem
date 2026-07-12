"""Remove videos from the DB that are not in a configured playlist."""
from __future__ import annotations

import sys

from app.db_sync import get_sync_conn

CURRENT_PLAYLIST_IDS = [
    "H0K7JQtm_38",
    "1GtyE0lNVPE",
    "F1rGPLa3onY",
    "kXpio_v8l9o",
    "kvAR6dR24IE",
    "VaHq68QhpEQ",
    "e-bO64mq74c",
    "C56P2HcLAN0",
]


def main() -> None:
    conn = get_sync_conn()
    cur = conn.cursor()

    cur.execute("SELECT source_id, title, transcript_status FROM videos ORDER BY created_at;")
    rows = cur.fetchall()
    print(f"Found {len(rows)} videos in DB:")
    for row in rows:
        title = row[1][:60] if row[1] else "(no title)"
        print(f"  - {row[0]}  [{row[2]}]  {title}")

    cur.execute(
        "DELETE FROM videos WHERE source_id != ALL(%s) RETURNING source_id, title;",
        (CURRENT_PLAYLIST_IDS,),
    )
    deleted = cur.fetchall()
    conn.commit()

    print(f"\nDeleted {len(deleted)} videos (and their chunks/summaries/messages):")
    for row in deleted:
        title = row[1][:60] if row[1] else ""
        print(f"  - {row[0]}  {title}")

    cur.execute("SELECT count(*) FROM videos;")
    remaining = cur.fetchone()[0]
    print(f"\nVideos remaining: {remaining}")

    cur.close()
    conn.close()


if __name__ == "__main__":
    main()
