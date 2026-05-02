"""
dalle_fetcher.py — Generate concept images via DALL-E 3 + apply Ken Burns effect.

Used for abstract concepts that have no real-world photo equivalent.
Cost: ~$0.04/image (standard), ~$0.08/image (hd).

Every DALL-E clip is logged with [DALLE] prefix and tracked in draft JSON
under _video.dalle_clips so the user knows which segments used AI imagery.

Usage (internal — called from video_assembler.py):
    from scripts.assembler.dalle_fetcher import fetch_dalle_clip
"""

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    OPENAI_API_KEY,
    FOOTAGE_DIR,
    KEN_BURNS_FPS,
    DALLE_IMAGE_SIZE,
    DALLE_QUALITY,
)

try:
    import openai
    OPENAI_AVAILABLE = bool(OPENAI_API_KEY)
except ImportError:
    OPENAI_AVAILABLE = False


def generate_dalle_image(prompt: str, output_path: Path) -> Path | None:
    """
    Generate an image via DALL-E 3 and save to output_path.
    Returns output_path on success, None on failure.
    """
    if not OPENAI_AVAILABLE:
        print("  [DALLE] OpenAI not configured — skipping.")
        return None

    client = openai.OpenAI(api_key=OPENAI_API_KEY)

    # Prepend cinematic style instruction to align with channel aesthetic
    styled_prompt = (
        f"Cinematic, photorealistic, dark dramatic lighting, high detail. "
        f"No text, no watermarks, no logos. Landscape 16:9. {prompt}"
    )

    print(f"  [DALLE] Generating image: '{prompt[:70]}...' " if len(prompt) > 70
          else f"  [DALLE] Generating image: '{prompt}'")

    try:
        response = client.images.generate(
            model="dall-e-3",
            prompt=styled_prompt,
            size=DALLE_IMAGE_SIZE,
            quality=DALLE_QUALITY,
            n=1,
        )
        image_url = response.data[0].url

        # Download the image
        import requests
        img_response = requests.get(image_url, timeout=60)
        img_response.raise_for_status()

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(img_response.content)
        print(f"  [DALLE] Saved image: {output_path.name}")
        return output_path

    except Exception as e:
        print(f"  [DALLE] Generation failed: {e}")
        return None


def apply_ken_burns_dalle(image_path: Path, output_path: Path,
                           duration: float = 10.0) -> Path | None:
    """Apply slow zoom-in Ken Burns to DALL-E image → .mp4"""
    fps = KEN_BURNS_FPS
    total_frames = int(duration * fps)
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0006,1.2)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
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
    if result.returncode == 0 and output_path.exists() and output_path.stat().st_size > 0:
        return output_path
    print(f"  [DALLE] ffmpeg Ken Burns failed:\n{result.stderr[-1500:]}")
    return None


def fetch_dalle_clip(prompt: str, stem: str, duration: float = 10.0) -> Path | None:
    """
    Main entry point. Generate DALL-E image, apply Ken Burns, return .mp4 Path.
    Logs [DALLE] prefix to console. Returns None if generation fails.

    Args:
        prompt:   The search_query / concept description from the segment
        stem:     Draft stem for naming output files
        duration: Clip duration in seconds
    """
    footage_dir = FOOTAGE_DIR / stem / "dalle"
    footage_dir.mkdir(parents=True, exist_ok=True)

    slug = re.sub(r"[^\w]", "_", prompt)[:50]
    img_path = footage_dir / f"dalle_{slug}.png"
    mp4_path = footage_dir / f"dalle_{slug}.mp4"

    # Use cached clip if already generated
    if mp4_path.exists() and mp4_path.stat().st_size > 10000:
        print(f"  [DALLE] Using cached clip: {mp4_path.name}")
        return mp4_path

    # Generate image
    img_result = generate_dalle_image(prompt, img_path)
    if not img_result:
        return None

    # Apply Ken Burns
    mp4_result = apply_ken_burns_dalle(img_path, mp4_path, duration)

    # Remove source image to save space
    img_path.unlink(missing_ok=True)

    if mp4_result:
        cost = 0.04 if DALLE_QUALITY == "standard" else 0.08
        print(f"  [DALLE] Clip ready: {mp4_path.name} (~${cost:.2f})")
        return mp4_path

    return None
