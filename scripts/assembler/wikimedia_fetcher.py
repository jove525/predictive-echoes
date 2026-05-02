"""
wikimedia_fetcher.py — Fetch images from Wikimedia Commons + apply Ken Burns effect.

No API key required. Uses MediaWiki API to search Commons, downloads top landscape
images, then converts to 10s .mp4 via ffmpeg zoompan filter.

Usage:
    python scripts/assembler/wikimedia_fetcher.py --test "Roman Colosseum"
"""

import argparse
import re
import subprocess
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import FOOTAGE_DIR, KEN_BURNS_FPS, VIDEO_FPS

COMMONS_API = "https://commons.wikimedia.org/w/api.php"
HEADERS = {"User-Agent": "PredictiveEchoes/1.0 (youtube automation; contact via channel)"}

# Ken Burns variants — alternated for visual variety
KEN_BURNS_EFFECTS = ["zoom_in", "zoom_out", "pan_right", "pan_left"]

# Minimum image dimensions (pixels) — skip tiny thumbnails
MIN_WIDTH = 1200
MIN_HEIGHT = 600


def search_wikimedia(query: str, max_results: int = 5) -> list[dict]:
    """
    Search Wikimedia Commons for images matching query.
    Returns list of dicts with page title and info.
    """
    params = {
        "action": "query",
        "list": "search",
        "srsearch": f"{query} filetype:bitmap",
        "srnamespace": "6",  # File namespace
        "srlimit": max_results * 3,  # fetch extra to filter by size
        "format": "json",
    }
    try:
        resp = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        results = resp.json().get("query", {}).get("search", [])
        return results[:max_results * 3]
    except Exception as e:
        print(f"  [Wikimedia] Search error: {e}")
        return []


