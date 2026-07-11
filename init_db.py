"""Initialize the database schema and verify tables exist."""
import os
import sys
from pathlib import Path

import psycopg2
from dotenv import load_dotenv

# Load .env from the project root (where this script lives)
load_dotenv(Path(__file__).parent / ".env")

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not set in .env", file=sys.stderr)
    sys.exit(1)

SCHEMA_PATH = Path(__file__).parent / "schema.sql"

EXPECTED_TABLES = ["videos", "transcript_chunks", "video_summaries", "chat_messages"]


def main():
    print(f"Connecting to Neon...")
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = True
    cur = conn.cursor()

    print(f"Running schema from {SCHEMA_PATH}...")
    schema_sql = SCHEMA_PATH.read_text(encoding="utf-8")
    cur.execute(schema_sql)

    # Verify the tables exist
    cur.execute(
        """
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = 'public'
        ORDER BY table_name;
        """
    )
    found = {row[0] for row in cur.fetchall()}
    print(f"Tables found in 'public' schema: {sorted(found)}")

    missing = [t for t in EXPECTED_TABLES if t not in found]
    if missing:
        print(f"ERROR: Missing tables: {missing}", file=sys.stderr)
        sys.exit(1)

    # Confirm pgvector is installed
    cur.execute("SELECT extname FROM pg_extension WHERE extname = 'vector';")
    if cur.fetchone():
        print("pgvector extension: INSTALLED")
    else:
        print("WARNING: pgvector extension not found", file=sys.stderr)

    cur.close()
    conn.close()
    print("\nDatabase is ready.")


if __name__ == "__main__":
    main()