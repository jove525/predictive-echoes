# D:\Agent44\config\settings.py
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# ── Paths ──────────────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent
STATE_DIR = ROOT / "state"
LOGS_DIR = ROOT / "logs"
DB_PATH = STATE_DIR / "runs.db"
LOG_FILE = LOGS_DIR / "agent44.log"

PREDICTIVE_ECHOES_ROOT = Path("D:/PredictiveEchoes")
PE_SCRIPTS = PREDICTIVE_ECHOES_ROOT / "scripts"
PE_OUTPUTS = PREDICTIVE_ECHOES_ROOT / "outputs" / "drafts"
PE_CLAUDE_MEMORY = PREDICTIVE_ECHOES_ROOT / "CLAUDE_MEMORY.md"
PE_STYLE_GUIDE = PREDICTIVE_ECHOES_ROOT / "STYLE_GUIDE.md"

# ── API Keys ───────────────────────────────────────────────────────────────────
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
AGENT44_BOT_TOKEN = os.getenv("AGENT44_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")

# ── Models ─────────────────────────────────────────────────────────────────────
HAIKU_MODEL = "claude-haiku-4-5-20251001"
SONNET_MODEL = "claude-sonnet-4-6"

# ── Channel Config ─────────────────────────────────────────────────────────────
CHANNEL = {
    "name": "PredictiveEchoes",
    "youtube_channel_id": "UCNnUCYJfdTFeDFdqFrAyDjg",
    "publish_days": ["Tuesday", "Friday"],
    "jiang_source_urls": [
        "https://singju.com",
        "https://substack.com/@tatsuikeda",
        "https://glenndiesen.substack.com",
    ],
}

# ── Thresholds ─────────────────────────────────────────────────────────────────
SPEND_GATE_THRESHOLD = float(os.getenv("SPEND_GATE_THRESHOLD", "0.50"))
MAX_RETRIES = 3
MAX_FOOTAGE_RERUNS = 3                 # max re-run attempts at publish gate
RETRY_BACKOFF = [30, 60, 120]          # seconds
APPROVAL_TIMEOUT_HOURS = 24
ANALYTICS_DELAY_HOURS = 72             # pull analytics this long after publish
ESTIMATED_COST_PER_RUN = 2.80         # used in spend gate message
