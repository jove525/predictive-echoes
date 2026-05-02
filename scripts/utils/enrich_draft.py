"""
enrich_draft.py — Patch existing draft JSON with source_type, search_query, highlight_phrase.
Used to upgrade old drafts to the multi-source pipeline format without re-running voice gen.

Usage:
    python scripts/utils/enrich_draft.py --draft outputs/drafts/<draft>.json
    python scripts/utils/enrich_draft.py --latest
"""

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

import anthropic
from config.settings import ANTHROPIC_API_KEY, CLAUDE_MODEL, DRAFTS_DIR

SYSTEM_PROMPT = """You annotate video script segments for a YouTube channel about geopolitics and empire cycles.

For each segment add THREE new fields:

1. "source_type": choose one of: wikimedia | stock | motion_graphic | archive | dalle
2. "search_query": specific factual query for the chosen source type
3. "highlight_phrase": ALL CAPS, ≤8 words, the most impactful phrase from the segment. Set null if nothing is worth highlighting.

Classification rules — follow strictly:
- wikimedia: ANY segment that NAMES a real person (Khamenei, Putin, Trump, Xi, Jiang Xueqin, etc.) OR a specific named landmark/location (Roman Colosseum, Suez Canal, White House, Strait of Hormuz). ALWAYS choose wikimedia if a named person appears, even if the action dominates the sentence. search_query = "[Name] official portrait" or "[Landmark] [brief descriptor]"
- motion_graphic: ANY segment that contains a numbered prediction ("Prediction one", "Prediction 1", "#1", etc.) PLUS a status word (Confirmed/Active/Pending). Also use for scorecard section intros ("Now the scorecard", "Five predictions").
- archive: specific historical events 1900-1985 WITHOUT named living people as focus (e.g. "Soviet Afghanistan invasion 1979", "Suez Crisis British warships 1956", "Cold War Berlin Wall footage")
- dalle: abstract concepts that cannot be photographed — game theory diagrams, structural decline visualizations, psychohistory concept art, empire metaphors
- stock: ONLY for abstract moods, symbolic objects, and scenes with NO named people or places (e.g. "chess board dark dramatic", "oil tanker ocean", "countdown clock close up")

search_query rules:
- GOOD: "Khamenei official Iranian state portrait", "Roman Colosseum aerial view ruins"
- BAD: "political stuff", "old military"
- For stock: search_query = evocative visual description (same as footage_keyword style)
- For motion_graphic: search_query = brief description of what the graphic should show

highlight_phrase rules:
- ALL CAPS, ≤8 words
- The single most quotable/impactful phrase from that segment
- Examples: "IT IS A SYMPTOM", "HE WAS RIGHT", "CONFIRMED — FEBRUARY 28", "NO CLEAN EXIT"
- null for CTA/subscribe/transition segments that have no quotable moment

Return ONLY a valid JSON array of the annotated segments with ALL original fields preserved.
Do not wrap in markdown. Do not add commentary."""


def enrich_segments(segments: list) -> list:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    print(f"  Calling Claude to classify {len(segments)} segments...")
    response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": (
                "Annotate each of these segments with source_type, search_query, and highlight_phrase.\n\n"
                + json.dumps(segments, indent=2, ensure_ascii=False)
            )
        }],
    )

    raw = response.content[0].text.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)

    enriched = json.loads(raw)

    tokens_in = response.usage.input_tokens
    tokens_out = response.usage.output_tokens
    cost = round(tokens_in * 0.000003 + tokens_out * 0.000015, 4)
    print(f"  Enrichment: {tokens_in} in + {tokens_out} out = ~${cost}")

    return enriched


def get_latest_draft() -> Path:
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No drafts in {DRAFTS_DIR}")
    return drafts[0]


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft", help="Path to draft JSON")
    group.add_argument("--latest", action="store_true")
    parser.add_argument("--force", action="store_true", help="Re-enrich even if already annotated")
    args = parser.parse_args()

    draft_path = get_latest_draft() if args.latest else Path(args.draft)
    print(f"  Enriching: {draft_path.name}")

    data = json.loads(draft_path.read_text(encoding="utf-8"))
    segments = data.get("segments", [])

    if not segments:
        print("  No segments found.")
        sys.exit(1)

    # Check if already enriched
    if not args.force and all("source_type" in s for s in segments):
        print("  Already enriched — skipping. Use --force to re-enrich.")
        return

    enriched = enrich_segments(segments)
    data["segments"] = enriched
    draft_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"  Saved enriched draft: {draft_path.name}")

    # Print summary
    from collections import Counter
    types = Counter(s.get("source_type", "?") for s in enriched)
    phrases = [(i+1, s.get("highlight_phrase")) for i, s in enumerate(enriched) if s.get("highlight_phrase")]
    print(f"\n  Source type breakdown: {dict(types)}")
    print(f"  Highlight phrases ({len(phrases)}):")
    for seg_num, phrase in phrases:
        print(f"    [{seg_num}] {phrase}")


if __name__ == "__main__":
    main()
