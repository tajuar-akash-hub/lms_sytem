from __future__ import annotations

from typing import Any

import yt_dlp

from app.db_sync import get_sync_conn
from app.services.video_pipeline import process_video


def get_existing_source_ids() -> set[str]:
    conn = get_sync_conn()
    cur = conn.cursor()
    cur.execute("SELECT source_id FROM videos;")
    ids = {row[0] for row in cur.fetchall()}
    cur.close()
    conn.close()
    return ids


def fetch_playlist_video_ids(playlist_id: str) -> list[dict[str, str | None]]:
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
    playlist_entries: list[dict[str, str | None]] = []
    for entry in entries:
        video_id = entry.get("id")
        title = entry.get("title")
        if video_id and len(video_id) == 11:
            playlist_entries.append({"id": video_id, "title": title})
    return playlist_entries


def check_playlist_for_new_videos(
    playlist_id: str,
    dry_run: bool = False,
) -> dict[str, Any]:
    playlist_entries = fetch_playlist_video_ids(playlist_id)
    existing = get_existing_source_ids()
    new_entries = [entry for entry in playlist_entries if entry["id"] not in existing]

    newly_processed: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for entry in new_entries:
        video_id = entry["id"]
        title = entry.get("title") or video_id
        if dry_run:
            continue
        try:
            result = process_video(video_id)
            newly_processed.append(
                {
                    "source_id": video_id,
                    "title": title,
                    "n_chunks": result.get("n_chunks"),
                }
            )
        except Exception as exc:
            errors.append({"source_id": video_id, "error": str(exc)})

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
    title: str | None = None,
    metadata: dict | None = None,
) -> dict[str, Any]:
    del title
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
