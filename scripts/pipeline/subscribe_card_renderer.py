"""
subscribe_card_renderer.py — Render a branded subscribe end card for @PredictiveEchoes.

Produces a reusable MP4 asset: assets/subscribe_card.mp4
- 1920x1080, 7 seconds, dark branded background
- Bell icon drawn with Pillow
- "SUBSCRIBE" + "@PredictiveEchoes" text
- Fade in / fade out via ffmpeg

Usage:
    python scripts/pipeline/subscribe_card_renderer.py
    python scripts/pipeline/subscribe_card_renderer.py --duration 8 --output assets/subscribe_card.mp4
"""

import argparse
import subprocess
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).parent.parent.parent
FONTS_DIR = ROOT / "assets" / "fonts"
ASSETS_DIR = ROOT / "assets"


# ── Brand colors ─────────────────────────────────────────────────────────────
BG_COLOR       = (8, 8, 20)         # near-black navy
ACCENT_COLOR   = (220, 50, 50)      # deep red — signal/alert tone
TEXT_PRIMARY   = (255, 255, 255)    # white
TEXT_SECONDARY = (180, 180, 200)    # muted lavender-white
BELL_COLOR     = (220, 50, 50)      # bell matches accent


# ── Bell drawing ─────────────────────────────────────────────────────────────

def draw_bell(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple):
    """
    Draw a simple bell icon centered at (cx, cy) with given size.
    Bell parts: dome (arc), body (polygon), clapper (circle), hat (small rect).
    """
    s = size

    # Bell dome — top arc
    dome_box = [cx - s//2, cy - int(s * 0.55), cx + s//2, cy + int(s * 0.1)]
    draw.arc(dome_box, start=180, end=0, fill=color, width=max(4, s // 16))

    # Bell body — trapezoid below dome
    body_pts = [
        (cx - s//2, cy + int(s * 0.08)),
        (cx + s//2, cy + int(s * 0.08)),
        (cx + int(s * 0.60), cy + int(s * 0.38)),
        (cx - int(s * 0.60), cy + int(s * 0.38)),
    ]
    draw.polygon(body_pts, fill=color)

    # Bell rim — horizontal bar
    rim_h = max(6, s // 14)
    draw.rectangle(
        [cx - int(s * 0.62), cy + int(s * 0.35),
         cx + int(s * 0.62), cy + int(s * 0.35) + rim_h],
        fill=color
    )

    # Clapper — small circle below rim
    clapper_r = max(5, s // 14)
    draw.ellipse(
        [cx - clapper_r, cy + int(s * 0.38) + rim_h,
         cx + clapper_r, cy + int(s * 0.38) + rim_h + clapper_r * 2],
        fill=color
    )

    # Hat / hook — small rect at very top
    hat_w = max(4, s // 20)
    hat_h = max(8, s // 10)
    draw.rectangle(
        [cx - hat_w // 2, cy - int(s * 0.58) - hat_h,
         cx + hat_w // 2, cy - int(s * 0.55)],
        fill=color
    )


# ── Notification wave rings (subtle) ─────────────────────────────────────────

def draw_waves(draw: ImageDraw.ImageDraw, cx: int, cy: int, size: int, color: tuple):
    """Three concentric arcs around bell to suggest notification pulse."""
    for i, r in enumerate([int(size * 0.72), int(size * 0.88), int(size * 1.04)]):
        alpha_color = tuple(int(c * (0.5 - i * 0.12)) for c in color[:3])
        w = max(2, size // 25 - i)
        box = [cx - r, cy - r, cx + r, cy + r]
        draw.arc(box, start=200, end=340, fill=alpha_color, width=w)
        draw.arc(box, start=200, end=340, fill=alpha_color, width=w)


# ── Frame renderer ────────────────────────────────────────────────────────────

def render_frame(width: int = 1920, height: int = 1080) -> Image.Image:
    img = Image.new("RGB", (width, height), BG_COLOR)
    draw = ImageDraw.Draw(img)

    font_bold = ImageFont.truetype(str(FONTS_DIR / "arialbd.ttf"), 96)
    font_sub  = ImageFont.truetype(str(FONTS_DIR / "arialbd.ttf"), 52)
    font_hint = ImageFont.truetype(str(FONTS_DIR / "arialbd.ttf"), 36)

    # Vertical layout — bell + text centered
    bell_cy = height // 2 - 60
    bell_size = 180

    draw_waves(draw, width // 2, bell_cy, bell_size, BELL_COLOR)
    draw_bell(draw, width // 2, bell_cy, bell_size, BELL_COLOR)

    # "SUBSCRIBE" — main CTA
    sub_text = "SUBSCRIBE"
    bbox = draw.textbbox((0, 0), sub_text, font=font_bold)
    tw = bbox[2] - bbox[0]
    ty = bell_cy + bell_size // 2 + 30
    draw.text(((width - tw) // 2, ty), sub_text, font=font_bold, fill=TEXT_PRIMARY)

    # "@PredictiveEchoes" — channel name
    ch_text = "@PredictiveEchoes"
    bbox2 = draw.textbbox((0, 0), ch_text, font=font_sub)
    tw2 = bbox2[2] - bbox2[0]
    cy2 = ty + 110
    draw.text(((width - tw2) // 2, cy2), ch_text, font=font_sub, fill=ACCENT_COLOR)

    # Hint text
    hint = "Turn on notifications to never miss a prediction."
    bbox3 = draw.textbbox((0, 0), hint, font=font_hint)
    tw3 = bbox3[2] - bbox3[0]
    cy3 = cy2 + 72
    draw.text(((width - tw3) // 2, cy3), hint, font=font_hint, fill=TEXT_SECONDARY)

    # Subtle top divider line
    draw.line([(width // 2 - 160, bell_cy - bell_size // 2 - 40),
               (width // 2 + 160, bell_cy - bell_size // 2 - 40)],
              fill=ACCENT_COLOR, width=2)

    return img


# ── Main ──────────────────────────────────────────────────────────────────────

def render_subscribe_card(output_path: Path, duration: int = 7, fps: int = 30):
    frame = render_frame()

    with tempfile.TemporaryDirectory() as tmp:
        frame_path = Path(tmp) / "subscribe_frame.png"
        frame.save(str(frame_path))

        fade = 0.5
        cmd = [
            "ffmpeg", "-y",
            "-loop", "1",
            "-i", str(frame_path),
            "-vf", (
                f"scale=1920:1080,"
                f"fade=t=in:st=0:d={fade},"
                f"fade=t=out:st={duration - fade}:d={fade}"
            ),
            "-t", str(duration),
            "-r", str(fps),
            "-c:v", "libx264",
            "-preset", "fast",
            "-pix_fmt", "yuv420p",
            "-an",
            str(output_path),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"  ffmpeg error:\n{result.stderr[-1000:]}")
            raise RuntimeError("subscribe card render failed")

    print(f"  Subscribe card rendered: {output_path} ({output_path.stat().st_size / 1024:.0f} KB, {duration}s)")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=int, default=7)
    parser.add_argument("--output", type=str, default=str(ASSETS_DIR / "subscribe_card.mp4"))
    args = parser.parse_args()

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"  Rendering @PredictiveEchoes subscribe card...")
    render_subscribe_card(output_path, duration=args.duration)
