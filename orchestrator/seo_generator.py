# D:\Agent44\seo_generator.py
"""
Generates YouTube-optimised title, description, and tags for a video.
Uses past analytics from runs.db to inform title strategy.
Model: Claude Sonnet.
"""

import json
import logging
import re
import anthropic

from config.settings import ANTHROPIC_API_KEY, SONNET_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the SEO and copywriting specialist for @PredictiveEchoes.

Generate a YouTube-optimised title, description, and tags for the given video script.

Title rules:
- Maximum 100 characters (hard limit)
- Hook-first: lead with the most compelling claim or prediction update
- Use Jiang's name or "Predictive History" when it fits naturally
- Avoid clickbait; the title must be accurate to the content

Description rules:
- Start with timestamps (00:00, 01:30, etc.) — estimate from script segment count
- 2-3 sentences summarising the core argument
- Credit sources: "Sources: [list]"
- End with 3-5 hashtags: #geopolitics is always first

Tags rules:
- 5-10 tags as a JSON list
- Mix broad (#geopolitics) and specific (#JiangXueqin #IranWar2026)

Return ONLY a JSON object:
{
  "title": "title string",
  "description": "full description string",
  "tags": ["tag1", "tag2", ...]
}"""


def generate(draft: dict, analytics_history: list) -> dict:
    """
    Returns SEO dict with title, description, tags.
    Mutates nothing — caller writes result back to draft JSON.
    """
    top_performers = sorted(
        [a for a in analytics_history if a.get("ctr")],
        key=lambda x: x["ctr"],
        reverse=True,
    )[:3]

    script_segments = draft.get("script", draft.get("segments", []))
    script_text = " ".join(
        seg.get("text", seg.get("narration", "")) for seg in script_segments
    )[:3000]

    user_content = f"""Video script summary:
{script_text}

Draft title from script generator: {draft.get('title', 'none')}

Top-performing past titles by CTR (use as style reference):
{json.dumps(top_performers, indent=2) if top_performers else "No history yet."}

Generate the SEO package."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=800,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        seo = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"SEO generator returned unparseable JSON: {e}") from e

    # Enforce title length hard limit
    if len(seo.get("title", "")) > 100:
        seo["title"] = seo["title"][:97] + "..."

    required = {"title", "description", "tags"}
    missing = required - set(seo.keys())
    if missing:
        raise ValueError(f"SEO response missing fields: {missing}")

    if not isinstance(seo.get("tags"), list):
        raise ValueError(f"SEO tags must be a list, got: {type(seo.get('tags'))}")

    logger.info(f"SEO title: {seo['title']}")
    return seo
