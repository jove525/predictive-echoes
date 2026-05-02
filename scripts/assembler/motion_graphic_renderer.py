"""
motion_graphic_renderer.py — Generate motion graphic clips from segment text.

Uses Pillow (PIL) for image composition and ffmpeg for Ken Burns animation.
Outputs 1920x1080 .mp4 clips — no API calls, fully deterministic.

Style: white text on dark vertical gradient (#0a0a0a → #1a1a2e), centered,
word-wrapped, slow zoom Ken Burns.

Auto-detects:
  - Scorecard: text contains "Prediction" + status words (CONFIRMED/ACTIVE/PENDING)
  - Text card: everything else

Usage:
    python scripts/assembler/motion_graphic_renderer.py --test
"""

import argparse
import re
import subprocess
import sys
import textwrap
from pathlib import Path

try:
    from PIL import Image, ImageDraw, ImageFont
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import FOOTAGE_DIR, KEN_BURNS_FPS

# ── Style constants ─────────────────────────────────────────────────────────────
WIDTH, HEIGHT = 1920, 1080
GRADIENT_TOP = (10, 10, 10)       # #0a0a0a
GRADIENT_BOTTOM = (26, 26, 46)    # #1a1a2e
TEXT_COLOR = (255, 255, 255)
ACCENT_COLOR = (180, 140, 255)    # soft purple accent for titles

# Status badge colors
STATUS_COLORS = {
    "CONFIRMED": (52, 199, 89),    # green
    "ACTIVE":    (255, 214, 10),   # yellow
    "PENDING":   (142, 142, 147),  # grey
}

# Font sizes
FONT_LARGE = 72
FONT_MEDIUM = 52
FONT_SMALL = 38
FONT_BADGE = 32

