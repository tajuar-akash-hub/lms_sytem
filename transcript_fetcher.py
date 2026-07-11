"""Fetch YouTube transcripts as timestamped segments.

Two strategies, tried in order:
  1. youtube-transcript-api: pulls official or auto-generated captions
     directly. Free, no API key, fast — but YouTube IP-blocks quickly.
  2. yt-dlp + Groq Whisper (primary ASR) or Gemini ASR (fallback):
     downloads the audio track and transcribes it.

The function always returns TranscriptSegment objects with the same
shape, so downstream code (chunking, embedding, chat) doesn't care
which strategy succeeded.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from youtube_transcript_api import (
    IpBlocked,
    NoTranscriptFound,
    RequestBlocked,
    TranscriptsDisabled,
    VideoUnavailable,
    YouTubeTranscriptApi,
)


def _find_ffmpeg_dir() -> Optional[str]:
    """Locate a directory containing ffmpeg.exe/ffprobe.exe.

    Looks in:
      - The current PATH
      - The well-known WinGet install location for Gyan.FFmpeg
    Returns the directory, or None if not found.
    """
    if shutil.which("ffmpeg"):
        return None  # already on PATH; nothing to add
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


# Pre-resolve a PATH augmentation that subprocesses will inherit.
_EXTRA_PATH = _find_ffmpeg_dir()


def _run_ytdlp(video_id: str, tmp_dir: str) -> str:
    """Run yt-dlp to download just the audio track. Returns the file path."""
    out_template = os.path.join(tmp_dir, f"{video_id}.%(ext)s")
    cmd = [
        "python", "-m", "yt_dlp",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "5",
        "--js-runtimes", "node",
        "-o", out_template,
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
                "ffmpeg is not installed on this server. "
                "Pre-process videos on a machine with ffmpeg and re-deploy, "
                "or rely on YouTube's built-in captions."
            )
        raise RuntimeError(f"yt-dlp failed: {stderr}")

    for f in os.listdir(tmp_dir):
        if f.startswith(video_id) and f.endswith(".mp3"):
            return os.path.join(tmp_dir, f)
    raise RuntimeError("yt-dlp did not produce an mp3")


@dataclass
class TranscriptSegment:
    text: str
    start: float  # seconds
    duration: float  # seconds

    @property
    def end(self) -> float:
        return self.start + self.duration


def extract_video_id(url_or_id: str) -> str:
    """Accept a raw 11-char ID or any common YouTube URL and return the ID."""
    s = url_or_id.strip()
    # Already an ID
    if re.fullmatch(r"[A-Za-z0-9_-]{11}", s):
        return s
    # Common URL forms
    patterns = [
        r"(?:v=|/v/|youtu\.be/)([A-Za-z0-9_-]{11})",
        r"embed/([A-Za-z0-9_-]{11})",
    ]
    for pat in patterns:
        m = re.search(pat, s)
        if m:
            return m.group(1)
    raise ValueError(f"Could not extract YouTube video ID from: {url_or_id!r}")


def fetch_transcript(
    url_or_id: str,
    preferred_languages: Optional[List[str]] = None,
    use_asr_fallback: bool = True,
) -> List[TranscriptSegment]:
    """Fetch the transcript for a video.

    Strategy:
      1. Try youtube-transcript-api for Bangla/English captions.
      2. If that fails (IP ban, no captions, etc.) AND use_asr_fallback
         is True, download the audio with yt-dlp and transcribe it via
         Groq Whisper (primary) or Gemini (fallback).
    """
    if preferred_languages is None:
        preferred_languages = ["bn", "en"]

    video_id = extract_video_id(url_or_id)

    # ---- Strategy 1: YouTube captions ----
    try:
        segs = _fetch_via_youtube_api(video_id, preferred_languages)
        if segs:
            return segs
    except (IpBlocked, RequestBlocked):
        if use_asr_fallback:
            try:
                return _fetch_via_groq_whisper(video_id)
            except Exception as e:
                print(f"      (Groq ASR failed: {e!r}, falling back to Gemini)")
                return _fetch_via_gemini_asr(video_id)
        raise
    except (VideoUnavailable, TranscriptsDisabled):
        raise RuntimeError(f"Video unavailable or captions disabled: {video_id}")
    except NoTranscriptFound:
        if use_asr_fallback:
            try:
                return _fetch_via_groq_whisper(video_id)
            except Exception as e:
                print(f"      (Groq ASR failed: {e!r}, falling back to Gemini)")
                return _fetch_via_gemini_asr(video_id)
        raise RuntimeError(f"No transcript available for {video_id}")

    if use_asr_fallback:
        try:
            return _fetch_via_groq_whisper(video_id)
        except Exception as e:
            print(f"      (Groq ASR failed: {e!r}, falling back to Gemini)")
            return _fetch_via_gemini_asr(video_id)
    return []


def _fetch_via_youtube_api(
    video_id: str, preferred_languages: List[str]
) -> List[TranscriptSegment]:
    api = YouTubeTranscriptApi()
    transcript_list = api.list(video_id)

    for lang in preferred_languages:
        try:
            t = transcript_list.find_transcript([lang])
            fetched = t.fetch()
            return [
                TranscriptSegment(text=s.text, start=s.start, duration=s.duration)
                for s in fetched
            ]
        except NoTranscriptFound:
            continue

    # Fall back: take any transcript and translate to Bangla
    any_t = next(iter(transcript_list))
    translated = any_t.translate("bn")
    fetched = translated.fetch()
    return [
        TranscriptSegment(text=s.text, start=s.start, duration=s.duration)
        for s in fetched
    ]


def _fetch_via_groq_whisper(video_id: str) -> List[TranscriptSegment]:
    """Download audio with yt-dlp, then transcribe via Groq's hosted Whisper.

    Groq's whisper-large-v3-turbo is very fast and supports timestamped
    segments in the response. This is our preferred ASR fallback because:
      - No local compute needed
      - Returns native timestamps (no need to ask an LLM to invent them)
      - Excellent Bangla support
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY not set — cannot use Groq Whisper")

    print(f"      (Groq Whisper) downloading audio for {video_id}...")
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _run_ytdlp(video_id, tmp)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"      (Groq Whisper) audio {size_mb:.1f} MB, transcribing...")

        # Groq supports flac, mp3, mp4, m4a, ogg, wav, webm
        from groq import Groq
        client = Groq(api_key=api_key)

        with open(audio_path, "rb") as f:
            transcription = client.audio.transcriptions.create(
                file=(os.path.basename(audio_path), f.read()),
                model="whisper-large-v3-turbo",
                language="bn",  # Bangla; Whisper auto-detects too but this is explicit
                response_format="verbose_json",
                timestamp_granularities=["segment"],
            )

        # The verbose_json response has 'segments' with start/end/text
        segments: List[TranscriptSegment] = []
        segs = getattr(transcription, "segments", None) or []
        for s in segs:
            try:
                start = float(s.get("start", 0))
                end = float(s.get("end", 0))
                text = str(s.get("text", "")).strip()
            except (TypeError, ValueError):
                continue
            if not text:
                continue
            segments.append(
                TranscriptSegment(
                    text=text, start=start, duration=max(0.0, end - start)
                )
            )
        if not segments:
            # Fallback: use the flat text + total duration
            text = (getattr(transcription, "text", "") or "").strip()
            if not text:
                raise RuntimeError("Groq Whisper returned no segments and no text")
            segments.append(TranscriptSegment(text=text, start=0.0, duration=0.0))
        return segments


