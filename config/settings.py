"""
PredictiveEchoes — Central Configuration
All pipeline settings live here. Edit to tune behavior.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent.parent
OUTPUTS_DIR = BASE_DIR / "outputs"
DRAFTS_DIR = OUTPUTS_DIR / "drafts"
PUBLISHED_DIR = OUTPUTS_DIR / "published"
ARCHIVE_DIR = OUTPUTS_DIR / "archive"
ASSETS_DIR = BASE_DIR / "assets"
FOOTAGE_DIR = ASSETS_DIR / "footage"
THUMBNAILS_DIR = ASSETS_DIR / "thumbnails"
AUDIO_DIR = ASSETS_DIR / "audio"
LOGS_DIR = BASE_DIR / "logs"
MEMORY_DIR = BASE_DIR / "memory"
MEMORY_FILE = BASE_DIR / "CLAUDE_MEMORY.md"
STYLE_GUIDE_FILE = BASE_DIR / "STYLE_GUIDE.md"

# ── API Keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID")
PEXELS_API_KEY = os.getenv("PEXELS_API_KEY")
PIXABAY_API_KEY = os.getenv("PIXABAY_API_KEY")
KLING_API_KEY = os.getenv("KLING_API_KEY", "")
KLING_API_SECRET = os.getenv("KLING_API_SECRET", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
YOUTUBE_CLIENT_ID = os.getenv("YOUTUBE_CLIENT_ID")
YOUTUBE_CLIENT_SECRET = os.getenv("YOUTUBE_CLIENT_SECRET")
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# ── Claude Settings ────────────────────────────────────────────────────────────
CLAUDE_MODEL = "claude-sonnet-4-6"
CLAUDE_MAX_TOKENS = 8192
CLAUDE_TEMPERATURE = 1.0  # Claude API uses default; kept for reference

# ── ElevenLabs Settings ────────────────────────────────────────────────────────
ELEVENLABS_MODEL = "eleven_multilingual_v2"
ELEVENLABS_STABILITY = 0.5
ELEVENLABS_SIMILARITY_BOOST = 0.75

# ── Video Settings ─────────────────────────────────────────────────────────────
VIDEO_RESOLUTION = "1920x1080"
VIDEO_FPS = 30
VIDEO_BITRATE = "4000k"
AUDIO_BITRATE = "192k"
SUBTITLE_FONT = "Arial"
SUBTITLE_FONT_SIZE = 22        # smaller — readable but not overwhelming
SUBTITLE_COLOR = "white"
SUBTITLE_OUTLINE_COLOR = "black"
SUBTITLE_OUTLINE_WIDTH = 2
BURN_SUBTITLES = False         # False = upload SRT to YouTube instead of burning in
FOOTAGE_CLIP_DURATION = 6      # seconds per stock clip before cut
FOOTAGE_PER_KEYWORD = 3        # clips to fetch per search keyword

# ── Footage Source Settings ────────────────────────────────────────────────────
# "pexels"         → Pexels only (free)
# "pixabay"        → Pixabay only (free)
# "pexels+pixabay" → Pexels first, Pixabay as fallback (free, best coverage)
# "kling+pexels"   → Kling AI for dramatic segments, Pexels for rest (paid)
FOOTAGE_SOURCE = "pexels+pixabay"

# Kling: only used when FOOTAGE_SOURCE includes "kling"
KLING_SEGMENTS = ["ominous", "dramatic", "tense"]  # moods to generate with Kling

# ── Music Settings ─────────────────────────────────────────────────────────────
# Place a royalty-free ambient .mp3 or .wav at assets/audio/background_music.mp3
# Recommended: dark ambient / cinematic tension tracks from pixabay.com/music (free)
BACKGROUND_MUSIC_FILE = "background_music.mp3"   # filename inside AUDIO_DIR
BACKGROUND_MUSIC_VOLUME = 0.13   # 0.0–1.0 — increased from 0.08 for more dramatic effect (2026-03-15)
VIDEO_OUTRO_SECONDS = 5          # seconds of music-only tail after voiceover ends
VIDEO_OUTRO_FADE_SECONDS = 3     # how long the music fadeout lasts at the very end

# ── Content Settings ───────────────────────────────────────────────────────────
SCRIPT_MIN_WORDS = 1000
SCRIPT_MAX_WORDS = 1800
PUBLISH_SCHEDULE = {
    "days": ["Tuesday", "Friday"],
    "time": "14:00",  # 2 PM — adjust to your audience timezone
    "timezone": "Asia/Manila"  # update to your timezone
}
ANALYTICS_REVIEW_HOURS = 72  # hours after publish to pull performance data

# ── Multi-Source Footage Settings ──────────────────────────────────────────────
WIKIMEDIA_MAX_RESULTS = 5          # images to fetch per query
DALLE_IMAGE_SIZE = "1792x1024"     # landscape ratio
DALLE_QUALITY = "standard"         # or "hd" for higher cost (~$0.08/image)
KEN_BURNS_FPS = 30                 # fps for wikimedia/dalle generated clips
DALLE_FALLBACK_FOR_STOCK = True    # True = use DALL-E instead of Pexels/Pixabay for stock segments

# ── Pipeline Mode ──────────────────────────────────────────────────────────────
# "auto"   → fully autonomous, publishes without approval
# "review" → sends Telegram notification, waits for approval before upload
PIPELINE_MODE = "review"  # start in review mode for safety
