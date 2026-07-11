"""One-off script: remove videos from the DB that are NOT in the current MLOps playlist.

Use this when switching playlists. CASCADE on FKs takes care of chunks/summaries/messages.
"""
from pathlib import Path

from dotenv import load_dotenv
import os
import psycopg2

load_dotenv(Path(__file__).parent / ".env")

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

conn = psycopg2.connect(os.getenv("DATABASE_URL"))
cur = conn.cursor()

# Show what's currently in the DB
cur.execute("SELECT source_id, title, transcript_status FROM videos ORDER BY created_at;")
rows = cur.fetchall()
print(f"Found {len(rows)} videos in DB:")
for r in rows:
    print(f"  - {r[0]}  [{r[2]}]  {r[1][:60] if r[1] else '(no title)'}")

# Delete anything not in the current playlist. FKs cascade.
cur.execute(
    "DELETE FROM videos WHERE source_id != ALL(%s) RETURNING source_id, title;",
    (CURRENT_PLAYLIST_IDS,),
)
deleted = cur.fetchall()
conn.commit()

print(f"\nDeleted {len(deleted)} videos (and their chunks/summaries/messages):")
for r in deleted:
    print(f"  - {r[0]}  {r[1][:60] if r[1] else ''}")

# Show what's left
cur.execute("SELECT count(*) FROM videos;")
n_left = cur.fetchone()[0]
print(f"\nVideos remaining: {n_left}")

cur.close()
conn.close()
