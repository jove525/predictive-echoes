"""
clip_reviewer.py — Claude Vision Clip Reviewer
Extracts frames from candidate video clips and uses Claude's vision
to score each clip's contextual relevance before it enters the pipeline.

Usage (standalone test):
    python scripts/assembler/clip_reviewer.py --segment "Venezuelan oil fields" --mood "ominous" --footage-dir assets/footage/some_folder

Integrated usage (called from video_assembler.py):
    from scripts.assembler.clip_reviewer import pick_best_clip
    best = pick_best_clip(candidate_paths, segment_text, keyword, mood)
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    FOOTAGE_DIR,
)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)


# ── Frame extraction ───────────────────────────────────────────────────────────

def extract_frames(clip_path: Path, n_frames: int = 2) -> list[Path]:
    """
    Extract n evenly-spaced frames from a video clip as JPGs.
    Returns list of temp file paths.
    """
    frames = []
    with tempfile.TemporaryDirectory() as tmp:
        tmp_dir = Path(tmp)

        # Get clip duration
        result = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", str(clip_path)],
            capture_output=True, text=True
        )
        try:
            duration = float(result.stdout.strip())
        except ValueError:
            duration = 5.0

        # Extract frames at evenly spaced timestamps
        for i in range(n_frames):
            ts = duration * (i + 1) / (n_frames + 1)
            frame_path = tmp_dir / f"frame_{i}.jpg"
            cmd = [
                "ffmpeg", "-y",
                "-ss", str(ts),
                "-i", str(clip_path),
                "-vframes", "1",
                "-q:v", "3",       # quality 1-31, lower = better
                "-vf", "scale=640:-1",  # resize for faster API
                str(frame_path),
            ]
            subprocess.run(cmd, capture_output=True)

            if frame_path.exists() and frame_path.stat().st_size > 0:
                # Read and encode immediately (before tmp dir is cleaned up)
                frames.append(frame_path.read_bytes())

    return frames  # list of raw bytes


def frames_to_b64(frame_bytes_list: list) -> list[dict]:
    """Convert frame bytes to Claude image content blocks."""
    blocks = []
    for fb in frame_bytes_list:
        b64 = base64.standard_b64encode(fb).decode("utf-8")
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": b64,
            }
        })
    return blocks


# ── Claude scoring ─────────────────────────────────────────────────────────────

def score_clip(clip_path: Path, segment_text: str, keyword: str, mood: str) -> dict:
    """
    Extract frames from clip and ask Claude to score its relevance.
    Returns dict: {score: 0-10, verdict: accept|reject, reason: str}
    """
    frame_bytes = extract_frames(clip_path, n_frames=2)
    if not frame_bytes:
        return {"score": 0, "verdict": "reject", "reason": "Could not extract frames"}

    image_blocks = frames_to_b64(frame_bytes)

    # Build prompt
    text_block = {
        "type": "text",
        "content": f"""You are a video editor reviewing stock footage clips for a YouTube video.

SEGMENT CONTEXT:
- Spoken text: "{segment_text[:300]}"
- Desired footage keyword: "{keyword}"
- Desired mood: "{mood}"

These are {len(image_blocks)} frames from a candidate stock footage clip.
Score this clip's suitability for the segment above.

Respond with ONLY valid JSON, no other text:
{{
  "score": <integer 0-10>,
  "verdict": "<accept|reject>",
  "what_i_see": "<one sentence describing what is literally in the frames>",
  "reason": "<one sentence explaining the score>"
}}

Scoring guide:
- 8-10: Highly relevant, correct mood, visually matches the spoken content
- 5-7: Somewhat relevant, acceptable for this segment
- 3-4: Loosely related, would feel out of place
- 0-2: Completely wrong — wrong subject, wrong mood, or inappropriate content
- Reject anything scoring below 4

AUTOMATIC REJECT (score 0) for any of:
- Green screen / chroma key background visible
- Animated or cartoon style (not photorealistic)
- Watermarks, logos, or text overlays burned into the footage
- Vertical/portrait orientation video
- Obviously inappropriate or unrelated content"""
    }

    # Combine image blocks + text
    content = image_blocks + [{"type": "text", "text": text_block["content"]}]

    try:
        message = client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=256,
            messages=[{"role": "user", "content": content}],
        )
        raw = message.content[0].text.strip()
        # Strip markdown if present
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            if raw.startswith("json"):
                raw = raw[4:]
        result = json.loads(raw)
        result["clip"] = str(clip_path)
        result["tokens"] = message.usage.input_tokens + message.usage.output_tokens
        return result
    except Exception as e:
        return {
            "score": 0,
            "verdict": "reject",
            "reason": f"Review failed: {e}",
            "clip": str(clip_path),
            "tokens": 0,
        }


# ── Main selector ──────────────────────────────────────────────────────────────

def pick_best_clip(
    candidates: list[Path],
    segment_text: str,
    keyword: str,
    mood: str,
    min_score: int = 4,
    verbose: bool = True,
) -> tuple[Path | None, list[dict]]:
    """
    Score all candidate clips and return the best one above min_score.
    Returns (best_path_or_None, list_of_all_scores).
    """
    if not candidates:
        return None, []

    scores = []
    for clip in candidates:
        result = score_clip(clip, segment_text, keyword, mood)
        scores.append(result)
        if verbose:
            verdict_icon = "OK" if result["verdict"] == "accept" else "NO"
            what_i_see = result.get('what_i_see', '').encode('ascii', 'replace').decode('ascii')
            reason = result.get('reason', '').encode('ascii', 'replace').decode('ascii')
            print(f"      [{verdict_icon}] [{result['score']}/10] {Path(clip).name[:50]}")
            print(f"         >> {what_i_see} | {reason}")

    # Sort by score descending
    accepted = [s for s in scores if s["verdict"] == "accept" and s["score"] >= min_score]
    accepted.sort(key=lambda x: x["score"], reverse=True)

    if accepted:
        best_path = Path(accepted[0]["clip"])
        return best_path, scores

    # If nothing accepted, return highest scorer anyway (better than nothing)
    scores.sort(key=lambda x: x["score"], reverse=True)
    if scores:
        best_path = Path(scores[0]["clip"])
        if verbose:
            print(f"      No clip passed min_score={min_score} — using best available")
        return best_path, scores

    return None, scores


# ── Standalone test ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Test clip reviewer on a footage folder")
    parser.add_argument("--segment", required=True, help="Segment spoken text")
    parser.add_argument("--keyword", required=True, help="Footage keyword")
    parser.add_argument("--mood", default="dramatic", help="Segment mood")
    parser.add_argument("--footage-dir", required=True, help="Folder of .mp4 clips to review")
    args = parser.parse_args()

    footage_dir = Path(args.footage_dir)
    clips = list(footage_dir.glob("*.mp4"))[:6]  # test up to 6 clips

    if not clips:
        print(f"No .mp4 files found in {footage_dir}")
        sys.exit(1)

    print(f"\nReviewing {len(clips)} clips for:")
    print(f"  Segment : '{args.segment[:80]}'")
    print(f"  Keyword : '{args.keyword}'")
    print(f"  Mood    : '{args.mood}'")
    print()

    best, all_scores = pick_best_clip(clips, args.segment, args.keyword, args.mood)

    total_tokens = sum(s.get("tokens", 0) for s in all_scores)
    est_cost = round(total_tokens * 0.000003, 4)

    print(f"\n{'='*60}")
    print(f"  BEST CLIP: {Path(best).name if best else 'None'}")
    print(f"  Tokens used: {total_tokens} (~${est_cost})")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
