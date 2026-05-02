"""
archive_fetcher.py — Internet Archive footage scaffold (future use).

Currently: search only — no download implemented.
Falls back to stock footage and logs a TODO.

TODO: Implement download when Internet Archive API access is confirmed.
      Focus on: /metadata/{identifier} + /download/{identifier}/{filename}
"""

import sys
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

ARCHIVE_SEARCH_URL = "https://archive.org/advancedsearch.php"


def search_archive(query: str, max_results: int = 5) -> list[dict]:
    """
    Search Internet Archive for video footage matching query.
    Returns list of result dicts (identifier, title, description).
    No download — scaffold only.
    """
    params = {
        "q": f"{query} AND mediatype:movies",
        "fl[]": ["identifier", "title", "description", "year"],
        "rows": max_results,
        "page": 1,
        "output": "json",
    }
    try:
        resp = requests.get(ARCHIVE_SEARCH_URL, params=params, timeout=15)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        print(f"  [Archive] Found {len(docs)} results for '{query}' (download not yet implemented)")
        return docs
    except Exception as e:
        print(f"  [Archive] Search error: {e}")
        return []


def fetch_archive_clips(query: str, stem: str, count: int = 3,
                         duration: float = 10.0) -> list[Path]:
    """
    Scaffold: searches archive but returns empty list (download not implemented).
    Caller should fall back to stock footage.
    """
    print(f"  [Archive] TODO: Download not implemented. Query: '{query}'")
    results = search_archive(query, max_results=count)
    if results:
        print(f"  [Archive] Available (not downloaded): "
              + ", ".join(r.get("title", "?")[:40] for r in results[:3]))
    print(f"  [Archive] Falling back to stock footage.")
    return []
