from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Any

from google import genai

from app.config import get_settings

SUMMARY_SYSTEM_PROMPT = """You are a teaching assistant for a Bangla machine-learning course.
Given a video transcript (which may be auto-generated and noisy), produce a JSON object with:
  - overview: 2-4 sentence summary of what the video teaches (in English, simple)
  - key_concepts: array of 3-7 short concept names mentioned in the video (e.g. ["linear regression", "cost function"])
  - suggested_questions: array of exactly 5 short student questions a learner might ask about THIS video's content (1 sentence each)

Rules:
- Output ONLY valid JSON, no markdown fences, no preamble.
- Questions must be answerable from the transcript itself.
- Concepts should match terminology the video actually uses.
"""

CHAT_SYSTEM_PROMPT = """You are a tutor for a Bangla machine-learning course.
The student is watching a specific video and has asked a question about it.

You will receive 3-5 short transcript excerpts from that exact video. Each excerpt
has a start time (seconds) that shows where in the video it came from.
You may also receive a "Previous conversation" block with the last few turns
from this same student on this same lesson.

Two kinds of questions, two kinds of answers:

A) CONTENT questions — the student is asking about the VIDEO itself
   (e.g. "what is backpropagation", "explain the math", "summarize this video").
   - Answer using the transcript excerpts as your primary source.
   - If the excerpts PARTIALLY cover the question, give what is there and
     mention which part of the video discusses it. It is better to say
     "the video mentions X at 2:30 but does not go into Y" than to refuse.
   - Only refuse ("The provided video excerpts do not contain information
     about that") if NONE of the excerpts are even topically related to
     the question. Do NOT guess outside information.
   - Cite a timestamp inline like "(at 4:23 in the video)".
   - Set cited_timestamp to the start_time of the excerpt you used.

B) CONVERSATIONAL / META questions — the student is talking to YOU, not the
   video (e.g. "my name is Akash", "what did I say before",
   "summarize our conversation", "repeat that", "do you remember",
   greetings, thanks, or any question whose answer lives in the
   "Previous conversation" block rather than the transcript).
   - Answer using the conversation history. Do NOT force the transcript.
   - Do NOT cite a timestamp. Set cited_timestamp to null.
   - Be natural and warm; you are a tutor who remembers the student.

Rules:
1. First decide: is this a CONTENT question or a CONVERSATIONAL question?
   If unsure, lean CONVERSATIONAL — it's better to answer a chat question
   from history than to falsely claim the video doesn't cover it.
2. For CONTENT: use only transcript excerpts. No outside knowledge.
3. For CONVERSATIONAL: use only the conversation history.
4. Be concise (2-4 sentences). Use English unless the user wrote in another language.
5. Do not repeat the question.
6. If the question is conversational but you have NO conversation history
   to draw on (empty history block), say so politely and ask the student
   to remind you.

Output a single JSON object with keys:
  - answer: your response to the student (string)
  - cited_timestamp: the single best start_time (float, seconds) of the
                     excerpt that most directly supports your answer, or
                     null if this is a conversational answer
"""


@lru_cache
def get_genai_client() -> genai.Client:
    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not configured")
    return genai.Client(api_key=settings.gemini_api_key)


def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    client = get_genai_client()
    try:
        resp = client.models.embed_content(
            model=settings.gemini_embed_model,
            contents=texts,
            config={"output_dimensionality": settings.embed_dim},
        )
        return [embedding.values for embedding in resp.embeddings]
    except Exception:
        embeddings: list[list[float]] = []
        for text in texts:
            resp = client.models.embed_content(
                model=settings.gemini_embed_model,
                contents=[text],
                config={"output_dimensionality": settings.embed_dim},
            )
            embeddings.append(resp.embeddings[0].values)
        return embeddings


def embed_query(text: str) -> list[float]:
    return embed_texts([text])[0]


def _parse_json_response(raw: str) -> dict[str, Any]:
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        cleaned = raw.strip().strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        return json.loads(cleaned)


def call_llm_json(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any] | str | None:
    settings = get_settings()
    client = get_genai_client()
    models = [
        settings.gemini_gen_model,
        "gemini-2.0-flash",
        "gemini-flash-latest",
    ]
    for model_name in models:
        for attempt in range(3):
            try:
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config={
                        "system_instruction": system_prompt,
                        "response_mime_type": "application/json",
                        "temperature": temperature,
                    },
                )
                return _parse_json_response(resp.text or "{}")
            except Exception as exc:
                err_str = str(exc)
                if (
                    "429" in err_str
                    or "RESOURCE_EXHAUSTED" in err_str
                    or "quota" in err_str.lower()
                ):
                    return "QUOTA"
                if attempt < 2:
                    time.sleep(2 ** attempt)
    return None


def call_llm_json_groq(
    system_prompt: str,
    user_prompt: str,
    temperature: float = 0.2,
) -> dict[str, Any] | None:
    settings = get_settings()
    if not settings.groq_api_key:
        return None
    try:
        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        resp = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {
                    "role": "system",
                    "content": system_prompt + "\n\nRespond ONLY with valid JSON.",
                },
                {"role": "user", "content": user_prompt},
            ],
            temperature=temperature,
            response_format={"type": "json_object"},
        )
        return json.loads(resp.choices[0].message.content)
    except Exception:
        return None


def generate_summary(transcript_text: str, title: str) -> dict[str, Any]:
    settings = get_settings()
    user_prompt = (
        f"VIDEO TITLE: {title}\n\n"
        f"TRANSCRIPT (may contain auto-caption noise):\n\n{transcript_text}\n\n"
        "Return JSON with keys: overview, key_concepts, suggested_questions."
    )
    models = [
        settings.gemini_gen_model,
        "gemini-2.0-flash",
        "gemini-flash-latest",
    ]
    last_err: Exception | None = None
    for model_name in models:
        for attempt in range(3):
            try:
                client = get_genai_client()
                resp = client.models.generate_content(
                    model=model_name,
                    contents=user_prompt,
                    config={
                        "system_instruction": SUMMARY_SYSTEM_PROMPT,
                        "response_mime_type": "application/json",
                        "temperature": 0.3,
                    },
                )
                data = _parse_json_response(resp.text or "{}")
                data.setdefault("overview", "")
                data.setdefault("key_concepts", [])
                data.setdefault("suggested_questions", [])
                return data
            except Exception as exc:
                last_err = exc
                time.sleep(2**attempt)
    raise RuntimeError(f"All summary attempts failed: {last_err!r}")