def get_image_info(page_title: str) -> dict | None:
    """
    Fetch image URL and dimensions from Wikimedia Commons API.
    Returns dict with url, width, height or None.
    """
    params = {
        "action": "query",
        "titles": page_title,
        "prop": "imageinfo",
        "iiprop": "url|size|mime",
        "iiurlwidth": "1920",
        "format": "json",
    }
    try:
        resp = requests.get(COMMONS_API, params=params, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        pages = resp.json().get("query", {}).get("pages", {})
        for page in pages.values():
            info_list = page.get("imageinfo", [])
            if info_list:
                info = info_list[0]
                mime = info.get("mime", "")
                if not mime.startswith("image/"):
                    return None
                # Prefer JPEG/PNG — skip SVG/GIF/TIFF
                if mime in ("image/svg+xml", "image/gif", "image/tiff"):
                    return None
                return {
                    "url": info.get("thumburl") or info.get("url"),
                    "width": info.get("thumbwidth") or info.get("width", 0),
                    "height": info.get("thumbheight") or info.get("height", 0),
                }
    except Exception as e:
        print(f"  [Wikimedia] Image info error for '{page_title}': {e}")
    return None


def download_image(url: str, dest_path: Path) -> bool:
    """Download image from URL to dest_path. Returns True on success."""
    try:
        resp = requests.get(url, headers=HEADERS, stream=True, timeout=60)
        resp.raise_for_status()
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        with open(dest_path, "wb") as f:
            for chunk in resp.iter_content(65536):
                if chunk:
                    f.write(chunk)
        return dest_path.exists() and dest_path.stat().st_size > 1000
    except Exception as e:
        print(f"  [Wikimedia] Download failed: {e}")
        return False


def apply_ken_burns(image_path: Path, output_path: Path, duration: float = 10.0,
                    effect: str = "zoom_in") -> bool:
    """
    Apply Ken Burns effect to an image and output as .mp4.

    Effects:
        zoom_in   — slow zoom toward center
        zoom_out  — slow zoom out from center
        pan_right — pan left to right
        pan_left  — pan right to left
    """
    fps = KEN_BURNS_FPS
    total_frames = int(duration * fps)

    # zoompan filter syntax: z=zoom expr, x/y=pan expr, d=duration in frames
    if effect == "zoom_in":
        vf = (
            f"scale=3840:2160:force_original_aspect_ratio=increase,"
            f"crop=3840:2160,"
            f"zoompan=z='min(zoom+0.0008,1.3)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1920x1080:fps={fps},"
            f"scale=1920:1080"
        )
    elif effect == "zoom_out":
        vf = (
            f"scale=3840:2160:force_original_aspect_ratio=increase,"
            f"crop=3840:2160,"
            f"zoompan=z='max(1.3-zoom*0.0008,1.0)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1920x1080:fps={fps},"
            f"scale=1920:1080"
        )
    elif effect == "pan_right":
        vf = (
            f"scale=-1:1080,"
            f"pad=3840:1080:(ow-iw)/2:0,"
            f"zoompan=z=1.0:x='(iw-iw/zoom)*t/{duration}':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1920x1080:fps={fps},"
            f"scale=1920:1080"
        )
    else:  # pan_left
        vf = (
            f"scale=-1:1080,"
            f"pad=3840:1080:(ow-iw)/2:0,"
            f"zoompan=z=1.0:x='iw/zoom-(iw-iw/zoom)*t/{duration}':y='ih/2-(ih/zoom/2)'"
            f":d={total_frames}:s=1920x1080:fps={fps},"
            f"scale=1920:1080"
        )

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(image_path),
        "-vf", vf,
        "-t", str(duration),
        "-c:v", "libx264", "-preset", "fast",
        "-pix_fmt", "yuv420p",
        "-an",
        str(output_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"  [Wikimedia] ffmpeg Ken Burns failed:\n{result.stderr[-2000:]}")
        return False
    return output_path.exists() and output_path.stat().st_size > 0


def fetch_wikimedia_clips(query: str, stem: str, count: int = 3,
                           duration: float = 10.0) -> list[Path]:
    """
    Main entry point. Search Wikimedia Commons, download top landscape images,
    apply Ken Burns effect, return list of .mp4 Paths.

    Args:
        query:    Search query (e.g., "Roman Colosseum aerial view")
        stem:     Draft stem for naming output files
        count:    Max number of clips to return
        duration: Clip duration in seconds
    """
    print(f"  [Wikimedia] Searching: '{query}'")
    footage_dir = FOOTAGE_DIR / stem / "wikimedia"
    footage_dir.mkdir(parents=True, exist_ok=True)

    search_results = search_wikimedia(query, max_results=count * 3)

    # If no results, retry with the first 2 significant words (subject entity only)
    if not search_results:
        short_query = " ".join(
            w for w in query.split()[:4]
            if len(w) > 2 and w.lower() not in {"the", "a", "an", "of", "in", "on", "at"}
        )
        if short_query and short_query.lower() != query.lower():
            print(f"  [Wikimedia] Retrying with shorter query: '{short_query}'")
            search_results = search_wikimedia(short_query, max_results=count * 3)

    if not search_results:
        print(f"  [Wikimedia] No results for: '{query}'")
        return []

    clips = []
    effect_index = 0

    for result in search_results:
        if len(clips) >= count:
            break

        page_title = result.get("title", "")
        if not page_title:
            continue

        info = get_image_info(page_title)
        if not info:
            continue

        # Filter: skip small images
        if info.get("width", 0) < MIN_WIDTH or info.get("height", 0) < MIN_HEIGHT:
            continue

        # Skip portrait-orientation images (want landscape for video)
        if info.get("width", 1) < info.get("height", 1):
            continue

        # Build safe filename
        slug = re.sub(r"[^\w]", "_", query)[:40]
        safe_title = re.sub(r"[^\w]", "_", page_title)[:30]
        img_ext = ".jpg"
        img_path = footage_dir / f"wm_{slug}_{safe_title}{img_ext}"
        mp4_path = footage_dir / f"wm_{slug}_{safe_title}.mp4"

        # Use cached clip if exists
        if mp4_path.exists() and mp4_path.stat().st_size > 10000:
            print(f"    [Wikimedia] Using cached: {mp4_path.name}")
            clips.append(mp4_path)
            effect_index += 1
            continue

        # Download image
        print(f"    [Wikimedia] Downloading: {page_title[:60]}")
        if not download_image(info["url"], img_path):
            continue

        # Apply Ken Burns
        effect = KEN_BURNS_EFFECTS[effect_index % len(KEN_BURNS_EFFECTS)]
        print(f"    [Wikimedia] Applying Ken Burns ({effect}): {mp4_path.name}")
        if apply_ken_burns(img_path, mp4_path, duration=duration, effect=effect):
            clips.append(mp4_path)
            effect_index += 1
            # Remove source image to save space
            img_path.unlink(missing_ok=True)

        time.sleep(0.5)  # be polite to Wikimedia servers

    print(f"  [Wikimedia] Got {len(clips)} clip(s) for '{query}'")
    return clips


# ── CLI test mode ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", required=True, help="Search query to test")
    parser.add_argument("--count", type=int, default=2, help="Number of clips")
    parser.add_argument("--duration", type=float, default=10.0, help="Clip duration in seconds")
    args = parser.parse_args()

    clips = fetch_wikimedia_clips(args.test, stem="test", count=args.count, duration=args.duration)
    if clips:
        print(f"\nSuccess! Created {len(clips)} clip(s):")
        for c in clips:
            print(f"  {c}")
    else:
        print("\nNo clips produced.")
