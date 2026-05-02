"""
video_assembler.py — ffmpeg Video Assembler (v2)
Combines contextual stock footage + voiceover audio into a final MP4.
Subtitles are generated via local ffmpeg Whisper and saved as a separate
SRT file for upload to YouTube — NOT burned into the video.

Pipeline:
  1. Load draft JSON (segments with per-segment footage keywords)
  2. Get audio duration via ffprobe
  3. Run local Whisper on the audio to generate accurate SRT
  4. For each script segment, fetch footage matching its keyword
  5. Build footage sequence aligned to segment timing
  6. Assemble with ffmpeg: footage + audio (no burned subtitles)
  7. Save MP4 to outputs/drafts/ and SRT to assets/audio/

Usage:
    python scripts/assembler/video_assembler.py --latest
    python scripts/assembler/video_assembler.py --draft outputs/drafts/your_draft.json
"""

import argparse
import json
import os
import re
import subprocess
import sys
import time
import tempfile
import requests
from pathlib import Path
from typing import Optional

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    PEXELS_API_KEY,
    PIXABAY_API_KEY,
    AUDIO_DIR,
    FOOTAGE_DIR,
    DRAFTS_DIR,
    VIDEO_FPS,
    VIDEO_BITRATE,
    AUDIO_BITRATE,
    FOOTAGE_CLIP_DURATION,
    FOOTAGE_SOURCE,
    KLING_SEGMENTS,
    BACKGROUND_MUSIC_FILE,
    BACKGROUND_MUSIC_VOLUME,
    VIDEO_OUTRO_SECONDS,
    VIDEO_OUTRO_FADE_SECONDS,
    DALLE_FALLBACK_FOR_STOCK,
)
from scripts.assembler.clip_reviewer import pick_best_clip
from scripts.assembler import wikimedia_fetcher, motion_graphic_renderer, dalle_fetcher, archive_fetcher
from scripts.assembler.vision_qc import run_vision_qc

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
PEXELS_HEADERS = {"Authorization": PEXELS_API_KEY}
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"


# ── Draft helpers ──────────────────────────────────────────────────────────────

def get_latest_draft() -> Path:
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No drafts found in {DRAFTS_DIR}")
    return drafts[0]


def load_draft(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_draft(path: Path, key: str, value):
    data = load_draft(path)
    data[key] = value
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Audio helpers ──────────────────────────────────────────────────────────────

def get_audio_duration(audio_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(audio_path)],
        capture_output=True, text=True
    )
    return float(result.stdout.strip())


# ── Whisper (local via ffmpeg) ─────────────────────────────────────────────────