# Font paths — try system fonts, fall back to PIL default
FONT_CANDIDATES = [
    "C:/Windows/Fonts/arialbd.ttf",    # Arial Bold (Windows)
    "C:/Windows/Fonts/arial.ttf",
    "C:/Windows/Fonts/calibrib.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def get_font(size: int) -> "ImageFont":
    for candidate in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(candidate, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def draw_gradient_background(draw: "ImageDraw", width: int = WIDTH, height: int = HEIGHT):
    """Vertical gradient from GRADIENT_TOP to GRADIENT_BOTTOM."""
    for y in range(height):
        t = y / height
        r = int(GRADIENT_TOP[0] + (GRADIENT_BOTTOM[0] - GRADIENT_TOP[0]) * t)
        g = int(GRADIENT_TOP[1] + (GRADIENT_BOTTOM[1] - GRADIENT_TOP[1]) * t)
        b = int(GRADIENT_TOP[2] + (GRADIENT_BOTTOM[2] - GRADIENT_TOP[2]) * t)
        draw.line([(0, y), (width, y)], fill=(r, g, b))


def image_to_mp4(image_path: Path, output_path: Path, duration: float) -> Path | None:
    """Slow zoom-in Ken Burns on a static image → .mp4"""
    fps = KEN_BURNS_FPS
    total_frames = int(duration * fps)
    vf = (
        f"scale=3840:2160:force_original_aspect_ratio=increase,"
        f"crop=3840:2160,"
        f"zoompan=z='min(zoom+0.0005,1.15)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
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
    print(f"  [MotionGraphic] ffmpeg failed:\n{result.stderr[-1500:]}")
    return None


def render_text_card(text: str, output_path: Path, duration: float = 10.0) -> Path | None:
    """
    Render a simple quote/text card:
    Dark gradient background + white centered word-wrapped text → .mp4
    """
    if not PIL_AVAILABLE:
        print("  [MotionGraphic] Pillow not installed. Run: pip install Pillow")
        return None

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    draw_gradient_background(draw)

    # Determine font size based on text length
    if len(text) < 80:
        font_size = FONT_LARGE
        wrap_width = 30
    elif len(text) < 200:
        font_size = FONT_MEDIUM
        wrap_width = 45
    else:
        font_size = FONT_SMALL
        wrap_width = 60

    font = get_font(font_size)
    lines = textwrap.wrap(text, width=wrap_width)

    # Measure total height
    line_height = font_size + 16
    total_text_height = len(lines) * line_height
    y_start = (HEIGHT - total_text_height) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (WIDTH - text_w) // 2
        y = y_start + i * line_height

        # Subtle shadow
        draw.text((x + 2, y + 2), line, font=font, fill=(0, 0, 0, 128))
        draw.text((x, y), line, font=font, fill=TEXT_COLOR)

    # Save PNG and convert to mp4
    png_path = output_path.with_suffix(".png")
    img.save(str(png_path), "PNG")

    result = image_to_mp4(png_path, output_path, duration)
    png_path.unlink(missing_ok=True)
    return result


ORDINAL_WORDS = {"one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"}
ORDINAL_MAP = {w: str(i+1) for i, w in enumerate(
    ["one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]
)}

def is_scorecard_segment(text: str) -> bool:
    """Detect if text is a scorecard-style segment (numbered predictions + status words)."""
    # Match "Prediction 1", "Prediction #1", "#1"
    has_numbered = bool(re.search(r"prediction\s*#?\s*\d|#\s*\d", text, re.IGNORECASE))
    # Also match spelled-out ordinals: "Prediction one/two/three..."
    if not has_numbered:
        has_numbered = bool(re.search(
            r"prediction\s+(?:one|two|three|four|five|six|seven|eight|nine|ten)\b",
            text, re.IGNORECASE
        ))
    has_status = any(w in text.upper() for w in ("CONFIRMED", "ACTIVE", "PENDING", "VERIFIED"))
    return has_numbered and has_status


def render_scorecard(segment_text: str, output_path: Path, duration: float = 10.0) -> Path | None:
    """
    Render a scorecard-style motion graphic.
    Parses prediction lines and status tags, renders with colored badges.
    """
    if not PIL_AVAILABLE:
        print("  [MotionGraphic] Pillow not installed. Run: pip install Pillow")
        return None

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    draw_gradient_background(draw)

    font_title = get_font(FONT_MEDIUM)
    font_item = get_font(FONT_SMALL)
    font_badge = get_font(FONT_BADGE)

    # Parse predictions — look for lines matching "Prediction N:" or "#N"
    lines_raw = segment_text.strip().split("\n")
    if len(lines_raw) == 1:
        # Might be comma-separated or period-separated — split by sentence
        lines_raw = re.split(r'(?<=[.!?])\s+', segment_text.strip())

    predictions = []
    current_pred = None
    for raw_line in lines_raw:
        line = raw_line.strip()
        if not line:
            continue
        # Match "Prediction 1" or "Prediction one" (spelled-out ordinals)
        m = re.match(
            r'^Prediction\s+(?:#?(\d+)|([a-z]+))\s*[—:\.\-]?\s*(.*)',
            line, re.IGNORECASE
        )
        if m:
            num = m.group(1) or ORDINAL_MAP.get((m.group(2) or "").lower(), "?")
            text_part = m.group(3).strip()
            # Strip trailing status word from text if present at end
            text_part = re.sub(r'\.\s*(?:Confirmed|Active|Pending|Verified)[.\s]*$', '',
                                text_part, flags=re.IGNORECASE).strip()
            current_pred = {"num": num, "text": text_part, "status": "PENDING"}
            predictions.append(current_pred)
            # Check inline status in same line
            for status in ("CONFIRMED", "ACTIVE", "PENDING", "VERIFIED"):
                if status in line.upper():
                    current_pred["status"] = "CONFIRMED" if status == "VERIFIED" else status
                    break
        else:
            # Standalone status line (e.g. "Confirmed." or "Active — Iran has retaliated")
            for status in ("CONFIRMED", "ACTIVE", "PENDING", "VERIFIED"):
                if line.upper().startswith(status[:4]):
                    if current_pred:
                        current_pred["status"] = "CONFIRMED" if status == "VERIFIED" else status
                    break
            else:
                if current_pred and not current_pred["text"]:
                    current_pred["text"] = line

    # If parsing failed, fallback to text card
    if not predictions:
        return render_text_card(segment_text, output_path, duration)

    # ── Layout ──
    title = "PREDICTION SCORECARD"
    title_font = get_font(FONT_LARGE)
    bbox = draw.textbbox((0, 0), title, font=title_font)
    title_w = bbox[2] - bbox[0]
    draw.text(((WIDTH - title_w) // 2 + 2, 82), title, font=title_font, fill=(0, 0, 0))
    draw.text(((WIDTH - title_w) // 2, 80), title, font=title_font, fill=ACCENT_COLOR)

    # Divider line
    draw.line([(160, 160), (WIDTH - 160, 160)], fill=(80, 80, 80), width=2)

    # Prediction rows
    row_height = min(120, (HEIGHT - 220) // max(len(predictions), 1))
    y = 180

    for pred in predictions[:7]:  # max 7 rows
        status = pred.get("status", "PENDING").upper()
        badge_color = STATUS_COLORS.get(status, STATUS_COLORS["PENDING"])

        # Prediction number circle
        circle_r = 28
        cx, cy = 200, y + row_height // 2
        draw.ellipse([(cx - circle_r, cy - circle_r), (cx + circle_r, cy + circle_r)],
                     fill=ACCENT_COLOR)
        num_text = pred["num"]
        nb = draw.textbbox((0, 0), num_text, font=font_badge)
        draw.text((cx - (nb[2] - nb[0]) // 2, cy - (nb[3] - nb[1]) // 2),
                  num_text, font=font_badge, fill=(0, 0, 0))

        # Prediction text (truncated if long)
        pred_text = pred["text"][:80] + ("..." if len(pred["text"]) > 80 else "")
        draw.text((260, y + (row_height - FONT_SMALL) // 2),
                  pred_text, font=font_item, fill=TEXT_COLOR)

        # Status badge
        badge_text = f"  {status}  "
        bb = draw.textbbox((0, 0), badge_text, font=font_badge)
        badge_w = bb[2] - bb[0] + 20
        badge_h = bb[3] - bb[1] + 12
        bx = WIDTH - 200 - badge_w // 2
        by = y + (row_height - badge_h) // 2
        draw.rounded_rectangle([(bx, by), (bx + badge_w, by + badge_h)],
                                radius=8, fill=badge_color)
        draw.text((bx + 10, by + 6), badge_text.strip(), font=font_badge, fill=(0, 0, 0))

        # Row separator
        draw.line([(160, y + row_height - 4), (WIDTH - 160, y + row_height - 4)],
                  fill=(40, 40, 40), width=1)

        y += row_height

    png_path = output_path.with_suffix(".png")
    img.save(str(png_path), "PNG")
    result = image_to_mp4(png_path, output_path, duration)
    png_path.unlink(missing_ok=True)
    return result


def render_cumulative_scorecard(
    predictions: list,
    highlight_idx: int,
    output_path: Path,
    duration: float = 10.0,
) -> "Path | None":
    """
    Render a cumulative scorecard showing predictions[0..highlight_idx].
    The entry at highlight_idx is highlighted (bright, full size).
    Earlier entries are dimmed to show context without stealing focus.

    predictions: list of {"num": str, "text": str, "status": str}
    highlight_idx: index of the newest prediction (0-based into predictions list)
    """
    if not PIL_AVAILABLE:
        print("  [MotionGraphic] Pillow not installed.")
        return None

    visible = predictions[: highlight_idx + 1]

    img = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(img)
    draw_gradient_background(draw)

    font_title  = get_font(FONT_LARGE)
    font_item   = get_font(FONT_SMALL)
    font_item_s = get_font(FONT_BADGE + 4)   # slightly smaller for old rows
    font_badge  = get_font(FONT_BADGE)

    # ── Title ──────────────────────────────────────────────────────────────────
    title = "PREDICTION SCORECARD"
    bbox = draw.textbbox((0, 0), title, font=font_title)
    tw = bbox[2] - bbox[0]
    draw.text(((WIDTH - tw) // 2 + 2, 52), title, font=font_title, fill=(0, 0, 0))
    draw.text(((WIDTH - tw) // 2,     50), title, font=font_title, fill=ACCENT_COLOR)
    draw.line([(140, 140), (WIDTH - 140, 140)], fill=(80, 80, 80), width=2)

    # ── Row layout ─────────────────────────────────────────────────────────────
    max_rows   = 5
    row_height = min(140, (HEIGHT - 200) // max_rows)
    y          = 160

    for idx, pred in enumerate(visible):
        is_new  = (idx == highlight_idx)
        status  = pred.get("status", "PENDING").upper()
        badge_c = STATUS_COLORS.get(status, STATUS_COLORS["PENDING"])

        # Dimmed palette for older rows
        if is_new:
            text_col  = (255, 255, 255)
            num_col   = ACCENT_COLOR
            badge_col = badge_c
            badge_txt = (0, 0, 0)
            item_font = font_item
            alpha_div = 1.0
        else:
            text_col  = (130, 130, 130)
            num_col   = (90, 90, 110)
            badge_col = tuple(int(c * 0.45) for c in badge_c)
            badge_txt = (160, 160, 160)
            item_font = font_item_s
            alpha_div = 0.5

        # Highlight bar behind new row
        if is_new:
            bar_alpha = 25
            draw.rectangle(
                [(120, y + 4), (WIDTH - 120, y + row_height - 6)],
                fill=(180, 140, 255, bar_alpha),
            )

        # Number circle
        circle_r = 26 if is_new else 22
        cx = 200
        cy = y + row_height // 2
        draw.ellipse(
            [(cx - circle_r, cy - circle_r), (cx + circle_r, cy + circle_r)],
            fill=num_col,
        )
        num_text = pred["num"]
        nb = draw.textbbox((0, 0), num_text, font=font_badge)
        draw.text(
            (cx - (nb[2] - nb[0]) // 2, cy - (nb[3] - nb[1]) // 2),
            num_text, font=font_badge, fill=(0, 0, 0) if is_new else (200, 200, 200),
        )

        # Prediction text
        pred_text = pred["text"][:72] + ("…" if len(pred["text"]) > 72 else "")
        txt_y = y + (row_height - (FONT_SMALL if is_new else FONT_BADGE + 4)) // 2
        draw.text((260, txt_y), pred_text, font=item_font, fill=text_col)

        # Status badge
        badge_label = f"  {status}  "
        bb  = draw.textbbox((0, 0), badge_label, font=font_badge)
        bw  = bb[2] - bb[0] + 20
        bh  = bb[3] - bb[1] + 12
        bx  = WIDTH - 180 - bw
        by  = y + (row_height - bh) // 2
        draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=8, fill=badge_col)
        draw.text((bx + 10, by + 6), badge_label.strip(), font=font_badge, fill=badge_txt)

        # Row separator
        sep_col = (60, 60, 60) if is_new else (35, 35, 35)
        draw.line([(140, y + row_height - 2), (WIDTH - 140, y + row_height - 2)],
                  fill=sep_col, width=1)

        y += row_height

    png_path = output_path.with_suffix(".png")
    img.save(str(png_path), "PNG")
    result = image_to_mp4(png_path, output_path, duration)
    png_path.unlink(missing_ok=True)
    return result


def render_motion_graphic(segment_text: str, output_path: Path,
                           duration: float = 10.0) -> Path | None:
    """
    Auto-route: scorecard if text has numbered predictions + status words,
    otherwise text card.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    if is_scorecard_segment(segment_text):
        print(f"  [MotionGraphic] Rendering scorecard -> {output_path.name}")
        return render_scorecard(segment_text, output_path, duration)
    else:
        print(f"  [MotionGraphic] Rendering text card -> {output_path.name}")
        return render_text_card(segment_text, output_path, duration)


# ── CLI test mode ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--test", action="store_true", help="Run test renders")
    args = parser.parse_args()

    if args.test:
        test_dir = FOOTAGE_DIR / "test" / "motion_graphics"
        test_dir.mkdir(parents=True, exist_ok=True)

        # Test text card
        text_card_path = test_dir / "test_text_card.mp4"
        result = render_text_card(
            "The empire's decline is not a military failure. It is a failure of imagination.",
            text_card_path,
            duration=8.0,
        )
        print(f"Text card: {'OK — ' + str(result) if result else 'FAILED'}")

        # Test scorecard
        scorecard_text = (
            "Prediction #1: Iran attacks Israel proxies. CONFIRMED\n"
            "Prediction #2: China moves on Taiwan. ACTIVE\n"
            "Prediction #3: USD loses reserve status. PENDING"
        )
        scorecard_path = test_dir / "test_scorecard.mp4"
        result = render_scorecard(scorecard_text, scorecard_path, duration=12.0)
        print(f"Scorecard: {'OK — ' + str(result) if result else 'FAILED'}")
