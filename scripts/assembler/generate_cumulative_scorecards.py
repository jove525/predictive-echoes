"""
generate_cumulative_scorecards.py
Pre-generates cumulative scorecard clips for prediction segments.

Each clip shows all predictions from P1 up to the current one:
  - mg_011: P1 (highlighted)
  - mg_012: P1 (dimmed) + P2 (highlighted)
  - mg_013: P1+P2 (dimmed) + P3 (highlighted)
  - ... etc.

Clips are saved to the motion_graphics cache folder.
The assembler will use them directly (cache-skip logic prevents overwrite).

Usage:
    python scripts/assembler/generate_cumulative_scorecards.py --latest
    python scripts/assembler/generate_cumulative_scorecards.py --draft outputs/drafts/xxx.json
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import FOOTAGE_DIR
from scripts.assembler.video_assembler import get_latest_draft, load_draft, estimate_segment_durations, get_audio_duration
from scripts.assembler.motion_graphic_renderer import (
    render_cumulative_scorecard,
    ORDINAL_MAP,
    is_scorecard_segment,
)
from config.settings import AUDIO_DIR

# Status keyword detection order (first match wins)
STATUS_ORDER = ["CONFIRMED", "ACTIVE", "PENDING", "VERIFIED"]


def parse_prediction(text: str) -> dict | None:
    """
    Extract (num, short_text, status) from a prediction segment text.
    Returns None if not a prediction segment.
    """
    m = re.match(
        r'^Prediction\s+(?:#?(\d+)|([a-z]+))\s*[—:\.\-]?\s*(.*)',
        text.strip(), re.IGNORECASE | re.DOTALL,
    )
    if not m:
        return None

    num = m.group(1) or ORDINAL_MAP.get((m.group(2) or "").lower(), "?")
    body = m.group(3).strip()

    # Extract status: look only in first 150 chars of body where the standalone
    # declaration always lives (e.g. "Confirmed." right after the prediction text).
    # This avoids false-positives from negated occurrences later in the paragraph
    # like "has not confirmed yet" or "too early to call confirmed".
    status = "PENDING"
    first_chunk = body[:150]
    for s in STATUS_ORDER:
        pattern = r'(?:^|[.!?]\s+|[—–]\s*)' + s + r'\b'
        if re.search(pattern, first_chunk, re.IGNORECASE):
            status = "CONFIRMED" if s == "VERIFIED" else s
            break

    # Clean body: remove status word and trailing noise
    body_clean = re.sub(
        r'\.?\s*(?:Confirmed|Active|Pending|Verified)[^.]*$', '',
        body, flags=re.IGNORECASE,
    ).strip()
    # Take first sentence as the display text
    first_sentence = re.split(r'(?<=[.!?])\s+', body_clean)[0] if body_clean else body[:80]

    return {"num": num, "text": first_sentence, "status": status}


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--draft", help="Path to draft JSON")
    args = parser.parse_args()

    draft_path = get_latest_draft() if args.latest else Path(args.draft)
    print(f"Draft: {draft_path.name}")

    data = load_draft(draft_path)
    stem = draft_path.stem
    segments = data.get("segments", [])

    # Estimate durations (need audio for this)
    audio_path = AUDIO_DIR / f"{stem}.mp3"
    if not audio_path.exists():
        print(f"ERROR: audio not found: {audio_path}")
        sys.exit(1)
    audio_dur = get_audio_duration(audio_path)
    durations = estimate_segment_durations(segments, audio_dur)

    # Collect all prediction segments in order
    predictions = []   # list of {"num", "text", "status", "seg_idx", "duration", "slug"}
    for i, seg in enumerate(segments):
        if seg.get("source_type") != "motion_graphic":
            continue
        text = seg.get("text", "")
        pred = parse_prediction(text)
        if pred is None:
            continue
        slug = re.sub(r"[^\w]", "_", text[:40])
        pred["seg_idx"] = i
        pred["duration"] = durations[i]
        pred["slug"] = slug
        predictions.append(pred)

    if not predictions:
        print("No prediction segments found — nothing to generate.")
        sys.exit(0)

    print(f"\nFound {len(predictions)} prediction(s):")
    for p in predictions:
        print(f"  [{p['seg_idx']:2d}] P{p['num']} {p['status']:12s}  {p['text'][:60]}")

    # Output directory
    mg_dir = FOOTAGE_DIR / stem / "motion_graphics"
    mg_dir.mkdir(parents=True, exist_ok=True)

    # Generate cumulative clips — delete existing files first so assembler re-uses them
    print(f"\nGenerating {len(predictions)} cumulative scorecard clip(s)...")
    for clip_idx, pred in enumerate(predictions):
        i = pred["seg_idx"]
        out_path = mg_dir / f"mg_{i:03d}_{pred['slug']}.mp4"

        # Remove existing so it's treated as freshly generated
        if out_path.exists():
            out_path.unlink()

        print(f"  [{clip_idx + 1}/{len(predictions)}] P{pred['num']} ({pred['status']}) "
              f"showing 1-{clip_idx + 1} of {len(predictions)} -> {out_path.name}")

        result = render_cumulative_scorecard(
            predictions=predictions[:clip_idx + 1],
            highlight_idx=clip_idx,
            output_path=out_path,
            duration=pred["duration"],
        )
        if result:
            print(f"    OK: {result.stat().st_size // 1024} KB")
        else:
            print(f"    FAILED — will fall back to standard render during assembly")

    print(f"\nDone. Run video_assembler.py --latest to rebuild with cumulative scorecards.")


if __name__ == "__main__":
    main()
