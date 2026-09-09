# AscendEd

## AI-Powered EdTech Platform with Gamified Learning and RAG

AscendEd is an AI-powered learning management platform designed to make online learning more interactive, personalized, and engaging.

The platform combines Retrieval-Augmented Generation (RAG), AI-powered learning assistance, gamification, adaptive learning, and automated content ingestion into a single learning ecosystem.

Students can learn from course videos and books, ask questions about the learning material, track their progress, compete through leagues, participate in challenges, and practice through AI-powered mock interviews.

## Key Features

### AI-Powered Video Learning

* Automated YouTube playlist ingestion
* Video downloading using yt-dlp
* Transcript extraction with timestamps
* Automatic text chunking
* Embedding generation
* Vector storage using PostgreSQL and pgvector
* RAG-powered question answering
* Answers include exact video timestamps as citations

### Course Book RAG

* Course books can be indexed into the vector database
* Semantic search over learning materials
* Context-aware AI answers
* Source-based responses to reduce hallucination

### Gamified Learning

AscendEd uses gamification to encourage consistent learning.

* Daily learning streaks
* Streak freeze points
* Points and rewards
* Competitive league system
* Four-week league seasons
* Promotion and demotion between tiers
* GitHub-style contribution heatmap

League progression:

Iron → Bronze → Silver → Gold → Platinum → Ascendant → Immortal → Radiant

### AI Pair Challenges

Students can participate in peer learning challenges.

The system automatically matches students based on their skill level, with a configurable skill-distance threshold.

### AI Mock Interviews

The platform includes an AI-powered interview system using Google Gemini.

It evaluates:

* Technical knowledge
* Behavioral responses
* Interview performance
* Strengths
* Weaknesses
* Areas for improvement

### Adaptive Learning

AscendEd tracks student performance at the topic level.

Topics can be categorized as:

* Weak
* Improving
* Resolved

Based on these results, the system generates personalized learning recommendations.

### Examination System

Supports multiple examination formats:

* MCQ
* Coding
* Written
* Mixed

Student results are stored and used for learning analytics.

## Video RAG Architecture

The core video learning pipeline works as follows:

```text
YouTube Playlist
       |
       v
     yt-dlp
       |
       v
Video / Captions
       |
       v
Transcript with Timestamps
       |
       v
Text Chunking
       |
       v
Sentence Transformers
       |
       v
Vector Embeddings
       |
       v
PostgreSQL + pgvector
       |
       v
Student Question
       |
       v
Similarity Search
       |
       v
Top-K Relevant Chunks
       |
       v
LangChain RAG Pipeline
       |
       v
Llama 3.3 70B via Groq
       |
       v
Grounded Answer + Timestamp Citation
```

Example response:

```json
{
  "answer": "A Docker container is an isolated environment...",
  "cited_timestamp": "12:34"
}
```

## System Architecture

```text
                    +----------------------+
                    |      Frontend        |
                    |      Static JS       |
                    +----------+-----------+
                               |
                               v
                    +----------------------+
                    |       FastAPI        |
                    |      API Layer       |
                    +----------+-----------+
                               |
              +----------------+----------------+
              |                |                |
              v                v                v
        PostgreSQL          Supabase          Redis
        + pgvector             Auth             |
              |                                 |
              |                                 v
              |                              Celery
              |                                 |
              |                    +------------+------------+
              |                    |                         |
              v                    v                         v
       Learning Data        Video Ingestion           Scheduled Jobs
                            Transcription             Pair Matching
                            Embeddings                 Streak Processing
              |
              v
        RAG Retrieval
              |
              v
       Groq / Gemini LLMs
```

## Technology Stack

### Backend

* Python 3.12
* FastAPI
* Uvicorn
* SQLAlchemy 2.0
* asyncpg
* Pydantic v2
* Alembic

### AI and LLM

* LangChain
* Groq
* Llama 3.3 70B
* Google Gemini
* Sentence Transformers

### Database and Vector Search

* PostgreSQL
* pgvector
* HNSW indexing
* IVFFlat indexing
* Neon

### Authentication

* Supabase Auth
* JWT

### Background Processing

* Celery
* Celery Beat
* Redis

### Content Ingestion

* yt-dlp
* YouTube captions/transcripts
* Recursive text chunking
* Sentence Transformers

### DevOps

* Docker
* Docker Compose
* GitHub Actions
* Render

## Project Structure

```text
app/
├── main.py
├── config.py
├── database.py
├── db_sync.py
│
├── routers/
│   ├── auth.py
│   └── videos.py
│
├── models/
│
├── schemas/
│
├── services/
│
├── dependencies/
│   ├── auth.py
│   └── database.py
│
├── ai/
│   ├── gemini_client.py
│   └── rag.py
│
└── tasks/
    ├── celery_app.py
    └── background.py
```

## Database Design

The system uses a normalized PostgreSQL database with 15+ tables.

