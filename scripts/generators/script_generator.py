"""
script_generator.py — AI Script Generator
Reads CLAUDE_MEMORY.md + STYLE_GUIDE.md, calls Claude API to generate
a full video script, then saves output to outputs/drafts/.

Usage:
    python scripts/generators/script_generator.py --topic "Your topic here"
    python scripts/generators/script_generator.py --topic "Prof. Jiang on X" --source-transcript "path/to/transcript.txt"
"""

import argparse
import json
import sys
import re
from datetime import datetime
from pathlib import Path

import anthropic

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    ANTHROPIC_API_KEY,
    CLAUDE_MODEL,
    CLAUDE_MAX_TOKENS,
    MEMORY_FILE,
    STYLE_GUIDE_FILE,
    DRAFTS_DIR,
    LOGS_DIR,
)


def load_file(path: Path, label: str) -> str:
    """Load a text file, warn if missing."""
    if not path.exists():
        print(f"  Warning: {label} not found at {path}")
        return ""
    return path.read_text(encoding="utf-8")


def build_system_prompt(memory: str, style_guide: str) -> str:
    return f"""You are the script writer for the YouTube channel @PredictiveEchoes.

You write authoritative, conversational, debate-inviting video scripts on geopolitics,
empire cycles, and predictive history. Your primary subject is Prof. Jiang Xueqin's
Predictive History framework, but you also cover other big-idea thinkers.

## Your Style Guide
{style_guide}

## Your Persistent Memory (learnings from previous videos)
{memory if memory else "No prior runs yet — this is the first script."}

## Output Format
Return a JSON object with exactly these fields:
{{
  "title": "Video title following the title formula in the style guide",
  "description": "YouTube description following the description template",
  "tags": ["tag1", "tag2", ...],
  "thumbnail_prompt": "DALL-E image generation prompt for the thumbnail",
  "thumbnail_text": "Max 6 words for thumbnail overlay text",
  "word_count": 0,
  "keywords": ["keyword1", "keyword2", ...],
  "segments": [
    {{
      "text": "The spoken words for this segment — 2 to 4 sentences max",
      "footage_keyword": "specific search term for Pexels/Pixabay stock footage (fallback)",
      "footage_mood": "one of: dramatic, calm, tense, hopeful, ominous, analytical",
      "source_type": "wikimedia|stock|motion_graphic|archive|dalle",
      "search_query": "specific factual query for the primary source",
      "highlight_phrase": "THE MOST IMPACTFUL 5–8 WORDS FROM THIS SEGMENT"
    }},
    ...
  ]
}}

IMPORTANT RULES FOR segments:
- Break the ENTIRE script into segments of 2-4 sentences each
- Every word of the script must appear in exactly one segment, in order
- The concatenation of all segment "text" fields must equal the full spoken script
- Write each segment as pure spoken words — no stage directions, no section labels

CRITICAL RULES FOR footage_keyword:
- Keywords must be SEARCHABLE on stock footage sites (Pexels/Pixabay)
- Use ABSTRACT, SYMBOLIC, or CINEMATIC imagery — NOT literal people or events
- Think "what image EVOKES this idea?" not "what is literally happening?"
- NEVER name real politicians, world leaders, or specific living people
- NEVER request archival or historical footage — stock sites don't have it
- NEVER include years (1971, 1944, etc.) — stock sites can't filter by era
- NEVER use terms like "composite", "infographic", "archival", "overhead shot"

GOOD keyword examples (searchable, evocative, cinematic):
  - Instead of "Trump Xi trade war" → "two chess kings facing each other dramatic"
  - Instead of "Nixon 1971 speech" → "old television static vintage close up"
  - Instead of "US China diplomatic meeting" → "two flags wind stormy sky"
  - Instead of "WWI archival trench footage" → "soldiers silhouettes fog dark battlefield"
  - Instead of "geopolitical strategy map" → "world map globe dark dramatic"
  - Instead of "Federal Reserve building" → "imposing stone government building columns"
  - Instead of "Suez Canal aerial ships" → "cargo ships ocean aerial dramatic"
  - Instead of "G7 summit world leaders" → "suited men around conference table tense"
  - Instead of "oil barrels Saudi desert" → "oil refinery flaring stack desert sunset"
  - Instead of "Chinese factory 1980s" → "industrial factory production line workers"

SOURCE TYPE RULES — choose source_type per segment:
- "wikimedia": named real people, named locations, specific historical events with photos
  Examples: "Khamenei official portrait", "Roman Colosseum aerial view", "US aircraft carrier Pacific"
- "motion_graphic": segments listing data, predictions, numbers, scorecard-style content
  Examples: "5 predictions scorecard", "empire decline graph", "timeline of events"
- "stock": abstract moods, emotions, symbolic objects (chess pieces, clocks, nature, crowds)
  Examples: "chess kings dark board", "countdown clock close up", "city night timelapse"
- "archive": historical footage/images 1900–1985 (wars, treaties, specific events)
  Examples: "Soviet troops Afghanistan 1979", "Suez Crisis 1956", "Cold War Berlin Wall"
- "dalle": abstract concepts that don't exist as real photographs
  Examples: "psychohistory concept visualization", "empire collapse fractal pattern"

search_query rules:
- GOOD: "US Navy aircraft carrier Pacific Ocean", "Roman Colosseum aerial view", "Khamenei official portrait"
- BAD: "military stuff", "old stuff happening", "political things"
- For stock type: search_query can equal footage_keyword
- Be specific and factual — treat it as a Wikipedia or Google Images search

highlight_phrase rules:
- ALL CAPS, ≤8 words, the single most impactful/quotable phrase from the segment
- Think Johnny Harris / podcast-clip style text overlays
- Examples: "IT IS A SYMPTOM", "HE WAS RIGHT", "CONFIRMED — FEBRUARY 28"
- Set to null if no phrase is worth highlighting (CTA segments, transitions)

CALL-TO-ACTION RULES:
- Include AT MOST ONE segment at the very end asking viewers to subscribe/comment
- Only ONE subscribe/comment/engagement segment total — never more
"""