def _fetch_via_gemini_asr(video_id: str) -> List[TranscriptSegment]:
    """Download audio with yt-dlp, then ask Gemini to transcribe it
    in timestamped segments. Works even when YouTube blocks captions.
    """
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).parent / ".env")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY not set — cannot use ASR fallback")

    from google import genai

    print(f"      (ASR fallback) downloading audio for {video_id}...")
    with tempfile.TemporaryDirectory() as tmp:
        audio_path = _run_ytdlp(video_id, tmp)
        size_mb = os.path.getsize(audio_path) / (1024 * 1024)
        print(f"      (ASR fallback) audio {size_mb:.1f} MB, sending to Gemini...")

        client = genai.Client(api_key=api_key)

        prompt = (
            "Listen to this audio carefully. The speaker is teaching "
            "machine learning in Bangla (Bengali). "
            "Transcribe the speech verbatim in its original language. "
            "Return the output as a JSON array of segments, each with: "
            '{"start": <seconds>, "end": <seconds>, "text": "<verbatim transcript>"}. '
            "Cover the entire audio from start to finish with consecutive, "
            "non-overlapping segments of roughly 5-15 seconds each. "
            "Output ONLY the JSON array, no markdown fences, no preamble."
        )

        # Decide upload path: inline if <=18 MB, else Files API.
        if size_mb <= 18:
            print(f"      (ASR fallback) using inline audio (small file)...")
            with open(audio_path, "rb") as f:
                audio_bytes = f.read()
            audio_part = {"inline_data": {"mime_type": "audio/mp3", "data": audio_bytes}}
            contents = [prompt, audio_part]
        else:
            print(f"      (ASR fallback) uploading via Files API (large file)...")
            uploaded = client.files.upload(file=audio_path)
            while uploaded.state and uploaded.state.name == "PROCESSING":
                time.sleep(2)
                uploaded = client.files.get(name=uploaded.name)
            if uploaded.state and uploaded.state.name == "FAILED":
                raise RuntimeError("Gemini file upload failed")
            contents = [prompt, uploaded]
            try:
                client.files.delete(name=uploaded.name)
            except Exception:
                pass

        resp = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=contents,
            config={"response_mime_type": "application/json", "temperature": 0.1},
        )
        raw = resp.text or "[]"

        # Parse the JSON array
        import json
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            cleaned = raw.strip().strip("`")
            if cleaned.startswith("json"):
                cleaned = cleaned[4:]
            data = json.loads(cleaned)

        # Clean up the uploaded file
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
                TranscriptSegment(text=text, start=start, duration=max(0.0, end - start))
            )
        if not segments:
            raise RuntimeError("Gemini ASR returned no usable segments")
        return segments


