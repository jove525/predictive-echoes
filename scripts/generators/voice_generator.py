"""
voice_generator.py — ElevenLabs Text-to-Speech Generator
Reads a draft JSON from outputs/drafts/, sends the script to ElevenLabs,
and saves the resulting MP3 to assets/audio/.

Usage:
    python scripts/generators/voice_generator.py --draft outputs/drafts/your_draft.json
    python scripts/generators/voice_generator.py --latest
"""

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

from elevenlabs.client import ElevenLabs
from elevenlabs import VoiceSettings

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    ELEVENLABS_API_KEY,
    ELEVENLABS_VOICE_ID,
    ELEVENLABS_MODEL,
    ELEVENLABS_STABILITY,
    ELEVENLABS_SIMILARITY_BOOST,
    AUDIO_DIR,
    DRAFTS_DIR,
    LOGS_DIR,
)


def get_latest_draft() -> Path:
    """Return the most recently created draft JSON."""
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No draft JSON files found in {DRAFTS_DIR}")
    return drafts[0]


def load_draft(draft_path: Path) -> dict:
    return json.loads(draft_path.read_text(encoding="utf-8"))


def clean_script_for_tts(script: str) -> str:
    """
    Clean script text for optimal TTS output.
    - Remove any accidental markdown
    - Ensure natural pause points with punctuation
    - Keep ellipses for intentional pauses
    """
    import re
    # Remove any markdown bold/italic that slipped through
    script = re.sub(r"\*+(.+?)\*+", r"\1", script)
    script = re.sub(r"_+(.+?)_+", r"\1", script)
    # Ensure section breaks have a pause
    script = script.replace("\n\n", "\n\n... ")
    return script.strip()


def generate_audio(script: str, output_path: Path) -> dict:
    """Send script to ElevenLabs and save MP3. Returns usage info."""
    client = ElevenLabs(api_key=ELEVENLABS_API_KEY)

    print(f"  Sending to ElevenLabs ({ELEVENLABS_MODEL})...")
    print(f"  Voice ID : {ELEVENLABS_VOICE_ID}")
    print(f"  Characters: {len(script):,}")

    start = time.time()

    audio_generator = client.text_to_speech.convert(
        voice_id=ELEVENLABS_VOICE_ID,
        text=script,
        model_id=ELEVENLABS_MODEL,
        voice_settings=VoiceSettings(
            stability=ELEVENLABS_STABILITY,
            similarity_boost=ELEVENLABS_SIMILARITY_BOOST,
            style=0.35,
            use_speaker_boost=True,
        ),
    )

    # Stream to file
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    with open(output_path, "wb") as f:
        for chunk in audio_generator:
            if chunk:
                f.write(chunk)

    elapsed = time.time() - start
    file_size_mb = output_path.stat().st_size / (1024 * 1024)

    # ElevenLabs charges per character
    # Estimate: ~$0.30 per 1000 chars on Creator plan
    estimated_cost = round((len(script) / 1000) * 0.30, 4)

    return {
        "characters": len(script),
        "duration_seconds": elapsed,
        "file_size_mb": round(file_size_mb, 2),
        "estimated_cost_usd": estimated_cost,
        "output_path": str(output_path),
    }


def update_draft_with_audio(draft_path: Path, audio_info: dict):
    """Write audio metadata back into the draft JSON."""
    data = json.loads(draft_path.read_text(encoding="utf-8"))
    data["_audio"] = audio_info
    draft_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(audio_info: dict):
    print(f"\n{'='*60}")
    print(f"  AUDIO GENERATED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"  Characters  : {audio_info['characters']:,}")
    print(f"  File size   : {audio_info['file_size_mb']} MB")
    print(f"  Est. cost   : ${audio_info['estimated_cost_usd']}")
    print(f"  Saved to    : {audio_info['output_path']}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate voiceover from draft script")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft", help="Path to specific draft JSON file")
    group.add_argument("--latest", action="store_true", help="Use the most recent draft")
    args = parser.parse_args()

    # Load draft
    if args.latest:
        draft_path = get_latest_draft()
        print(f"  Using latest draft: {draft_path.name}")
    else:
        draft_path = Path(args.draft)
        if not draft_path.exists():
            print(f"  Error: Draft not found: {draft_path}")
            sys.exit(1)

    data = load_draft(draft_path)
    script = data.get("script", "")

    if not script:
        print("  Error: No script found in draft JSON.")
        sys.exit(1)

    # Clean script for TTS
    script = clean_script_for_tts(script)

    # Build output path — same stem as draft, saved to assets/audio/
    stem = draft_path.stem  # e.g. 20260221_120000_prof_jiangs_...
    output_path = AUDIO_DIR / f"{stem}.mp3"

    # Check if already generated (ignore empty/failed files)
    if output_path.exists() and output_path.stat().st_size > 1024:
        print(f"  Audio already exists: {output_path}")
        print("  Delete it manually or rename the draft to regenerate.")
        sys.exit(0)
    elif output_path.exists():
        # Empty or failed file — silently remove and regenerate
        output_path.unlink()

    # Generate
    audio_info = generate_audio(script, output_path)

    # Write audio metadata back to draft JSON
    update_draft_with_audio(draft_path, audio_info)

    print_summary(audio_info)


if __name__ == "__main__":
    main()
