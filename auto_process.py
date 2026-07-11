"""Auto-process new videos.

Two entry points:
  - check_playlist_for_new_videos(playlist_id): fetches the YouTube playlist,
    compares against the DB, and runs the pipeline on any new IDs.
  - process_video_url(url_or_id, source_type="youtube"): processes a single
    video given by URL or ID — used by both the poll path and the LMS
    webhook.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import psycopg2
import yt_dlp

from pipeline import process_video


def get_existing_source_ids() -> set:
    """Return the set of source_ids already in the DB."""
    import psycopg2
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")
    conn = psycopg2.connect(os.getenv("DATABASE_URL"))
    cur = conn.cursor()
    cur.execute("SELECT source_id FROM videos;")
    ids = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return ids


def fetch_playlist_video_ids(playlist_id: str) -> List[dict]:
    """Use yt-dlp to enumerate a playlist. Returns [{id, title}, ...]."""
    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "skip_download": True,
    }
    url = f"https://www.youtube.com/playlist?list={playlist_id}"
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
    entries = info.get("entries") or []
    out = []
    for e in entries:
        vid_id = e.get("id")
        title = e.get("title")
        if vid_id and len(vid_id) == 11:
            out.append({"id": vid_id, "title": title})
    return out


def check_playlist_for_new_videos(
    playlist_id: str,
    dry_run: bool = False,
) -> dict:
    """Compare the playlist against the DB, process any new IDs.

    Returns a summary dict: {total_in_playlist, already_in_db, newly_processed, errors}.
    Set dry_run=True to just report what would be processed without running anything.
    """
    print(f"Checking playlist {playlist_id}...")
    playlist_entries = fetch_playlist_video_ids(playlist_id)
    existing = get_existing_source_ids()
    new_entries = [e for e in playlist_entries if e["id"] not in existing]
    print(f"  playlist has {len(playlist_entries)} videos, "
          f"{len(existing)} already in DB, {len(new_entries)} new")

    newly_processed = []
    errors = []
    for entry in new_entries:
        vid_id = entry["id"]
        title = entry.get("title") or vid_id
        if dry_run:
            print(f"  [dry-run] would process: {vid_id} — {title[:60]}")
            continue
        print(f"  processing: {vid_id} — {title[:60]}")
        try:
            result = process_video(vid_id)
            newly_processed.append({
                "source_id": vid_id,
                "title": title,
                "n_chunks": result.get("n_chunks"),
            })
        except Exception as e:
            print(f"  ERROR on {vid_id}: {e!r}")
            errors.append({"source_id": vid_id, "error": str(e)})

    return {
        "playlist_id": playlist_id,
        "total_in_playlist": len(playlist_entries),
        "already_in_db": len(existing),
        "newly_processed": newly_processed,
        "errors": errors,
        "dry_run": dry_run,
    }


def process_lms_webhook(
    video_url_or_id: str,
    source_type: str = "youtube",
    title: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> dict:
    """Process a video uploaded via the LMS webhook.

    For now, this calls the same pipeline as YouTube videos. When the LMS
    supplies its own hosted video file (S3, R2, etc.), this function will
    download that file directly instead of going through yt-dlp.
    """
    # Defer import to avoid loading pipeline at module import time
    from pipeline import process_video

    result = process_video(video_url_or_id)
    return {
        "video_id": result.get("video_id"),
        "source_id": result.get("source_id"),
        "title": result.get("title"),
        "n_chunks": result.get("n_chunks"),
        "summary": result.get("summary"),
        "source_type": source_type,
        "received_metadata": metadata,
    }


# ---------------------------------------------------------------------------
# CLI for ad-hoc use
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python auto_process.py playlist <PLAYLIST_ID> [--dry-run]")
        print("  python auto_process.py video <YOUTUBE_URL_OR_ID>")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "playlist":
        if len(sys.argv) < 3:
            print("ERROR: playlist ID required")
            sys.exit(1)
        playlist_id = sys.argv[2]
        dry = "--dry-run" in sys.argv
        result = check_playlist_for_new_videos(playlist_id, dry_run=dry)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif cmd == "video":
        if len(sys.argv) < 3:
            print("ERROR: video URL or ID required")
            sys.exit(1)
        url_or_id = sys.argv[2]
        result = process_lms_webhook(url_or_id)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)