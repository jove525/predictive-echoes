"""
reapply_overlays.py — Re-run text overlay pass + append subscribe card.
Usage: python scripts/assembler/reapply_overlays.py --latest
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import AUDIO_DIR, DRAFTS_DIR
from scripts.assembler.video_assembler import (
    apply_text_overlays, get_audio_duration, get_latest_draft, load_draft
)

SUBSCRIBE_CARD = ROOT / "assets" / "subscribe_card.mp4"


def append_subscribe_card(main_video: Path, card: Path, output: Path) -> bool:
    """Concatenate main_video + card into output using ffmpeg concat demuxer."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt",
                                     delete=False, dir=str(ROOT)) as f:
        f.write(f"file '{str(main_video).replace(chr(92), '/')}'\n")
        f.write(f"file '{str(card).replace(chr(92), '/')}'\n")
        concat_file = Path(f.name)

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", str(concat_file),
        "-c", "copy",
        str(output),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    concat_file.unlink(missing_ok=True)

    if result.returncode == 0 and output.exists() and output.stat().st_size > 0:
        return True
    print(f"  Subscribe card append failed:\n{result.stderr[-1000:]}")
    return False


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

    assembled = DRAFTS_DIR / f"{stem}_assembled.mp4"
    if not assembled.exists():
        print(f"ERROR: assembled video not found: {assembled}")
        sys.exit(1)

    srt_path = AUDIO_DIR / f"{stem}.srt"
    if not srt_path.exists():
        print(f"ERROR: SRT not found: {srt_path}")
        sys.exit(1)

    audio_duration = get_audio_duration(assembled)
    print(f"Duration: {audio_duration:.1f}s")

    # ── Step 1: Text overlays ──────────────────────────────────────────────────
    overlaid_path = DRAFTS_DIR / f"{stem}_overlaid.mp4"
    ok = apply_text_overlays(assembled, segments, srt_path, overlaid_path, audio_duration)
    if not ok:
        print("Overlay pass failed — aborting.")
        sys.exit(1)

    # ── Step 2: Append subscribe card ─────────────────────────────────────────
    final_path = DRAFTS_DIR / f"{stem}_final.mp4"
    if SUBSCRIBE_CARD.exists():
        print(f"  Appending subscribe card ({SUBSCRIBE_CARD.name})...")
        ok2 = append_subscribe_card(overlaid_path, SUBSCRIBE_CARD, final_path)
        if ok2:
            overlaid_path.unlink(missing_ok=True)   # clean up intermediate
            size_mb = final_path.stat().st_size / (1024 * 1024)
            print(f"  Subscribe card appended.")
            print(f"Done: {size_mb:.1f} MB -> {final_path.name}")
        else:
            print("  Subscribe card append failed — using overlaid video as final.")
            overlaid_path.rename(final_path)
            size_mb = final_path.stat().st_size / (1024 * 1024)
            print(f"Done: {size_mb:.1f} MB -> {final_path.name}")
    else:
        print(f"  No subscribe card found at {SUBSCRIBE_CARD} — skipping.")
        overlaid_path.rename(final_path)
        size_mb = final_path.stat().st_size / (1024 * 1024)
        print(f"Done: {size_mb:.1f} MB -> {final_path.name}")


if __name__ == "__main__":
    main()
