"""Batch playlist processing CLI."""
from __future__ import annotations

import json
import sys

from app.services.auto_process import check_playlist_for_new_videos, process_lms_webhook


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python scripts/auto_process.py playlist <PLAYLIST_ID> [--dry-run]")
        print("  python scripts/auto_process.py video <YOUTUBE_URL_OR_ID>")
        sys.exit(1)

    command = sys.argv[1]
    if command == "playlist":
        if len(sys.argv) < 3:
            print("ERROR: playlist ID required")
            sys.exit(1)
        playlist_id = sys.argv[2]
        dry_run = "--dry-run" in sys.argv
        result = check_playlist_for_new_videos(playlist_id, dry_run=dry_run)
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    elif command == "video":
        if len(sys.argv) < 3:
            print("ERROR: video URL or ID required")
            sys.exit(1)
        result = process_lms_webhook(sys.argv[2])
        print(json.dumps(result, indent=2, ensure_ascii=False, default=str))
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
