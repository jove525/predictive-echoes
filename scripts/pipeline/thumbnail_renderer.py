"""
thumbnail_renderer.py — Generate YouTube thumbnail for @PredictiveEchoes.

Layout: dark background + subject photo (right) + bold text (left).
Output: assets/thumbnails/<stem>.png  (1280×720)

Usage:
    python scripts/pipeline/thumbnail_renderer.py --latest
    python scripts/pipeline/thumbnail_renderer.py --draft outputs/drafts/xxx.json
                                                   --photo pics/photo.png
                                                   --headline "HE CALLED IT."
                                                   --sub "MONTHS BEFORE IT HAPPENED"
"""

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
except ImportError:
    print("ERROR: Pillow not installed. Run: pip install Pillow")
    sys.exit(1)

from scripts.assembler.video_assembler import get_latest_draft

# ── Constants ──────────────────────────────────────────────────────────────────
W, H = 1280, 720
BG_COLOR      = (8, 8, 20)         # #080814
ACCENT_ORANGE = (255, 165, 0)      # orange
ACCENT_RED    = (220, 40, 40)      # red glow
WHITE         = (255, 255, 255)
GREY          = (180, 180, 180)

FONT_CANDIDATES = [
    "C:/Windows/Fonts/ariblk.ttf",    # Arial Black
    "C:/Windows/Fonts/arialbd.ttf",   # Arial Bold
    "C:/Windows/Fonts/calibrib.ttf",  # Calibri Bold
    "C:/Windows/Fonts/verdanab.ttf",  # Verdana Bold
    "C:/Windows/Fonts/arial.ttf",
]

def get_font(size):
    for f in FONT_CANDIDATES:
        try:
            return ImageFont.truetype(f, size)
        except (IOError, OSError):
            continue
    return ImageFont.load_default()


