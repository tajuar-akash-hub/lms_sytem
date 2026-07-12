# Database Architecture: EdTech Platform (FastAPI + PostgreSQL on Neon)

## Overview
This document defines the PostgreSQL database schema and business logic requirements for an AI-driven EdTech platform. The schema is normalized to 3NF. Use this to generate FastAPI ORM models (SQLAlchemy/SQLModel), Pydantic schemas, and Celery/Background tasks.

## 1. Core Enumerations (PostgreSQL ENUM types)
- `LeagueTier`: IRON, BRONZE, SILVER, GOLD, PLATINUM, ASCENDANT, IMMORTAL, RADIANT
- `ModuleType`: REGULAR, EXAM, CONCEPTUAL, GROWTH_DAY
- `PairChallengeStatus`: PENDING, ACCEPTED, REJECTED, COMPLETED, FAILED
- `LearningStatus`: WEAK, IMPROVING, RESOLVED
- `ExamType`: MCQ, CODING, WRITTEN, MIXED

---

## 2. Core Tables

### `students`
The central user table.
- `id`: UUID (Primary Key)
- `name`: VARCHAR(255)
- `email`: VARCHAR(255) (Unique, Indexed)
- `phone_number`: VARCHAR(20)
- `points`: INT (Default: 0) - *Used for unlocking AI Interviews*
- `pair_points`: INT (Default: 0) - *Used for Premium AI Features*
- `streak_freeze_points`: INT (Default: 0)
- `current_module_id`: UUID (Foreign Key -> `modules.id`)
- `job_profile`: TEXT
- `life_goal`: TEXT
- `soul`: JSONB - *Stores dynamic AI insights (Weakness, Watch time, Learning pace)*
- `current_league`: ENUM `LeagueTier` (Default: IRON)
- `created_at`: TIMESTAMP

### `modules`
- `id`: UUID (Primary Key)
- `name`: VARCHAR(255)
- `type`: ENUM `ModuleType`
- `module_book`: TEXT
- `ai_summary`: TEXT
- `vid_link`: VARCHAR(255)
- `duration_minutes`: INT
- `release_time`: TIMESTAMP

### `student_module_progress`
Tracks completion for streaks.
- `id`: UUID (Primary Key)
- `student_id`: UUID (Foreign Key -> `students.id`)
- `module_id`: UUID (Foreign Key -> `modules.id`)
- `watch_time_minutes`: INT (Default: 0)
- `quiz_score`: FLOAT (Default: 0.0)
- `is_completed`: BOOLEAN
- `completed_at`: TIMESTAMP

---

## 3. Examination System (3NF)

### `exams`
Stores exam definitions independently.
- `id`: UUID (Primary Key)
- `module_id`: UUID (Foreign Key -> `modules.id`, Nullable for standalone exams)
- `name`: VARCHAR(255)
- `type`: ENUM `ExamType`
- `total_marks`: FLOAT
- `created_at`: TIMESTAMP

### `student_exam_results`
Junction table tracking student performance on specific exams.
- `id`: UUID (Primary Key)
- `student_id`: UUID (Foreign Key -> `students.id`)
- `exam_id`: UUID (Foreign Key -> `exams.id`)
- `marks_obtained`: FLOAT
- `submitted_at`: TIMESTAMP

---

## 4. Feature-Specific Tables

### AI Mock Interview System
- `ai_interviews`
  - `id`: UUID (Primary Key)
  - `student_id`: UUID (Foreign Key)
  - `points_spent`: INT
  - `technical_score`: FLOAT
  - `behavioral_score`: FLOAT
  - `strengths`: JSONB
  - `weaknesses`: JSONB
  - `improvement_suggestions`: TEXT
  - `created_at`: TIMESTAMP

### Personalized Learning Path
- `learning_assessments`
  - `id`: UUID (Primary Key)
  - `student_id`: UUID (Foreign Key)
  - `topic_name`: VARCHAR(255)
  - `score_percentage`: FLOAT
  - `status`: ENUM `LearningStatus`
  - `reassessed_at`: TIMESTAMP
