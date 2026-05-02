# D:\Agent44\researcher.py
"""
Runs targeted web searches on an approved topic and returns a
structured facts bundle. Explicitly flags unverified claims so the
script generator never states them as facts.
Model: Claude Sonnet + web search.
"""

import json
import logging
import re
import anthropic
import requests

from config.settings import ANTHROPIC_API_KEY, SONNET_MODEL

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are a fact-checker and research analyst for @PredictiveEchoes.

Given a video topic, angle, and raw web search results, produce a structured
facts bundle. Be rigorous: only mark facts as verified if they appear in
multiple credible sources. Flag anything from a single source or that cannot
be confirmed as unverified.

Return ONLY a JSON object with these fields:
{
  "verified_facts": [
    {"claim": "specific factual claim", "source": "source name", "verified": true}
  ],
  "unverified_claims": [
    {"claim": "claim text", "note": "why it is unverified"}
  ],
  "prediction_scorecard": {
    "P1": "CONFIRMED|ACTIVE|PENDING|FAILED",
    "P2": "CONFIRMED|ACTIVE|PENDING|FAILED",
    "P3": "CONFIRMED|ACTIVE|PENDING|FAILED",
    "P4": "CONFIRMED|ACTIVE|PENDING|FAILED",
    "P5": "CONFIRMED|ACTIVE|PENDING|FAILED"
  },
  "key_quotes": ["notable quotes from analysts or officials"],
  "research_date": "YYYY-MM-DD"
}"""

SEARCH_QUERIES = [
    "{topic} latest news 2026",
    "{topic} analyst assessment",
    "Jiang Xueqin prediction {topic}",
    "{topic} geopolitical implications",
]


def _web_search(query: str) -> str:
    """Simple DuckDuckGo HTML search scrape — no API key required."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; research-bot/1.0)"}
        resp = requests.get(
            "https://html.duckduckgo.com/html/",
            params={"q": query},
            headers=headers,
            timeout=10,
        )
        text = re.sub(r"<[^>]+>", " ", resp.text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:1500]
    except Exception as e:
        logger.warning(f"Web search failed for '{query}': {e}")
        return ""


def research(topic: str, angle: str, source_urls: list) -> dict:
    """
    Returns a facts bundle dict.
    Raises ValueError if response is unparseable.
    """
    search_results = []
    for template in SEARCH_QUERIES:
        query = template.format(topic=topic)
        result = _web_search(query)
        if result:
            search_results.append(f"Query: {query}\n{result}")

    user_content = f"""Topic: {topic}
Angle: {angle}
Source URLs provided: {json.dumps(source_urls)}

Web search results:
{chr(10).join(search_results) if search_results else "No search results retrieved."}

Produce the facts bundle for this topic."""

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    response = client.messages.create(
        model=SONNET_MODEL,
        max_tokens=1500,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": user_content}],
    )

    raw = response.content[0].text.strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw)
    raw = re.sub(r"\s*```$", "", raw)

    try:
        bundle = json.loads(raw)
    except json.JSONDecodeError as e:
        raise ValueError(f"Researcher returned unparseable JSON: {e}\nRaw: {raw[:200]}") from e

    required = {"verified_facts", "unverified_claims", "prediction_scorecard", "key_quotes"}
    missing = required - set(bundle.keys())
    if missing:
        raise ValueError(f"Facts bundle missing fields: {missing}")

    logger.info(f"Research complete: {len(bundle['verified_facts'])} verified facts, "
                f"{len(bundle['unverified_claims'])} unverified claims")
    return bundle
