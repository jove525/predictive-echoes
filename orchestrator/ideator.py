# D:\Agent44\ideator.py
"""
Proposes the next video topic for a channel.
Reads past topics and analytics from runs.db to avoid repeats
and favour angles that historically drove higher CTR.
Fetches Jiang source URLs for new content signals.
Model: Claude Haiku (routine, low cost).
"""

import json
import logging
import re
import requests
import anthropic

from config.settings import ANTHROPIC_API_KEY, HAIKU_MODEL, CHANNEL
from state.db import get_past_topics, get_analytics_history

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are the content strategist for @PredictiveEchoes, a geopolitics YouTube channel
built on Prof. Jiang Xueqin's Predictive History framework.

Your job: propose the single best video topic for the next publish slot.

Rules:
- Never repeat a topic from the past topics list
- Prefer topics that update or extend the prediction scorecard
- Prefer angles that have driven CTR > 6% in past analytics
- Ground every proposal in a real, current news event
- Topic must be specific and falsifiable — not vague commentary

Return ONLY a JSON object with these fields:
{
  "topic": "specific topic string",
  "angle": "the precise angle or framing for this video",
  "source_urls": ["list of URLs that support this topic"],
  "rationale": "one sentence explaining why this topic now"
}"""


def _fetch_source_signals(urls: list) -> str:
    """Fetch and lightly parse source URLs for new content signals."""
    signals = []
    for url in urls:
        try:
            resp = requests.get(url, timeout=8)
            text = re.sub(r"<[^>]+>", " ", resp.text)
            text = re.sub(r"\s+", " ", text).strip()
            signals.append(f"[{url}]\n{text[:800]}")
        except Exception as e:
            logger.debug(f"Source fetch failed for {url}: {e}")
    return "\n\n".join(signals)


def propose_topic(channel: str) -> dict:
    """
    Returns a proposal dict with keys: topic, angle, source_urls, rationale.
    Raises ValueError if Claude returns unparseable JSON.
    """
    past_topics = get_past_topics(channel)
    analytics = get_analytics_history(channel, limit=10)
    # NOTE: Currently single-channel. When multi-channel support is added,
    # look up CHANNEL config by channel name here.
    source_signals = _fetch_source_signals(CHANNEL.get("jiang_source_urls", []))

    top_performers = sorted(
        [a for a in analytics if a.get("ctr")],
        key=lambda x: x["ctr"],
        reverse=True,
    )[:3]

    user_content = f"""Past topics (DO NOT repeat):
{json.dumps(past_topics, indent=2)}

Top-performing angles by CTR (favour similar):
{json.dumps([{"views": a["views"], "ctr": a["ctr"], "retention": a["retention"]} for a in top_performers], indent=2)}

Latest signals from Jiang source URLs:
{source_signals if source_signals else "No new signals retrieved."}

Propose the next video topic."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=HAIKU_MODEL,
        max_tokens=512,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        proposal = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Ideator returned unparseable JSON: {e}\nRaw: {raw[:200]}") from e

    required = {"topic", "angle", "source_urls", "rationale"}
    missing = required - set(proposal.keys())
    if missing:
        raise ValueError(f"Ideator response missing fields: {missing}")

    logger.info(f"Proposed topic: {proposal['topic']}")
    return proposal