def generate_srt_local_whisper(audio_path: Path, srt_path: Path) -> bool:
    """
    Use ffmpeg's built-in Whisper to transcribe audio to SRT.
    ffmpeg must be compiled with --enable-whisper (confirmed present).
    Falls back gracefully if model download fails.
    Skips generation if SRT already exists (preserves manual corrections).
    """
    if srt_path.exists() and srt_path.stat().st_size > 100:
        print(f"  SRT already exists — skipping regeneration: {srt_path.name}")
        return True
    print("  Generating subtitles via local Whisper (ffmpeg)...")

    # ffmpeg whisper outputs subtitle stream — we use the ASS/SRT subtitle filter
    # The cleanest approach: use ffmpeg -i audio -f srt output.srt
    cmd = [
        "ffmpeg", "-y",
        "-i", str(audio_path),
        "-f", "srt",
        str(srt_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)

    if srt_path.exists() and srt_path.stat().st_size > 100:
        print(f"  SRT generated: {srt_path.name}")
        return True

    # Fallback: use openai-whisper Python package if installed
    print("  ffmpeg SRT export not available — trying whisper Python package...")
    try:
        import whisper
        model = whisper.load_model("base")
        result = model.transcribe(str(audio_path))
        srt_content = whisper_result_to_srt(result)
        srt_path.write_text(srt_content, encoding="utf-8")
        print(f"  SRT generated via whisper package: {srt_path.name}")
        return True
    except ImportError:
        print("  whisper package not installed. Run: pip install openai-whisper")
    except Exception as e:
        print(f"  Whisper package failed: {e}")

    # Final fallback: basic timed SRT
    print("  Using basic timed SRT fallback...")
    return False


def whisper_result_to_srt(result: dict) -> str:
    lines = []
    for i, seg in enumerate(result["segments"], 1):
        start = format_srt_time(seg["start"])
        end = format_srt_time(seg["end"])
        text = seg["text"].strip()
        lines.append(f"{i}\n{start} --> {end}\n{text}\n")
    return "\n".join(lines)


def generate_basic_srt(script: str, audio_duration: float) -> str:
    """Fallback: evenly space subtitle chunks across audio duration."""
    words = script.split()
    chunk_size = 8
    chunks = [" ".join(words[i:i+chunk_size]) for i in range(0, len(words), chunk_size)]
    chunk_dur = audio_duration / len(chunks)
    lines = []
    for i, chunk in enumerate(chunks, 1):
        start = format_srt_time(i * chunk_dur - chunk_dur)
        end = format_srt_time(i * chunk_dur)
        lines.append(f"{i}\n{start} --> {end}\n{chunk}\n")
    return "\n".join(lines)


def format_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


# ── Footage helpers ────────────────────────────────────────────────────────────

_footage_cache: dict = {}   # cache_key → list of local paths

# Mood → search modifier (applied to both Pexels and Pixabay)
MOOD_MODIFIERS = {
    "dramatic":   "dramatic cinematic dark",
    "ominous":    "dark ominous storm conflict",
    "tense":      "tense war conflict protest",
    "analytical": "finance data technology office",
    "calm":       "peaceful calm nature minimal",
    "hopeful":    "sunrise hope light dawn",
}

# Simplified fallback keywords when specific query returns nothing
KEYWORD_SIMPLIFIER = {
    # Strip overly specific terms to broader searchable ones
    "archival footage": "",
    "close up": "",
    "aerial drone footage": "aerial",
    "overhead shot": "",
    "slow motion": "",
    "composite": "",
    "satellite map view": "map",
    "historical painting": "historical",
    "infographic": "map",
}


def simplify_keyword(keyword: str) -> str:
    """Strip terms that Pexels/Pixabay struggle with, leaving core searchable terms."""
    result = keyword.lower()
    for phrase, replacement in KEYWORD_SIMPLIFIER.items():
        result = result.replace(phrase, replacement)
    # Remove year references (Pexels has no 1971 footage)
    result = re.sub(r"\b(19|20)\d{2}\b", "", result)
    # Collapse whitespace
    result = " ".join(result.split())
    return result[:60]


def build_search_query(keyword: str, mood: str) -> str:
    modifier = MOOD_MODIFIERS.get(mood, "dramatic cinematic")
    return f"{keyword} {modifier}"


def download_file(url: str, dest: Path) -> bool:
    try:
        r = requests.get(url, stream=True, timeout=60)
        r.raise_for_status()
        dest.parent.mkdir(parents=True, exist_ok=True)
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    Download failed: {e}")
        return False


def search_pexels(query: str, footage_dir: Path, per_page: int = 5) -> list:
    """Search Pexels, download clips, return local paths."""
    params = {
        "query": query, "per_page": per_page,
        "orientation": "landscape", "size": "large",
        "min_duration": 4, "max_duration": 25,
    }
    videos = []
    for attempt in range(3):
        try:
            resp = requests.get(PEXELS_VIDEO_URL, headers=PEXELS_HEADERS,
                                params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("videos", [])
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)

    paths = []
    for video in videos[:per_page]:
        vid_id = video.get("id")
        files = video.get("video_files", [])
        hd = [f for f in files if f.get("width") == 1920]
        best = hd[0] if hd else (
            sorted(files, key=lambda f: f.get("width", 0), reverse=True)[0] if files else None
        )
        if not best:
            continue
        slug = re.sub(r"[^\w]", "_", query)[:35]
        dest = footage_dir / f"px_{slug}_{vid_id}.mp4"
        if dest.exists() and dest.stat().st_size > 0:
            paths.append(dest)
            continue
        if download_file(best["link"], dest):
            paths.append(dest)
            time.sleep(0.3)

    time.sleep(0.4)
    return paths


def search_pixabay(query: str, footage_dir: Path, per_page: int = 5) -> list:
    """Search Pixabay videos, download clips, return local paths."""
    if not PIXABAY_API_KEY:
        return []
    params = {
        "key": PIXABAY_API_KEY, "q": query,
        "video_type": "film", "per_page": per_page,
        "min_width": 1280, "safesearch": "true",
    }
    videos = []
    for attempt in range(3):
        try:
            resp = requests.get(PIXABAY_VIDEO_URL, params=params, timeout=15)
            resp.raise_for_status()
            videos = resp.json().get("hits", [])
            break
        except Exception as e:
            if attempt < 2:
                time.sleep(2 ** attempt)

    paths = []
    for video in videos[:per_page]:
        vid_id = video.get("id")
        # Pixabay offers large/medium/small/tiny sizes
        video_files = video.get("videos", {})
        best_url = (
            video_files.get("large", {}).get("url") or
            video_files.get("medium", {}).get("url") or
            video_files.get("small", {}).get("url")
        )
        if not best_url:
            continue
        slug = re.sub(r"[^\w]", "_", query)[:35]
        dest = footage_dir / f"pb_{slug}_{vid_id}.mp4"
        if dest.exists() and dest.stat().st_size > 0:
            paths.append(dest)
            continue
        if download_file(best_url, dest):
            paths.append(dest)
            time.sleep(0.3)

    time.sleep(0.4)
    return paths


def fetch_clips_for_segment(keyword: str, mood: str, footage_dir: Path,
                             needed: int = 3) -> list:
    """
    Fetch clips for a segment using configured FOOTAGE_SOURCE.
    Tries multiple query variants to avoid fallback dominance.
    Returns list of unique local Paths.
    """
    query_full = build_search_query(keyword, mood)
    query_simple = build_search_query(simplify_keyword(keyword), mood)
    query_bare = simplify_keyword(keyword)

    cache_key = query_full.lower().strip()
    if cache_key in _footage_cache:
        return _footage_cache[cache_key]

    paths = []
    seen = set()

    def add_paths(new_paths):
        for p in new_paths:
            if str(p) not in seen:
                seen.add(str(p))
                paths.append(p)

    source = FOOTAGE_SOURCE.lower()

    # ── Pexels ──
    if "pexels" in source:
        add_paths(search_pexels(query_full, footage_dir, per_page=5))
        if len(paths) < needed:
            add_paths(search_pexels(query_simple, footage_dir, per_page=5))
        if len(paths) < needed:
            add_paths(search_pexels(query_bare, footage_dir, per_page=3))

    # ── Pixabay fallback ──
    if "pixabay" in source and len(paths) < needed:
        add_paths(search_pixabay(query_full, footage_dir, per_page=5))
        if len(paths) < needed:
            add_paths(search_pixabay(query_simple, footage_dir, per_page=5))
        if len(paths) < needed:
            add_paths(search_pixabay(query_bare, footage_dir, per_page=3))

    # ── Last resort: generic dark b-roll ──
    if not paths:
        print(f"    No results — using generic fallback for '{keyword}'")
        generic_queries = ["dark storm clouds", "city night timelapse", "world map spinning"]
        for gq in generic_queries:
            if "pexels" in source:
                add_paths(search_pexels(gq, footage_dir, per_page=2))
            if "pixabay" in source:
                add_paths(search_pixabay(gq, footage_dir, per_page=2))
            if paths:
                break

    _footage_cache[cache_key] = paths
    return paths


# ── Scorecard helpers ──────────────────────────────────────────────────────────

def _extract_prediction_from_segment(text: str) -> dict | None:
    """Extract {num, text, status} from a single prediction segment text."""
    ORDINAL_MAP = {w: str(i + 1) for i, w in enumerate(
        ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
    )}
    m = re.match(
        r'^Prediction\s+(?:#?(\d+)|([a-z]+))\s*[—:\.\-]?\s*(.*)',
        text.strip(), re.IGNORECASE
    )
    if not m:
        return None
    num = m.group(1) or ORDINAL_MAP.get((m.group(2) or "").lower(), "?")
    text_part = m.group(3).strip()
    status = "PENDING"
    for s in ("CONFIRMED", "ACTIVE", "PENDING"):
        if s in text.upper():
            status = s
            break
    # Keep only up to the first colon/dash separator for display
    short = re.split(r'[:\-—]', text_part)[0].strip()
    return {"num": num, "text": short or text_part[:65], "status": status}


# ── Segment timing ─────────────────────────────────────────────────────────────

def estimate_segment_durations(segments: list, total_duration: float) -> list:
    """
    Estimate how long each segment plays based on its word count
    relative to total word count. Returns list of durations in seconds.
    """
    word_counts = [len(s["text"].split()) for s in segments]
    total_words = sum(word_counts)
    durations = [(wc / total_words) * total_duration for wc in word_counts]
    return durations


# ── ffmpeg assembly ────────────────────────────────────────────────────────────

def get_clip_duration(clip_path: Path) -> float:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
        capture_output=True, text=True
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return 5.0


def preprocess_clips(entries: list, tmp_dir: Path) -> list:
    """
    Trim each clip to its assigned duration. No looping — clips are already
    chained at the entry level to avoid repeats.
    """
    processed = []
    for i, e in enumerate(entries):
        clip_path = Path(e["path"])
        target_dur = e["duration"]
        out_path = tmp_dir / f"seg_{i:03d}.mp4"

        cmd = [
            "ffmpeg", "-y",
            "-i", str(clip_path),
            "-t", str(target_dur),
            "-c:v", "libx264", "-preset", "ultrafast",
            "-an",
            "-r", str(VIDEO_FPS),
            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,"
                   "pad=1920:1080:(ow-iw)/2:(oh-ih)/2",  # letterbox to 1080p
            "-pix_fmt", "yuv420p",
            str(out_path),
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode == 0 and out_path.exists() and out_path.stat().st_size > 0:
            processed.append({"path": out_path, "duration": target_dur})
        else:
            processed.append({"path": clip_path, "duration": target_dur})

    return processed


def build_concat_file(entries: list, tmp_dir: Path) -> Path:
    """entries: list of {"path": Path, "duration": float}"""
    concat_path = tmp_dir / "concat.txt"
    lines = []
    for e in entries:
        p = str(e["path"]).replace("\\", "/")
        lines.append(f"file '{p}'\n")
    concat_path.write_text("".join(lines), encoding="utf-8")
    return concat_path



def build_footage_entries(segments: list, durations: list, footage_dir: Path,
                           stem: str = "video", dalle_clips_log: list = None) -> list:
    """
    For each segment, build a chain of UNIQUE clips that fills the segment duration.
    Routes to the appropriate source based on segment["source_type"]:
      - motion_graphic: rendered locally via motion_graphic_renderer (no clip_reviewer)
      - wikimedia: Wikimedia Commons image + Ken Burns
      - dalle: DALL-E 3 generated image + Ken Burns
      - archive: scaffold fallback to stock
      - stock (default): Pexels/Pixabay

    Returns list of {"path": Path, "duration": float} — one entry per clip sub-segment.
    """
    entries = []
    last_used_path = None
    fallback_clips = []
    total_review_tokens = 0
    if dalle_clips_log is None:
        dalle_clips_log = []

    # Pre-extract prediction data for cumulative scorecard rendering
    all_predictions = []
    for seg in segments:
        if seg.get("source_type") == "motion_graphic":
            pred = _extract_prediction_from_segment(seg.get("text", ""))
            if pred:
                all_predictions.append(pred)
    scorecard_render_count = [0]  # mutable counter shared across iterations

    for i, (seg, total_dur) in enumerate(zip(segments, durations)):
        keyword = seg.get("footage_keyword", "city skyline dark dramatic")
        mood = seg.get("footage_mood", "dramatic")
        segment_text = seg.get("text", "")
        source_type = seg.get("source_type", "stock")
        search_query = seg.get("search_query", keyword)

        print(f"  [{i+1}/{len(segments)}] [{source_type.upper()}] '{search_query[:50]}' ({total_dur:.1f}s)")

        def dalle_clip(prompt: str) -> list:
            """Helper: fetch one DALL-E clip and log it. Returns list with Path or []."""
            c = dalle_fetcher.fetch_dalle_clip(prompt, stem=stem, duration=total_dur)
            if c:
                dalle_clips_log.append({"segment": i + 1, "prompt": prompt, "path": str(c)})
                return [c]
            return []

        # ── motion_graphic: deterministic render, skip clip_reviewer ──────────
        if source_type == "motion_graphic":
            mg_dir = footage_dir / "motion_graphics"
            mg_dir.mkdir(parents=True, exist_ok=True)
            slug = re.sub(r"[^\w]", "_", segment_text[:40])
            clip_path = mg_dir / f"mg_{i:03d}_{slug}.mp4"

            is_scorecard = motion_graphic_renderer.is_scorecard_segment(segment_text)

            if is_scorecard and all_predictions:
                # Always re-render cumulative scorecards (never use cache)
                cur_idx = scorecard_render_count[0]
                scorecard_render_count[0] += 1
                print(f"  [MotionGraphic] Rendering cumulative scorecard ({cur_idx + 1}/{len(all_predictions)}) -> {clip_path.name}")
                result = motion_graphic_renderer.render_cumulative_scorecard(
                    all_predictions, cur_idx, clip_path, duration=total_dur
                )
            else:
                # Non-scorecard: use cache if available
                if clip_path.exists() and clip_path.stat().st_size > 0:
                    print(f"  [MotionGraphic] Using cached clip -> {clip_path.name}")
                    entries.append({"path": clip_path, "duration": total_dur})
                    continue
                result = motion_graphic_renderer.render_motion_graphic(
                    segment_text, clip_path, duration=total_dur
                )

            if result and result.exists():
                entries.append({"path": result, "duration": total_dur})
            else:
                print(f"    [MotionGraphic] Render failed — trying DALL-E")
                fallback = dalle_clip(keyword)
                if fallback:
                    entries.append({"path": fallback[0], "duration": total_dur})
            continue  # skip clip_reviewer for motion graphics

        # ── wikimedia ─────────────────────────────────────────────────────────
        elif source_type == "wikimedia":
            clips = wikimedia_fetcher.fetch_wikimedia_clips(
                search_query, stem=stem, count=3, duration=total_dur
            )
            if not clips:
                print(f"    [Wikimedia] No results — trying DALL-E")
                clips = dalle_clip(search_query)
            if not clips:
                clips = fetch_clips_for_segment(keyword, mood, footage_dir, needed=5)

        # ── dalle ─────────────────────────────────────────────────────────────
        elif source_type == "dalle":
            clips = dalle_clip(search_query)
            if not clips:
                print(f"    [DALLE] Failed — trying stock fallback")
                clips = fetch_clips_for_segment(keyword, mood, footage_dir, needed=5)

        # ── archive ───────────────────────────────────────────────────────────
        elif source_type == "archive":
            clips = archive_fetcher.fetch_archive_clips(search_query, stem=stem, count=3)
            if not clips:
                print(f"    [Archive] No results — trying DALL-E")
                clips = dalle_clip(search_query)
            if not clips:
                clips = fetch_clips_for_segment(keyword, mood, footage_dir, needed=5)

        # ── stock: route to DALL-E if DALLE_FALLBACK_FOR_STOCK is set ─────────
        else:
            if DALLE_FALLBACK_FOR_STOCK:
                dalle_prompt = f"{keyword}, {mood} cinematic mood"
                clips = dalle_clip(dalle_prompt)
                if not clips:
                    clips = fetch_clips_for_segment(keyword, mood, footage_dir, needed=5)
            else:
                clips = fetch_clips_for_segment(keyword, mood, footage_dir, needed=5)

        # ── clip selection: use first available clip (vision review disabled) ──
        best_clip = clips[0] if clips else None

        # Fallback to previously used clips if nothing found
        if best_clip is None:
            if fallback_clips:
                candidates = [c for c in fallback_clips if c != last_used_path]
                best_clip = candidates[0] if candidates else fallback_clips[0]
                clips = fallback_clips
                print(f"    Using fallback clip")
            else:
                print(f"    No clips — skipping segment {i+1}")
                continue

        # Update fallback pool
        if clips:
            fallback_clips = clips

        # Chain unique clips to fill total_dur — no looping
        available = [c for c in clips if c != last_used_path] if clips else [best_clip]
        if best_clip not in available:
            available = [best_clip] + available

        remaining = total_dur
        clip_idx = 0
        while remaining > 0.1:
            clip = available[clip_idx % len(available)]
            clip_dur = get_clip_duration(clip)
            use_dur = min(clip_dur, remaining)
            entries.append({"path": clip, "duration": use_dur})
            last_used_path = clip
            remaining -= use_dur
            clip_idx += 1

    est_review_cost = round(total_review_tokens * 0.000003, 3)
    print(f"\n  Vision review: {total_review_tokens} tokens (~${est_review_cost})")
    return entries


def parse_srt_timestamps(srt_path: Path) -> list[dict]:
    """Parse SRT file into list of {index, start, end, text} dicts."""
    if not srt_path.exists():
        return []
    content = srt_path.read_text(encoding="utf-8")
    entries = []
    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3:
            continue
        try:
            time_line = lines[1]
            m = re.match(
                r"(\d{2}:\d{2}:\d{2}[,\.]\d{3})\s+-->\s+(\d{2}:\d{2}:\d{2}[,\.]\d{3})",
                time_line,
            )
            if not m:
                continue
            start = srt_time_to_seconds(m.group(1))
            end = srt_time_to_seconds(m.group(2))
            text = " ".join(lines[2:])
            entries.append({"start": start, "end": end, "text": text})
        except (ValueError, IndexError):
            continue
    return entries


def srt_time_to_seconds(t: str) -> float:
    """Convert SRT timestamp '00:01:23,456' to seconds float."""
    t = t.replace(",", ".")
    parts = t.split(":")
    h, m, s = float(parts[0]), float(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def find_segment_timestamp(segment_text: str, srt_entries: list) -> tuple[float, float] | None:
    """
    Match a script segment's first ~8 words to SRT entries.
    Returns (start_seconds, end_seconds) or None.
    """
    # Use first 6 words of segment as anchor
    anchor_words = segment_text.split()[:6]
    anchor = " ".join(anchor_words).lower()
    # Remove punctuation for matching
    anchor_clean = re.sub(r"[^\w\s]", "", anchor)

    best_match = None
    best_start = None
    best_end = None

    for entry in srt_entries:
        entry_clean = re.sub(r"[^\w\s]", "", entry["text"].lower())
        if any(w in entry_clean for w in anchor_clean.split() if len(w) > 3):
            best_start = entry["start"]
            # Find end: scan forward for last matching SRT entry for this segment
            seg_words = set(re.sub(r"[^\w\s]", "", segment_text.lower()).split())
            for later_entry in srt_entries:
                later_clean = re.sub(r"[^\w\s]", "", later_entry["text"].lower())
                later_words = set(later_clean.split())
                if later_words & seg_words and later_entry["start"] >= best_start:
                    best_end = later_entry["end"]
            break

    if best_start is not None and best_end is not None:
        return (best_start, best_end)
    return None


def escape_ffmpeg_text(text: str) -> str:
    """Escape special characters for ffmpeg drawtext."""
    text = text.replace("\\", "\\\\")
    text = text.replace("'", "\\'")
    text = text.replace(":", "\\:")
    return text


def _seconds_to_ass_time(s: float) -> str:
    """Convert seconds to ASS subtitle time format H:MM:SS.cs"""
    h = int(s // 3600)
    m = int((s % 3600) // 60)
    sec = int(s % 60)
    cs = int((s % 1) * 100)
    return f"{h}:{m:02d}:{sec:02d}.{cs:02d}"


def _parse_srt(srt_path: Path) -> list:
    """Parse SRT file → list of (start_s, end_s, text) tuples."""
    import re
    content = srt_path.read_text(encoding="utf-8", errors="ignore")
    blocks = []
    for m in re.finditer(
        r"\d+\r?\n(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})\r?\n([\s\S]*?)(?=\r?\n\r?\n|\Z)",
        content,
    ):
        def ts(t):
            t = t.replace(",", ".")
            h, mi, s = t.split(":")
            return int(h) * 3600 + int(mi) * 60 + float(s)
        text = " ".join(m.group(3).split())
        if text:
            blocks.append((ts(m.group(1)), ts(m.group(2)), text))
    return blocks


def _find_phrase_in_srt(words: list, blocks: list, search_from: int,
                         min_word_len: int = 4, min_matches: int = 2) -> tuple:
    """
    Forward scan: find the first SRT block (from search_from) that contains
    at least min_matches words from the given word list (length > min_word_len).
    Returns (block_index, start_seconds) or (None, None) if not found.
    """
    anchor = [w for w in words if len(w) >= min_word_len]
    if not anchor:
        return None, None
    anchor_set = set(anchor)
    # If we only have 1 anchor word, require just 1 match (can't require 2)
    effective_min = min(min_matches, len(anchor_set))
    for bi in range(search_from, len(blocks)):
        block_clean = re.sub(r"[^\w\s]", "", blocks[bi][2].lower())
        block_words = set(block_clean.split())
        overlap = block_words & anchor_set
        if len(overlap) >= effective_min:
            return bi, blocks[bi][0]
        # Also accept a single very specific word (8+ chars) as a strong signal
        if any(len(w) >= 8 and w in block_words for w in anchor_set):
            return bi, blocks[bi][0]
    return None, None


def _srt_segment_times(segments: list, srt_path: Path) -> list:
    """
    For each segment, find WHEN the highlight_phrase (or segment's opening words)
    is spoken in the SRT. Returns (start_s, start_s + DISPLAY_DUR) so the overlay
    appears as a short punchy card (not stretched across the whole segment window).

    Strategy (in priority order):
      1. Match highlight_phrase words directly in SRT — phrase is often literally spoken
      2. Match first 8 words of segment text — finds segment start
      3. Fall back to current SRT position estimate

    Returns list of (start_s, end_s) parallel to segments, or None on failure.
    """
    DISPLAY_DUR = 5.0   # seconds each overlay card is shown
    MIN_GAP     = 0.4   # minimum silence between consecutive overlays

    try:
        blocks = _parse_srt(srt_path)
        if not blocks:
            return None

        times = []
        search_from = 0

        for seg in segments:
            phrase = seg.get("highlight_phrase") or ""
            seg_text = seg.get("text", "")

            # ── Priority 1: literal phrase substring match in SRT ────────────
            # Word-set overlap is unreliable for short phrases (e.g. "THREE FOR THREE"
            # → only {"three"} survives the 4-char filter → matches anything).
            # Literal substring search is more precise.
            phrase_str = re.sub(r"[^\w\s]", "", phrase.lower())
            bi, t_start = None, None
            for _bi in range(search_from, len(blocks)):
                block_clean = re.sub(r"[^\w\s]", "", blocks[_bi][2].lower())
                if phrase_str in block_clean:
                    bi, t_start = _bi, blocks[_bi][0]
                    break
            phrase_words = phrase_str.split()  # keep for fallback below

            # ── Priority 2: match first 8 words of segment text ───────────────
            if t_start is None:
                opener_words = re.sub(r"[^\w\s]", "", seg_text.lower()).split()[:8]
                bi, t_start = _find_phrase_in_srt(opener_words, blocks, search_from,
                                                   min_word_len=4, min_matches=2)

            # ── Fallback: current position ─────────────────────────────────────
            if t_start is None:
                if search_from < len(blocks):
                    t_start = blocks[search_from][0]
                    bi = search_from
                else:
                    t_start = blocks[-1][1]
                    bi = len(blocks) - 1

            times.append((t_start, t_start + DISPLAY_DUR))
            # Advance past this block so next segment doesn't match the same spot
            search_from = (bi + 1) if bi is not None else search_from + 1

        # ── Enforce no-overlap: clip end of each item to leave MIN_GAP ─────────
        for i in range(len(times) - 1):
            s_cur, e_cur = times[i]
            s_next, _ = times[i + 1]
            if e_cur + MIN_GAP > s_next:
                times[i] = (s_cur, max(s_cur + 0.5, s_next - MIN_GAP))

        return times
    except Exception as e:
        print(f"  SRT timing parse failed ({e}) — falling back to word-count proportion")
        return None


def apply_text_overlays(input_path: Path, segments: list, srt_path: Path,
                         output_path: Path, audio_duration: float = None) -> bool:
    """
    Second ffmpeg pass: burn highlight_phrase text overlays timed to each segment.
    Bold orange text with dark box, top-center position (above subtitles).

    Uses ASS subtitle burning (-vf ass=file.ass) — avoids all filter_complex
    expression issues on Windows. Timing derived from SRT timestamps for accuracy.

    Returns (success: bool, srt_times: list|None).
    """
    overlay_segments = [
        seg for seg in segments
        if seg.get("highlight_phrase") and seg["highlight_phrase"] is not None
    ]
    if not overlay_segments:
        print("  No highlight phrases — skipping text overlay pass.")
        return False, None

    if audio_duration is None:
        audio_duration = get_audio_duration(input_path)

    print(f"  Applying text overlays for {len(overlay_segments)} segment(s) via ASS subtitles...")

    # ── Timing: SRT phrase matching (accurate) ───────────────────────────────
    # Uses actual Whisper SRT timestamps to place overlays when phrase is spoken.
    # Falls back to word-count proportional if SRT parse fails.
    srt_times = _srt_segment_times(segments, srt_path)
    total_words = sum(len(s["text"].split()) for s in segments) or 1

    overlay_items = []
    for seg_idx, seg in enumerate(segments):
        phrase = seg.get("highlight_phrase")
        if not phrase:
            continue
        if srt_times:
            t_start, t_end = srt_times[seg_idx]
        else:
            words_before = sum(len(segments[j]["text"].split()) for j in range(seg_idx))
            seg_words_list = re.sub(r"[^\w\s]", "", seg["text"].lower()).split()
            seg_word_count = len(seg_words_list)
            t_seg_start = (words_before / total_words) * audio_duration
            t_seg_end   = ((words_before + seg_word_count) / total_words) * audio_duration
            phrase_words = re.sub(r"[^\w\s]", "", phrase.lower()).split()
            phrase_offset = 0
            for i in range(len(seg_words_list)):
                if seg_words_list[i:i + len(phrase_words)] == phrase_words:
                    phrase_offset = i
                    break
            t_start = ((words_before + phrase_offset) / total_words) * audio_duration
            t_start = min(t_start, max(t_seg_start, t_seg_end - 4.5))
            t_end   = t_start + 4.5
        overlay_items.append((t_start, t_end, phrase.upper()))

    if not overlay_items:
        print("  No overlay items — skipping.")
        return False, None

    # ── Generate ASS subtitle file ────────────────────────────────────────────
    # ASS color format: &HAABBGGRR (AA=alpha: 00=opaque, FF=transparent)
    # Orange (255,165,0): R=FF G=A5 B=00 → &H0000A5FF
    # BorderStyle=3 = opaque box; Alignment=8 = top-center; MarginV=160 = 160px from top
    # BackColour &HAA000000 = ~33% opaque dark box behind text
    ass_lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1920",
        "PlayResY: 1080",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: Overlay,Arial Black,96,&H0000A5FF,&H000000FF,&H00000000,"
        "&HAA000000,-1,0,0,0,100,100,2,0,3,0,0,8,20,20,160,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]

    for start_s, end_s, phrase in overlay_items:
        start_ass = _seconds_to_ass_time(start_s)
        end_ass   = _seconds_to_ass_time(end_s)
        safe = phrase.replace("\\", "").replace("{", "").replace("}", "")
        ass_lines.append(f"Dialogue: 0,{start_ass},{end_ass},Overlay,,0,0,0,,{safe}")

    # Write ASS file inside ROOT so we can pass a relative path to ffmpeg.
    # Absolute Windows paths contain C: which ffmpeg treats as a filter option
    # separator — relative paths avoid the colon entirely.
    import os
    ass_path = ROOT / "_tmp_overlay.ass"
    ass_path.write_text("\n".join(ass_lines), encoding="utf-8-sig")

    # ── Burn ASS into video ───────────────────────────────────────────────────
    cmd = [
        "ffmpeg", "-y",
        "-i", str(input_path),
        "-vf", "ass=_tmp_overlay.ass",
        "-c:v", "libx264", "-preset", "fast",
        "-c:a", "copy",
        "-b:v", VIDEO_BITRATE,
        "-pix_fmt", "yuv420p",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    ass_path.unlink(missing_ok=True)

    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        print(f"  Text overlay pass complete: {output_path.name}")
        return True, srt_times
    else:
        print(f"  Text overlay (ASS) failed (non-fatal):\n{result.stderr[-2000:]}")
        return False, None


def run_ffmpeg(cmd: list, label: str):
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  ffmpeg error ({label}):\n{result.stderr[-3000:]}")
        raise RuntimeError(f"ffmpeg failed: {label}")


def assemble(audio_path: Path, entries: list, output_path: Path, audio_duration: float):
    music_path = AUDIO_DIR / BACKGROUND_MUSIC_FILE
    has_music = music_path.exists() and music_path.stat().st_size > 0
    total_duration = audio_duration + VIDEO_OUTRO_SECONDS
    fade_start = total_duration - VIDEO_OUTRO_FADE_SECONDS

    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Pre-process: trim each clip to exact segment duration
        print("  Pre-processing clips (trim to segment duration)...")
        processed = preprocess_clips(entries, tmp_dir)

        concat_file = build_concat_file(processed, tmp_dir)

        print("  Running ffmpeg final assembly...")

        if has_music:
            print(f"  Mixing background music: {music_path.name} (volume={BACKGROUND_MUSIC_VOLUME})")
            print(f"  Outro: {VIDEO_OUTRO_SECONDS}s music tail + {VIDEO_OUTRO_FADE_SECONDS}s fadeout")
            # Voiceover padded with silence for outro, music looped with fadeout at end
            filter_complex = (
                f"[1:a]loudnorm=I=-14:TP=-1.5:LRA=11,apad=pad_dur={VIDEO_OUTRO_SECONDS}[vo];"
                f"[2:a]volume={BACKGROUND_MUSIC_VOLUME},"
                f"afade=t=out:st={fade_start:.3f}:d={VIDEO_OUTRO_FADE_SECONDS}[bg];"
                f"[vo][bg]amix=inputs=2:duration=first:dropout_transition=0[aout]"
            )
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),  # 0: video
                "-i", str(audio_path),                                   # 1: voiceover
                "-stream_loop", "-1", "-i", str(music_path),            # 2: music (looped)
                "-filter_complex", filter_complex,
                "-map", "0:v:0",
                "-map", "[aout]",
                "-t", str(total_duration),
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", VIDEO_BITRATE,
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-r", str(VIDEO_FPS),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_path),
            ]
        else:
            print("  No background music found — assembling without music.")
            print(f"  To add music: place a .mp3 at {music_path}")
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0", "-i", str(concat_file),
                "-i", str(audio_path),
                "-map", "0:v:0", "-map", "1:a:0",
                "-t", str(audio_duration),
                "-c:v", "libx264", "-preset", "fast",
                "-b:v", VIDEO_BITRATE,
                "-c:a", "aac", "-b:a", AUDIO_BITRATE,
                "-r", str(VIDEO_FPS),
                "-pix_fmt", "yuv420p",
                "-movflags", "+faststart",
                str(output_path),
            ]

        run_ffmpeg(cmd, "assembly")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Assemble video from draft")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft", help="Path to specific draft JSON")
    group.add_argument("--latest", action="store_true", help="Use most recent draft")
    args = parser.parse_args()

    draft_path = get_latest_draft() if args.latest else Path(args.draft)
    if args.latest:
        print(f"  Using latest draft: {draft_path.name}")

    data = load_draft(draft_path)
    stem = draft_path.stem

    # Locate audio
    audio_path = AUDIO_DIR / f"{stem}.mp3"
    if not audio_path.exists():
        print(f"  Error: Audio not found at {audio_path}")
        print("  Run voice_generator.py first.")
        sys.exit(1)

    segments = data.get("segments", [])
    if not segments:
        print("  Error: No segments in draft. Re-run script_generator.py to get new format.")
        sys.exit(1)

    # Audio duration
    print("  Measuring audio duration...")
    audio_duration = get_audio_duration(audio_path)
    print(f"  Duration: {audio_duration:.1f}s ({audio_duration/60:.1f} min)")

    # Generate SRT
    srt_path = AUDIO_DIR / f"{stem}.srt"
    ok = generate_srt_local_whisper(audio_path, srt_path)
    if not ok:
        print("  Generating basic timed SRT...")
        srt_content = generate_basic_srt(data.get("script", ""), audio_duration)
        srt_path.write_text(srt_content, encoding="utf-8")
    print(f"  SRT saved: {srt_path} (upload this to YouTube as captions)")

    # Estimate segment durations from word count
    # Use audio_duration only — outro is silent music tail, no footage needed for it
    durations = estimate_segment_durations(segments, audio_duration)

    # Fetch contextual footage per segment
    footage_dir = FOOTAGE_DIR / stem
    footage_dir.mkdir(parents=True, exist_ok=True)
    print(f"\n  Fetching contextual footage for {len(segments)} segments...")
    dalle_clips_log = []
    entries = build_footage_entries(segments, durations, footage_dir,
                                    stem=stem, dalle_clips_log=dalle_clips_log)

    if not entries:
        print("  Error: No footage entries built.")
        sys.exit(1)

    # Assemble base video
    output_path = DRAFTS_DIR / f"{stem}_assembled.mp4"
    if output_path.exists():
        output_path.unlink()

    print(f"\n  Assembling final video...")
    assemble(audio_path, entries, output_path, audio_duration)

    # Text overlay pass (highlight phrases — Johnny Harris style)
    final_path = output_path
    overlay_srt_times = None
    has_phrases = any(seg.get("highlight_phrase") for seg in segments)
    if has_phrases:
        overlay_path = DRAFTS_DIR / f"{stem}_final.mp4"
        print(f"\n  Applying text overlays...")
        ok, overlay_srt_times = apply_text_overlays(output_path, segments, srt_path,
                                                     overlay_path, audio_duration=audio_duration)
        if ok:
            final_path = overlay_path
            print(f"  Final video with overlays: {overlay_path.name}")
        else:
            print(f"  Overlay pass failed — using base assembly: {output_path.name}")

    # Update draft metadata
    size_mb = final_path.stat().st_size / (1024 * 1024)
    video_meta = {
        "path": str(final_path),
        "srt_path": str(srt_path),
        "duration_seconds": audio_duration,
        "file_size_mb": round(size_mb, 1),
        "assembled": True,
    }
    if dalle_clips_log:
        video_meta["dalle_clips"] = dalle_clips_log
        print(f"\n  [DALLE] {len(dalle_clips_log)} AI-generated clip(s) used:")
        for dc in dalle_clips_log:
            print(f"    Segment {dc['segment']}: {dc['prompt'][:60]}")
    update_draft(draft_path, "_video", video_meta)
    output_path = final_path

    # Full QC SLA pass — 11 checks, gates publish readiness
    run_vision_qc(output_path, segments, durations, audio_duration=audio_duration,
                  srt_times=overlay_srt_times)

    total_duration = audio_duration + VIDEO_OUTRO_SECONDS
    print(f"\n{'='*60}")
    print(f"  VIDEO ASSEMBLED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"  Duration  : {total_duration:.1f}s ({total_duration/60:.1f} min) [{VIDEO_OUTRO_SECONDS}s outro]")
    print(f"  File size : {size_mb:.1f} MB")
    print(f"  Video     : {output_path}")
    print(f"  Captions  : {srt_path}")
    print(f"  >> Upload the SRT to YouTube Studio > Subtitles after publishing")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
