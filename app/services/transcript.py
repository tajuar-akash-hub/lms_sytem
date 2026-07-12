"""Fetch YouTube transcripts as timestamped segments.

Requires ffmpeg on PATH for audio extraction (e.g. brew install ffmpeg on macOS).
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional


def _find_ffmpeg_dir() -> Optional[str]:
    if shutil.which("ffmpeg"):
        return None
    local = os.environ.get("LOCALAPPDATA")
    if local:
        winget_root = Path(local) / "Microsoft" / "WinGet" / "Packages"
        if winget_root.exists():
            for pkg in winget_root.glob("Gyan.FFmpeg*"):
                for sub in pkg.iterdir():
                    bin_dir = sub / "bin"
                    if (bin_dir / "ffmpeg.exe").exists():
                        return str(bin_dir)
    return None


_EXTRA_PATH = _find_ffmpeg_dir()


def _run_ytdlp(video_id: str, tmp_dir: str) -> str:
    out_template = os.path.join(tmp_dir, f"{video_id}.%(ext)s")
    cmd = [
        sys.executable,
        "-m",
        "yt_dlp",
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        "5",
        "--js-runtimes",
        "node",
        "-o",
        out_template,
        f"https://www.youtube.com/watch?v={video_id}",
    ]
    env = os.environ.copy()
    if _EXTRA_PATH:
        env["PATH"] = _EXTRA_PATH + os.pathsep + env.get("PATH", "")
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)
    if result.returncode != 0:
        stderr = result.stderr[-400:]
        if "ffmpeg" in stderr.lower() or "ffprobe" in stderr.lower():
            raise RuntimeError(
                "ffmpeg is not installed. Install it with: brew install ffmpeg"
            )
        raise RuntimeError(f"yt-dlp failed: {stderr}")

    for filename in os.listdir(tmp_dir):
        if filename.startswith(video_id) and filename.endswith(".mp3"):
            return os.path.join(tmp_dir, filename)
    raise RuntimeError("yt-dlp did not produce an mp3")


@dataclass
class TranscriptSegment:
    text: str
    start: float
    duration: float

    @property
    def end(self) -> float:
        return self.start + self.duration


def extract_video_id(url_or_id: str) -> str:
    value = url_or_id.strip()
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", value):
        return value
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]
    for pattern in patterns:
        match = re.search(pattern, value)
        if match:
            return match.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id!r}")


def fetch_transcript(
    url_or_id: str,
    preferred_languages: Optional[List[str]] = None,
) -> List[TranscriptSegment]:
    video_id = extract_video_id(url_or_id)
    lang_map = {
        "bn": "bn",
        "ben": "bn",
        "bengali": "bn",
        "bangla": "bn",
        "en": "en",
        "eng": "en",
        "english": "en",
    }
    hint = None
    for lang in preferred_languages or []:
        code = lang_map.get(lang.lower())
        if code:
            hint = code
            break

    try:
        return _fetch_via_groq_whisper(video_id, language_hint=hint)
    except Exception as exc:
        print(f"      (Groq ASR failed: {exc!r}, falling back to Gemini)")
        return _fetch_via_gemini_asr(video_id, language_hint=hint)


def _fetch_via_groq_whisper(
    video_id: str,
    language_hint: Optional[str] = None,
) -> List[TranscriptSegment]:
    from app.config import get_settings

    settings = get_settings()
    if not settings.groq_api_key:
        raise RuntimeError("GROQ_API_KEY not set — cannot use Groq Whisper")

    print(f"      (Groq Whisper) downloading audio for {video_id}...")
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _run_ytdlp(video_id, tmp)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"      (Groq Whisper) audio {size_mb:.1f} MB, transcribing...")

        from groq import Groq

        client = Groq(api_key=settings.groq_api_key)
        with open(audio_path, "rb") as audio_file:
            kwargs = dict(
                file=(os.path.basename(audio_path), audio_file.read()),
                model="whisper-large-v3-turbo",
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )
            if language_hint:
                kwargs["language"] = language_hint
            transcription = client.audio.transcriptions.create(**kwargs)

        segments: List[TranscriptSegment] = []
        raw_segments = getattr(transcription, "segments", None) or []
        for segment in raw_segments:
            try:
                start = float(segment.get("start", 0))
                end = float(segment.get("end", 0))
                text = str(segment.get("text", "")).strip()
            except (TypeError, ValueError):
                continue
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    text=text,
                    start=start,
                    duration=max(0.0, end - start),
                )
            )
        if not segments:
            text = (getattr(transcription, "text", "") or "").strip()
            if not text:
                raise RuntimeError("Groq Whisper returned no segments and no text")
            segments.append(TranscriptSegment(text=text, start=0.0, duration=0.0))
        return segments


def _fetch_via_gemini_asr(
    video_id: str,
    language_hint: Optional[str] = None,
) -> List[TranscriptSegment]:
    del language_hint
    from google import genai

    from app.ai.gemini_client import get_genai_client
    from app.config import get_settings

    settings = get_settings()
    if not settings.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY not set — cannot use ASR fallback")

    print(f"      (ASR fallback) downloading audio for {video_id}...")
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _run_ytdlp(video_id, tmp)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"      (ASR fallback) audio {size_mb:.1f} MB, sending to Gemini...")

        client = get_genai_client()
        prompt = (
            "Listen to this audio carefully. The speaker is teaching "
            "machine learning (the lecture may be in English, Bangla, or "
            "code-switched between both). "
            "Transcribe the speech verbatim in its original language. "
            "Return the output as a JSON array of segments, each with: "
            '{"start": <seconds>, "end": <seconds>, "text": "<verbatim transcript>"}. '
            "Cover the entire audio from start to finish with consecutive, "
            "non-overlapping segments of roughly 5-15 seconds each. "
            "Output ONLY the JSON array, no markdown fences, no preamble."
        )

        uploaded = None
        if size_mb <= 18:
            with open(audio_path, "rb") as audio_file:
                audio_bytes = audio_file.read()
            contents = [
                prompt,
                {"inline_data": {"mime_type": "audio/mp3", "data": audio_bytes}},
            ]
        else:
            uploaded = client.files.upload(file=audio_path)
            while uploaded.state and uploaded.state.name == "PROCESSING":
                time.sleep(2)
                uploaded = client.files.get(name=uploaded.name)
            if uploaded.state and uploaded.state.name == "FAILED":
                raise RuntimeError("Gemini file upload failed")
            contents = [prompt, uploaded]

        resp = client.models.generate_content(
            model=settings.gemini_gen_model,
            contents=contents,
            config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        raw = resp.text or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            data = json.loads(cleaned)

        if uploaded is not None:
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

        segments: List[TranscriptSegment] = []
        for item in data:
            try:
                start = float(item["start"])
                end = float(item["end"])
                text = str(item["text"]).strip()
            except (KeyError, TypeError, ValueError):
                continue
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    text=text,
                    start=start,
                    duration=max(0.0, end - start),
                )
            )
        if not segments:
            raise RuntimeError("Gemini ASR returned no usable segments")
        return segments


def merge_short_segments(
    segments: List[TranscriptSegment],
    max_gap_seconds: float = 0.5,
) -> List[TranscriptSegment]:
    if not segments:
        return []

    merged: List[TranscriptSegment] = [segments[0]]
    for segment in segments[1:]:
        previous = merged[-1]
        if segment.start - previous.end <= max_gap_seconds:
            merged[-1] = TranscriptSegment(
                text=(previous.text + " " + segment.text).strip(),
                start=previous.start,
                duration=(segment.start + segment.duration) - previous.start,
            )
        else:
            merged.append(segment)
    return merged


def chunk_by_time(
    segments: List[TranscriptSegment],
    chunk_seconds: float = 60.0,
    max_gap_seconds: float = 15.0,
) -> List[dict]:
    chunks: List[dict] = []
    current_texts: List[str] = []
    current_start: Optional[float] = None
    current_end: float = 0.0

    for segment in segments:
        if current_start is None:
            current_start = segment.start
            current_texts.append(segment.text)
            current_end = segment.end
            continue

        span = segment.end - current_start
        gap = segment.start - current_end
        too_long = span > chunk_seconds and len(current_texts) >= 1
        big_gap = gap > max_gap_seconds and len(current_texts) >= 1
        if too_long or big_gap:
            chunks.append(
                {
                    "text": " ".join(current_texts).strip(),
                    "start_time": current_start,
                    "end_time": current_end,
                    "chunk_index": len(chunks),
                }
            )
            current_texts = [segment.text]
            current_start = segment.start
            current_end = segment.end
        else:
            current_texts.append(segment.text)
            current_end = segment.end

    if current_texts and current_start is not None:
        chunks.append(
            {
                "text": " ".join(current_texts).strip(),
                "start_time": current_start,
                "end_time": current_end,
                "chunk_index": len(chunks),
            }
        )

    return chunks
