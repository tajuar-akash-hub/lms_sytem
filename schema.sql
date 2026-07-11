-- Chat-with-the-video feature schema
-- Run against the Neon Postgres instance

-- Enable the vector extension for similarity search
CREATE EXTENSION IF NOT EXISTS vector;

-- Videos: one row per source video
CREATE TABLE IF NOT EXISTS videos (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  source_id TEXT NOT NULL UNIQUE,
  source_type TEXT NOT NULL DEFAULT 'youtube',
  title TEXT,
  transcript_status TEXT DEFAULT 'pending',
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- Transcript chunks: timestamped segments with embeddings for retrieval
CREATE TABLE IF NOT EXISTS transcript_chunks (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
  chunk_text TEXT NOT NULL,
  start_time FLOAT NOT NULL,
  end_time FLOAT NOT NULL,
  chunk_index INT NOT NULL,
  embedding VECTOR(768),  -- Gemini text-embedding-004 produces 768-dim vectors
  created_at TIMESTAMP DEFAULT now()
);

-- Index for fast similarity search within a video
CREATE INDEX IF NOT EXISTS transcript_chunks_video_id_idx
  ON transcript_chunks (video_id);

-- Video summaries: overview + key concepts + suggested questions
CREATE TABLE IF NOT EXISTS video_summaries (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  video_id UUID REFERENCES videos(id) ON DELETE CASCADE UNIQUE,
  overview TEXT NOT NULL,
  key_concepts JSONB NOT NULL DEFAULT '[]'::jsonb,
  suggested_questions JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at TIMESTAMP DEFAULT now(),
  updated_at TIMESTAMP DEFAULT now()
);

-- Chat history: per-student messages tied to a video
CREATE TABLE IF NOT EXISTS chat_messages (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  student_id UUID,
  video_id UUID REFERENCES videos(id) ON DELETE CASCADE,
  role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
  content TEXT NOT NULL,
  cited_timestamp FLOAT,
  created_at TIMESTAMP DEFAULT now()
);

CREATE INDEX IF NOT EXISTS chat_messages_video_student_idx
  ON chat_messages (video_id, student_id, created_at);