def build_user_prompt(topic: str, source_transcript: str = "") -> str:
    prompt = f"Write a complete video script for the following topic:\n\n{topic}"

    if source_transcript:
        prompt += f"""

## Source Transcript / Reference Material
Use this as your primary source. Quote directly where it strengthens the argument.
Always credit the original speaker.

{source_transcript[:6000]}  # trim to avoid token overload
"""

    prompt += """

Remember:
- Hook must reference something happening RIGHT NOW (use 2026 context)
- 5 predictions must be specific, falsifiable, and time-bound
- End with ONE clear debate question for the comments
- Word count must be between 1,000 and 1,800 words
- Return valid JSON only — no markdown code blocks, no commentary outside the JSON
"""
    return prompt


def generate_script(topic: str, source_transcript: str = "") -> dict:
    """Call Claude API and return parsed script data."""
    print(f"\n  Loading memory and style guide...")
    memory = load_file(MEMORY_FILE, "CLAUDE_MEMORY.md")
    style_guide = load_file(STYLE_GUIDE_FILE, "STYLE_GUIDE.md")

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    system_prompt = build_system_prompt(memory, style_guide)
    user_prompt = build_user_prompt(topic, source_transcript)

    print(f"  Calling Claude ({CLAUDE_MODEL})...")
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=CLAUDE_MAX_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )

    raw = message.content[0].text.strip()

    # Strip markdown code fences if Claude wrapped it anyway
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"\n  Error: Claude returned invalid JSON.\n  {e}")
        print(f"\n  Raw response saved to {LOGS_DIR}/last_raw_response.txt")
        LOGS_DIR.mkdir(exist_ok=True)
        (LOGS_DIR / "last_raw_response.txt").write_text(raw, encoding="utf-8")
        raise

    # Reconstruct full script from segments for convenience
    segments = data.get("segments", [])
    if segments:
        data["script"] = " ".join(s["text"] for s in segments)
        data["word_count"] = len(data["script"].split())

    # Attach token usage for cost tracking
    data["_meta"] = {
        "topic": topic,
        "generated_at": datetime.now().isoformat(),
        "model": CLAUDE_MODEL,
        "input_tokens": message.usage.input_tokens,
        "output_tokens": message.usage.output_tokens,
        "estimated_cost_usd": round(
            (message.usage.input_tokens * 0.000003)
            + (message.usage.output_tokens * 0.000015),
            4,
        ),
    }

    return data


def save_draft(data: dict) -> Path:
    """Save script data to outputs/drafts/ with timestamped filename."""
    DRAFTS_DIR.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    slug = data.get("title", "untitled")[:50]
    slug = re.sub(r"[^\w\s-]", "", slug).strip().replace(" ", "_").lower()
    filename = f"{timestamp}_{slug}.json"
    output_path = DRAFTS_DIR / filename

    output_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    # Also save plain script as .txt for easy reading
    script_path = DRAFTS_DIR / f"{timestamp}_{slug}_script.txt"
    script_path.write_text(
        f"TITLE: {data.get('title', '')}\n\n"
        f"DESCRIPTION:\n{data.get('description', '')}\n\n"
        f"TAGS: {', '.join(data.get('tags', []))}\n\n"
        f"THUMBNAIL TEXT: {data.get('thumbnail_text', '')}\n\n"
        f"WORD COUNT: {data.get('word_count', '?')}\n\n"
        f"{'='*60}\nSCRIPT\n{'='*60}\n\n"
        f"{data.get('script', '')}",
        encoding="utf-8",
    )

    return output_path


def print_summary(data: dict, draft_path: Path):
    meta = data.get("_meta", {})
    print(f"\n{'='*60}")
    print(f"  SCRIPT GENERATED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"  Title      : {data.get('title', '—')}")
    print(f"  Word count : {data.get('word_count', '—')}")
    print(f"  Keywords   : {', '.join(data.get('keywords', []))}")
    print(f"  Input tkns : {meta.get('input_tokens', '—')}")
    print(f"  Output tkns: {meta.get('output_tokens', '—')}")
    print(f"  Est. cost  : ${meta.get('estimated_cost_usd', '—')}")
    print(f"  Saved to   : {draft_path}")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Generate a PredictiveEchoes video script")
    parser.add_argument("--topic", required=True, help="Topic or angle for the video")
    parser.add_argument("--source-transcript", default="", help="Path to source transcript .txt file")
    args = parser.parse_args()

    source_text = ""
    if args.source_transcript:
        transcript_path = Path(args.source_transcript)
        if transcript_path.exists():
            source_text = transcript_path.read_text(encoding="utf-8")
            print(f"  Loaded transcript: {transcript_path.name} ({len(source_text)} chars)")
        else:
            print(f"  Warning: transcript file not found: {transcript_path}")

    print(f"\n  Topic: {args.topic}")
    data = generate_script(args.topic, source_text)
    draft_path = save_draft(data)
    print_summary(data, draft_path)


if __name__ == "__main__":
    main()