def draw_glow(canvas: Image.Image, x: int, y: int, w: int, h: int,
              color: tuple, radius: int = 120, alpha: int = 80):
    """Draw a soft radial glow ellipse at (x,y) with given size."""
    glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    gd.ellipse([(x - w//2, y - h//2), (x + w//2, y + h//2)],
               fill=(*color, alpha))
    glow = glow.filter(ImageFilter.GaussianBlur(radius))
    canvas.alpha_composite(glow)


def paste_subject(canvas: Image.Image, photo_path: Path,
                  target_x_center: float = 0.72, scale: float = 1.0):
    """
    Paste subject photo onto canvas, anchored at bottom-right region.
    For photos with dark/black backgrounds, blends naturally via darkening.
    """
    img = Image.open(photo_path).convert("RGBA")
    orig_w, orig_h = img.size

    # Scale to fill ~65% of thumbnail height
    target_h = int(H * 0.92 * scale)
    ratio = target_h / orig_h
    new_w = int(orig_w * ratio)
    img = img.resize((new_w, target_h), Image.LANCZOS)

    # Brighten slightly for thumbnail pop
    img_rgb = img.convert("RGB")
    img_rgb = ImageEnhance.Brightness(img_rgb).enhance(1.15)
    img_rgb = ImageEnhance.Contrast(img_rgb).enhance(1.1)
    img = img_rgb.convert("RGBA")

    # Position: center at target_x_center of canvas width, flush to bottom
    paste_x = int(W * target_x_center) - new_w // 2
    paste_y = H - target_h

    # For dark-background photos: use multiply-like blend by darkening bg under subject
    # Simple approach: just paste with alpha; dark pixels blend naturally
    canvas.alpha_composite(img, dest=(paste_x, paste_y))
    return paste_x, new_w


def render_thumbnail(
    photo_path: Path,
    headline: str,
    sub_text: str,
    output_path: Path,
    byline: str = "@PredictiveEchoes",
):
    """Render a 1280×720 YouTube thumbnail."""
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # ── Base canvas ────────────────────────────────────────────────────────────
    canvas = Image.new("RGBA", (W, H), (*BG_COLOR, 255))

    # ── Background glow elements ───────────────────────────────────────────────
    # Warm red/orange glow center-right (behind subject)
    draw_glow(canvas, int(W * 0.72), int(H * 0.55), 500, 400, ACCENT_RED,   radius=100, alpha=55)
    draw_glow(canvas, int(W * 0.55), int(H * 0.6),  400, 300, ACCENT_ORANGE, radius=90,  alpha=25)
    # Cool dark blue edge left
    draw_glow(canvas, 0, H//2, 300, 500, (10, 20, 60), radius=80, alpha=120)

    # ── Subject photo ─────────────────────────────────────────────────────────
    paste_subject(canvas, photo_path, target_x_center=0.77, scale=1.05)

    # ── Right-side vignette to keep text readable on left ─────────────────────
    # (already handled by dark bg + subject placement)

    # ── Text layer ────────────────────────────────────────────────────────────
    draw = ImageDraw.Draw(canvas)

    text_x = 52        # left margin
    text_max_w   = int(W * 0.56)   # headline width limit
    text_max_w_s = int(W * 0.64)   # sub-text can be a bit wider

    def wrap_text(text, font, max_w):
        result = []
        for segment in text.split("\n"):
            words = segment.split()
            line = ""
            for w in words:
                test = (line + " " + w).strip()
                bb = draw.textbbox((0, 0), test, font=font)
                if bb[2] - bb[0] > max_w and line:
                    result.append(line)
                    line = w
                else:
                    line = test
            if line:
                result.append(line)
        return result

    def draw_text_shadowed(x, y, text, font, fill, shadow=(0, 0, 0)):
        draw.text((x + 3, y + 3), text, font=font, fill=(*shadow, 200))
        draw.text((x, y), text, font=font, fill=fill)

    # ── Left-side readability gradient ────────────────────────────────────────
    grad = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(grad)
    for xi in range(int(W * 0.65)):
        alpha = int(130 * max(0, 1 - (xi / (W * 0.62)) ** 2.0))
        gd.line([(xi, 0), (xi, H)], fill=(0, 0, 0, alpha))
    canvas.alpha_composite(grad)
    draw = ImageDraw.Draw(canvas)

    font_h = get_font(112)
    font_s = get_font(38)
    font_b = get_font(22)
    BAR_H  = 5
    BAR_GAP = 48   # gap above and below the accent bar

    h_lines = wrap_text(headline, font_h, text_max_w)
    s_lines = wrap_text(sub_text, font_s, text_max_w_s)

    # ── Pre-measure total text block height ───────────────────────────────────
    def line_h(text, font):
        bb = draw.textbbox((0, 0), text, font=font)
        return bb[3] - bb[1]

    block_h = sum(line_h(l, font_h) + 6 for l in h_lines)
    block_h += BAR_H + BAR_GAP * 3
    block_h += sum(line_h(l, font_s) + 6 for l in s_lines)

    # Vertically center in the usable area (top 90% of canvas, leaving room for byline)
    usable_h = int(H * 0.88)
    y = max(40, (usable_h - block_h) // 2)

    # ── Headline ──────────────────────────────────────────────────────────────
    for hl in h_lines:
        draw_text_shadowed(text_x, y, hl, font_h, WHITE)
        y += line_h(hl, font_h) + 6

    # ── Orange accent bar ─────────────────────────────────────────────────────
    y += BAR_GAP          # full gap below headline
    draw.rectangle([(text_x, y), (text_x + int(text_max_w * 0.85), y + BAR_H)],
                   fill=ACCENT_ORANGE)
    y += BAR_H + BAR_GAP  # full gap above sub-text

    # ── Sub-text ──────────────────────────────────────────────────────────────
    for sl in s_lines:
        draw_text_shadowed(text_x, y, sl, font_s, ACCENT_ORANGE)
        y += line_h(sl, font_s) + 6

    # ── Byline ────────────────────────────────────────────────────────────────
    draw.text((text_x, H - 32), byline, font=font_b, fill=(120, 120, 140))

    # ── Save ──────────────────────────────────────────────────────────────────
    final = canvas.convert("RGB")
    final.save(str(output_path), "PNG", quality=95)
    print(f"Thumbnail saved: {output_path}  ({output_path.stat().st_size // 1024} KB)")
    return output_path


def main():
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true")
    group.add_argument("--draft", help="Path to draft JSON")
    parser.add_argument("--photo", default=str(ROOT / "pics" / "Xueqin_jiang_half_body_shot_predictive_history.png"))
    parser.add_argument("--headline", default="IRAN WAR")
    parser.add_argument("--sub", default="HE CALLED IT\nMONTHS BEFORE IT HAPPENED")
    parser.add_argument("--byline", default="@PredictiveEchoes")
    args = parser.parse_args()

    draft_path = get_latest_draft() if args.latest else Path(args.draft)
    stem = draft_path.stem

    out_dir = ROOT / "assets" / "thumbnails"
    output_path = out_dir / f"{stem}_thumbnail.png"

    render_thumbnail(
        photo_path=Path(args.photo),
        headline=args.headline,
        sub_text=args.sub.replace("\\n", "\n"),
        output_path=output_path,
        byline=args.byline,
    )


if __name__ == "__main__":
    main()
