"""
kling_generator.py — Kling AI Video Generator
Generates short video clips from text prompts using Kling AI API.
Used when FOOTAGE_SOURCE includes "kling" in settings.py.

To enable:
  1. Sign up at https://klingai.com/dev
  2. Get your API Key and API Secret
  3. Add to .env: KLING_API_KEY and KLING_API_SECRET
  4. Set FOOTAGE_SOURCE = "kling+pexels" in config/settings.py

Kling API docs: https://docs.qingque.cn/d/home/eZQBsKwnqqeVOjWd-YkqM9u7t
Pricing: ~$0.14 per 5s clip on standard mode

Usage (standalone test):
    python scripts/assembler/kling_generator.py --prompt "dark storm clouds over a city" --duration 5
"""

import argparse
import hashlib
import hmac
import json
import sys
import time
import base64
import requests
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    KLING_API_KEY,
    KLING_API_SECRET,
    FOOTAGE_DIR,
)

KLING_BASE_URL = "https://api.klingai.com"


# ── Auth ───────────────────────────────────────────────────────────────────────

def build_kling_jwt() -> str:
    """
    Kling uses JWT authentication.
    Header: {"alg": "HS256", "typ": "JWT"}
    Payload: {"iss": api_key, "exp": now+1800, "nbf": now-5}
    """
    import struct

    def b64url(data: bytes) -> str:
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode()

    header = b64url(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    now = int(time.time())
    payload = b64url(json.dumps({
        "iss": KLING_API_KEY,
        "exp": now + 1800,
        "nbf": now - 5,
    }).encode())

    signing_input = f"{header}.{payload}"
    signature = hmac.new(
        KLING_API_SECRET.encode(),
        signing_input.encode(),
        hashlib.sha256,
    ).digest()

    return f"{signing_input}.{b64url(signature)}"


def kling_headers() -> dict:
    return {
        "Authorization": f"Bearer {build_kling_jwt()}",
        "Content-Type": "application/json",
    }


# ── API calls ──────────────────────────────────────────────────────────────────

def create_video_task(prompt: str, duration: int = 5, aspect_ratio: str = "16:9") -> str:
    """
    Submit a video generation task to Kling.
    Returns task_id.
    duration: 5 or 10 seconds
    """
    payload = {
        "model_name": "kling-v1",
        "prompt": prompt,
        "negative_prompt": "text, watermark, low quality, blurry, cartoon, animation",
        "cfg_scale": 0.5,
        "mode": "std",         # "std" or "pro" (pro = higher quality, higher cost)
        "duration": str(duration),
        "aspect_ratio": aspect_ratio,
    }

    resp = requests.post(
        f"{KLING_BASE_URL}/v1/videos/text2video",
        headers=kling_headers(),
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()

    if data.get("code") != 0:
        raise RuntimeError(f"Kling API error: {data.get('message', data)}")

    task_id = data["data"]["task_id"]
    print(f"    Kling task submitted: {task_id}")
    return task_id


def poll_task(task_id: str, max_wait: int = 600) -> str:
    """
    Poll Kling task until complete. Returns video download URL.
    Typical generation time: 60-180 seconds, can exceed 300s under load.
    """
    start = time.time()
    while time.time() - start < max_wait:
        resp = requests.get(
            f"{KLING_BASE_URL}/v1/videos/text2video/{task_id}",
            headers=kling_headers(),
            timeout=15,
        )
        resp.raise_for_status()
        data = resp.json()

        if data.get("code") != 0:
            raise RuntimeError(f"Kling poll error: {data.get('message')}")

        task_status = data["data"]["task_status"]

        if task_status == "succeed":
            videos = data["data"].get("task_result", {}).get("videos", [])
            if videos:
                return videos[0]["url"]
            raise RuntimeError("Kling task succeeded but no video URL returned")

        elif task_status == "failed":
            raise RuntimeError(f"Kling task failed: {data['data'].get('task_status_msg')}")

        print(f"    Kling status: {task_status} — waiting...")
        time.sleep(10)

    raise TimeoutError(f"Kling task {task_id} timed out after {max_wait}s")


def generate_clip(prompt: str, footage_dir: Path, duration: int = 5) -> Path | None:
    """
    Full flow: submit → poll → download → return local path.
    """
    if not KLING_API_KEY or not KLING_API_SECRET:
        print("    Kling API keys not configured. Set KLING_API_KEY and KLING_API_SECRET in .env")
        return None

    try:
        print(f"    Generating via Kling: '{prompt[:60]}'")
        task_id = create_video_task(prompt, duration=duration)
        video_url = poll_task(task_id)

        slug = "".join(c if c.isalnum() else "_" for c in prompt[:40])
        ts = datetime.now().strftime("%H%M%S")
        dest = footage_dir / f"kling_{slug}_{ts}.mp4"
        footage_dir.mkdir(parents=True, exist_ok=True)

        r = requests.get(video_url, stream=True, timeout=60)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(65536):
                if chunk:
                    f.write(chunk)

        print(f"    Kling clip saved: {dest.name}")
        return dest

    except Exception as e:
        print(f"    Kling generation failed: {e}")
        return None


# ── Standalone test ────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--prompt", required=True)
    parser.add_argument("--duration", type=int, default=5)
    args = parser.parse_args()

    out_dir = FOOTAGE_DIR / "kling_test"
    result = generate_clip(args.prompt, out_dir, args.duration)
    if result:
        print(f"\nSuccess: {result}")
    else:
        print("\nFailed — check API keys and error messages above.")


if __name__ == "__main__":
    main()