def merge_short_segments(
    segments: List[TranscriptSegment],
    max_gap_seconds: float = 0.5,
) -> List[TranscriptSegment]:
    """Merge consecutive segments that are very close in time into one.

    youtube-transcript-api sometimes returns micro-segments (e.g. one
    per word). For readability and for chunking, we glue together any
    consecutive segments whose end and start are within max_gap_seconds.
    """
    if not segments:
        return []

    merged: List[TranscriptSegment] = [segments[0]]
    for seg in segments[1:]:
        prev = merged[-1]
        if seg.start - prev.end <= max_gap_seconds:
            merged[-1] = TranscriptSegment(
                text=(prev.text + " " + seg.text).strip(),
                start=prev.start,
                duration=(seg.start + seg.duration) - prev.start,
            )
        else:
            merged.append(seg)
    return merged


def chunk_by_time(
    segments: List[TranscriptSegment],
    chunk_seconds: float = 60.0,
    max_gap_seconds: float = 15.0,
) -> List[dict]:
    """Group segments into chunks of roughly `chunk_seconds` length.

    Each output dict has: text, start_time, end_time, chunk_index.

    Closing rules:
      - Close the current chunk when its total span exceeds chunk_seconds
        AND we have at least one segment in it.
      - Also close if the gap between the previous segment's end and the
        next segment's start is larger than max_gap_seconds (handles long
        silences in audio so we don't make giant chunks).
    """
    chunks: List[dict] = []
    current_texts: List[str] = []
    current_start: Optional[float] = None
    current_end: float = 0.0

    for seg in segments:
        if current_start is None:
            current_start = seg.start
            current_texts.append(seg.text)
            current_end = seg.end
            continue

        span = seg.end - current_start
        gap = seg.start - current_end

        # Decide whether to close the current chunk
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
            current_texts = [seg.text]
            current_start = seg.start
            current_end = seg.end
        else:
            current_texts.append(seg.text)
            current_end = seg.end

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


# ---------------------------------------------------------------------------
# CLI for ad-hoc testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import json
    import sys

    if len(sys.argv) < 2:
        print("Usage: python transcript_fetcher.py <youtube_url_or_id>")
        sys.exit(1)

    vid = sys.argv[1]
    print(f"Fetching transcript for: {vid}")
    raw = fetch_transcript(vid)
    print(f"Got {len(raw)} raw segments")

    merged = merge_short_segments(raw)
    print(f"After merging short gaps: {len(merged)} segments")

    chunks = chunk_by_time(merged, chunk_seconds=60.0)
    print(f"After time chunking (60s): {len(chunks)} chunks")

    print("\nFirst 3 chunks preview:")
    for c in chunks[:3]:
        preview = c["text"][:120] + ("..." if len(c["text"]) > 120 else "")
        print(f"  [{c['start_time']:.1f}s - {c['end_time']:.1f}s] {preview}")

    print("\nFull chunks as JSON:")
    print(json.dumps(chunks, ensure_ascii=False, indent=2))