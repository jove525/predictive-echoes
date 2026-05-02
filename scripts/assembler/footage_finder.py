"""
footage_finder.py — Stock Footage Fetcher
Reads keywords from a draft JSON, searches Pexels for relevant video clips,
downloads them to assets/footage/, and updates the draft with footage metadata.

Usage:
    python scripts/assembler/footage_finder.py --latest
    python scripts/assembler/footage_finder.py --draft outputs/drafts/your_draft.json
"""

import argparse
import json
import sys
import time
import requests
from pathlib import Path

# ── Path setup ─────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    PEXELS_API_KEY,
    FOOTAGE_DIR,
    DRAFTS_DIR,
    FOOTAGE_CLIP_DURATION,
    FOOTAGE_PER_KEYWORD,
)

PEXELS_VIDEO_URL = "https://api.pexels.com/videos/search"
HEADERS = {"Authorization": PEXELS_API_KEY}


def get_latest_draft() -> Path:
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No draft JSON files found in {DRAFTS_DIR}")
    return drafts[0]


def load_draft(draft_path: Path) -> dict:
    return json.loads(draft_path.read_text(encoding="utf-8"))


def search_pexels(keyword: str, per_page: int = 5) -> list:
    """Search Pexels for video clips matching keyword. Returns list of video dicts."""
    params = {
        "query": keyword,
        "per_page": per_page,
        "orientation": "landscape",
        "size": "large",          # HD quality
        "min_duration": 5,
        "max_duration": 20,
    }
    try:
        resp = requests.get(PEXELS_VIDEO_URL, headers=HEADERS, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        return data.get("videos", [])
    except requests.RequestException as e:
        print(f"    Pexels search failed for '{keyword}': {e}")
        return []


def pick_best_file(video: dict) -> dict | None:
    """Pick the best quality video file (prefer HD 1080p, fallback to highest available)."""
    files = video.get("video_files", [])
    # Prefer 1920x1080
    hd = [f for f in files if f.get("width") == 1920 and f.get("height") == 1080]
    if hd:
        return hd[0]
    # Fallback: highest width
    files_sorted = sorted(files, key=lambda f: f.get("width", 0), reverse=True)
    return files_sorted[0] if files_sorted else None


def download_clip(url: str, dest_path: Path) -> bool:
    """Download a video file to dest_path. Returns True on success."""
    try:
        resp = requests.get(url, stream=True, timeout=60)
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)
        return True
    except Exception as e:
        print(f"    Download failed: {e}")
        return False


def fetch_footage_for_keywords(keywords: list, stem: str) -> list:
    """
    For each keyword, fetch and download FOOTAGE_PER_KEYWORD clips.
    Returns list of metadata dicts for all downloaded clips.
    """
    footage_dir = FOOTAGE_DIR / stem
    footage_dir.mkdir(parents=True, exist_ok=True)

    downloaded = []
    seen_ids = set()

    for keyword in keywords:
        print(f"\n  Searching: '{keyword}'")
        videos = search_pexels(keyword, per_page=FOOTAGE_PER_KEYWORD + 3)  # fetch extra for dedup

        count = 0
        for video in videos:
            if count >= FOOTAGE_PER_KEYWORD:
                break

            vid_id = video.get("id")
            if vid_id in seen_ids:
                continue
            seen_ids.add(vid_id)

            best_file = pick_best_file(video)
            if not best_file:
                continue

            filename = f"{keyword.replace(' ', '_')}_{vid_id}.mp4"
            dest = footage_dir / filename

            if dest.exists() and dest.stat().st_size > 0:
                print(f"    Already downloaded: {filename}")
            else:
                print(f"    Downloading: {filename} ({best_file.get('width')}x{best_file.get('height')})")
                success = download_clip(best_file["link"], dest)
                if not success:
                    continue
                time.sleep(0.3)  # be polite to Pexels API

            downloaded.append({
                "keyword": keyword,
                "video_id": vid_id,
                "filename": filename,
                "path": str(dest),
                "width": best_file.get("width"),
                "height": best_file.get("height"),
                "duration": video.get("duration"),
                "photographer": video.get("user", {}).get("name", "Unknown"),
                "pexels_url": video.get("url", ""),
            })
            count += 1

        # Respect Pexels rate limit
        time.sleep(0.5)

    return downloaded


def update_draft_with_footage(draft_path: Path, footage: list):
    data = json.loads(draft_path.read_text(encoding="utf-8"))
    data["_footage"] = {
        "clips": footage,
        "total_clips": len(footage),
        "footage_dir": str(FOOTAGE_DIR / draft_path.stem),
    }
    draft_path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def print_summary(footage: list, stem: str):
    print(f"\n{'='*60}")
    print(f"  FOOTAGE DOWNLOADED SUCCESSFULLY")
    print(f"{'='*60}")
    print(f"  Total clips : {len(footage)}")
    print(f"  Saved to    : {FOOTAGE_DIR / stem}")
    print(f"\n  Clips:")
    for clip in footage:
        print(f"    [{clip['keyword']}] {clip['filename']} ({clip['duration']}s)")
    print(f"{'='*60}\n")


def main():
    parser = argparse.ArgumentParser(description="Fetch stock footage for a draft")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft", help="Path to specific draft JSON")
    group.add_argument("--latest", action="store_true", help="Use most recent draft")
    args = parser.parse_args()

    if args.latest:
        draft_path = get_latest_draft()
        print(f"  Using latest draft: {draft_path.name}")
    else:
        draft_path = Path(args.draft)
        if not draft_path.exists():
            print(f"  Error: Draft not found: {draft_path}")
            sys.exit(1)

    data = load_draft(draft_path)
    keywords = data.get("keywords", [])

    if not keywords:
        print("  Error: No keywords found in draft JSON.")
        sys.exit(1)

    print(f"  Keywords: {', '.join(keywords)}")
    print(f"  Fetching {FOOTAGE_PER_KEYWORD} clips per keyword...")

    footage = fetch_footage_for_keywords(keywords, draft_path.stem)

    if not footage:
        print("  Error: No footage downloaded. Check your Pexels API key.")
        sys.exit(1)

    update_draft_with_footage(draft_path, footage)
    print_summary(footage, draft_path.stem)


if __name__ == "__main__":
    main()
