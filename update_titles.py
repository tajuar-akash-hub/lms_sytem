"""One-off script to update existing video titles in the DB using the
known playlist titles from `playlist_videos.tsv`.
"""
import csv
import os
from pathlib import Path
from dotenv import load_dotenv
import psycopg2

load_dotenv(Path(__file__).parent / ".env")
TSV_PATH = Path(__file__).parent / "playlist_raw.txt"


def main():
    if not TSV_PATH.exists():
        print(f"ERROR: {TSV_PATH} not found")
        return
    title_map = {}
    with open(TSV_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if "\t" not in line:
                continue
            vid_id, title = line.split("\t", 1)
            title_map[vid_id.strip()] = title.strip()

    print(f"Loaded {len(title_map)} playlist titles")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    conn.autocommit = True
    cur = conn.cursor()
    cur.execute("SELECT source_id, title FROM videos;")
    rows = cur.fetchall()
    updated = 0
    for sid, current_title in rows:
        new_title = title_map.get(sid)
        if new_title and new_title != current_title:
            cur.execute(
                "UPDATE videos SET title = %s, updated_at = now() WHERE source_id = %s;",
                (new_title, sid),
            )
            print(f"  {sid}: '{current_title}' -> '{new_title[:80]}'")
            updated += 1
    print(f"\nUpdated {updated}/{len(rows)} videos")
    cur.close()
    conn.close()


if __name__ == "__main__":
    main()