- `learning_recommendations`
  - `id`: UUID (Primary Key)
  - `assessment_id`: UUID (Foreign Key -> `learning_assessments.id`)
  - `recommended_content_link`: VARCHAR(255)
  - `is_completed`: BOOLEAN

### HeatMap & Consistency Tracker
- `daily_activity_logs`
  - `id`: UUID (Primary Key)
  - `student_id`: UUID (Foreign Key)
  - `date`: DATE
  - `watch_time_minutes`: INT
  - `heatmap_percentage`: FLOAT
  - `is_streak_maintained`: BOOLEAN
  - `used_freeze_point`: BOOLEAN

### AI Pair Challenge
- `pair_challenges`
  - `id`: UUID (Primary Key)
  - `date`: DATE
  - `student_1_id`: UUID (Foreign Key)
  - `student_2_id`: UUID (Foreign Key)
  - `target_module_id`: UUID (Foreign Key)
  - `status`: ENUM `PairChallengeStatus`
  - `s1_accepted`: BOOLEAN
  - `s2_accepted`: BOOLEAN
  - `s1_completed`: BOOLEAN
  - `s2_completed`: BOOLEAN

### Weekly Sprint (Phitron Royale League)
- `league_seasons`
  - `id`: UUID (Primary Key)
  - `season_number`: INT
  - `start_date`: DATE
  - `end_date`: DATE
- `league_groups`
  - `id`: UUID (Primary Key)
  - `season_id`: UUID (Foreign Key)
  - `week_number`: INT
  - `tier`: ENUM `LeagueTier`
- `league_participants`
  - `id`: UUID (Primary Key)
  - `group_id`: UUID (Foreign Key -> `league_groups.id`)
  - `student_id`: UUID (Foreign Key)
  - `tournament_points`: INT
  - `rank_in_group`: INT
  - `promotion_status`: VARCHAR(50)

### Marketing Content AI Suggestions
- `marketing_suggestions`
  - `id`: UUID (Primary Key)
  - `topic`: VARCHAR(255)
  - `ai_generated_content`: TEXT
  - `target_audience`: VARCHAR(255)

---

## 5. RAG & Semantic Search System (pgvector)

**Pre-requisite:** PostgreSQL database must have the vector extension enabled (`CREATE EXTENSION IF NOT EXISTS vector;`).

### `phitron_book`
- `id`: UUID (Primary Key)
- `module_id`: UUID (Foreign Key -> `modules.id`, Unique)
- `text`: TEXT
- `module_summary`: TEXT
- `embedding`: VECTOR(1536) - *Index using HNSW or IVFFlat for fast similarity search.*

---

## 6. Cursor Implementation Directives (Libraries & Logic)

**Required Python Libraries:**
- `SQLAlchemy (v2.0+)` (Core ORM using Async)
- `asyncpg` (Async DB Driver)
- `pgvector` (Vector support for SQLAlchemy)
- `Alembic` (Migrations - must import pgvector in env.py)
- `LangChain-Core` or `LlamaIndex` (RAG pipelines)

**Business Logic Requirements:**
1. **Streak Logic (10 PM Cron):** If module not completed in 24h, `is_streak_maintained = False` unless `streak_freeze_points > 0`. Deduct 1 freeze point to grant a 48h extension.
2. **HeatMap Logic:**
   - Sat/Sun/Tue: `watch_time == module duration` AND `module quiz_score >= 9`.
   - Mon/Wed: `watch_time == conceptual_session duration`.
   - Thu: `watch_time == exam duration + 60 mins`.
   - Fri: `watch_time >= 60 mins`.
3. **AI Pair Challenge (10 AM Match):** Match active students within `±20%` module distance. Re-match inactive acceptors by 12 PM. Deduct pair points on 3 consecutive misses.
4. **League Reset:** After 4-week season, shift `current_league` down 2 tiers (floor is IRON).