Major entities include:

```text
students
modules
student_module_progress
exams
student_exam_results
ai_interviews
learning_assessments
learning_recommendations
daily_activity_logs
pair_challenges
league_seasons
league_groups
league_participants
phitron_book
videos
transcript_chunks
video_summaries
chat_messages
```

### Vector Search

The platform uses pgvector to store and retrieve embeddings.

Different embedding dimensions are used for different content types:

```text
Course Books
1536-dimensional embeddings

Video Transcripts
768-dimensional embeddings
```

Vector indexes such as HNSW and IVFFlat are used to improve similarity search performance.

## Scalability and Production Engineering

### Async-First Backend

FastAPI, SQLAlchemy async, and asyncpg are used to avoid blocking API requests and support high levels of concurrency.

### Background Processing

Heavy workloads such as:

* YouTube downloading
* Transcript processing
* Embedding generation
* Playlist ingestion
* Scheduled learning tasks

are moved to Celery workers instead of running inside the API request lifecycle.

### Scalable Vector Search

Instead of relying on an in-memory vector database, AscendEd uses PostgreSQL with pgvector.

This provides:

* Persistent vector storage
* Database-level indexing
* Multi-instance compatibility
* Easier production management
* A migration path toward larger-scale vector infrastructure

### Stateless API

Authentication and user session state are handled through Supabase JWT authentication.

This allows multiple FastAPI instances to run behind a load balancer.

### Scheduled Automation

Celery Beat handles recurring tasks such as:

```text
10:00 AM
    Pair matching

10:00 PM
    Streak processing
```

### CI/CD

GitHub Actions is used for automated development workflows.

The pipeline can run:

* Code quality checks
* Tests
* Build processes
* Deployment workflows

## Authentication

Supabase Auth provides JWT-based authentication.

Protected API routes use reusable authentication dependencies to validate user access before processing requests.

## RAG Pipeline

The RAG system follows this general process:

```text
User Question
      |
      v
Generate Query Embedding
      |
      v
pgvector Similarity Search
      |
      v
Retrieve Top-K Chunks
      |
      v
Build Context
      |
      v
LangChain LCEL Pipeline
      |
      v
LLM
      |
      v
Grounded Response
      |
      v
Source Citation
```

The system is designed to ground responses in the actual learning material rather than relying only on the model's internal knowledge.

## Learning Experience

AscendEd combines multiple learning mechanisms into one platform:

```text
Learn
  |
  +--> Watch Videos
  |
  +--> Read Course Books
  |
  +--> Ask AI Questions
  |
  +--> Take Exams
  |
  +--> Practice Interviews
  |
  +--> Complete Pair Challenges
  |
  +--> Build Learning Streaks
  |
  +--> Improve Weak Topics
  |
  +--> Compete in Leagues
```

## Key Engineering Highlights

* Built an asynchronous FastAPI backend
* Implemented RAG over both videos and course books
* Built automated YouTube content ingestion
* Implemented timestamp-aware video retrieval
* Integrated pgvector for semantic search
* Used HNSW and IVFFlat indexes for vector retrieval
* Implemented background processing with Celery
* Used Redis as a task broker
* Implemented JWT-based authentication
* Designed a normalized PostgreSQL schema
* Built adaptive learning recommendations
* Implemented gamification and league mechanics
* Integrated Gemini for AI-powered interviews
* Containerized services using Docker
* Implemented CI/CD using GitHub Actions

## Future Improvements

Potential improvements include:

* Dedicated vector database such as Qdrant or Pinecone
* Redis-based response caching
* Advanced observability with Prometheus and Grafana
* Kubernetes deployment
* Horizontal autoscaling
* CDN-based video delivery
* Advanced learner analytics
* Personalized course generation
* Multi-language learning support
* Automated evaluation of RAG retrieval quality
* LLM evaluation and monitoring

## Project Vision

AscendEd aims to move online education beyond passive video consumption by combining AI, retrieval-based learning, personalization, and gamification.

Instead of simply watching a course, students can interact with the material, ask questions, track their weaknesses, compete with peers, practice interviews, and receive personalized recommendations.

## Tech Stack Summary

```text
Backend       : FastAPI, Python, Uvicorn
Database      : PostgreSQL, SQLAlchemy, asyncpg
Vector Search : pgvector, HNSW, IVFFlat
AI / LLM      : Groq, Llama 3.3 70B, Google Gemini
RAG           : LangChain, Sentence Transformers
Auth          : Supabase JWT
Jobs          : Celery, Celery Beat, Redis
Ingestion     : yt-dlp, YouTube transcripts
Frontend      : Static JavaScript
DevOps        : Docker, GitHub Actions
Deployment    : Render
```

## Project

AscendEd is an independently developed AI-powered EdTech platform focused on RAG-based learning, gamification, adaptive learning, and AI-assisted education.
