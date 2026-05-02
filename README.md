# PredictiveEchoes — Autonomous YouTube Agent

Autonomous pipeline for publishing 2 faceless videos/week on geopolitics, empire cycles, and predictive history.

## Quick Start
```bash
# 1. Clone/setup
cd D:\PredictiveEchoes
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Fill in your API keys in .env

# 3. Run manually (Phase 1)
python run.py --topic "Prof. Jiang's prediction on X"

# 4. Run scheduler (Phase 2+)
python scheduler.py
```

## Project Files
| File | Purpose |
|---|---|
| `PROJECT_PLAN.md` | Vision, phases, decisions |
| `ACTIVITY_LOG.md` | Chronological change log + video performance |
| `CLAUDE_MEMORY.md` | Claude's self-improving memory (read+write each run) |
| `STYLE_GUIDE.md` | Voice, tone, script format fed to Claude |
| `.env` | API keys (never commit) |
| `config/settings.py` | All pipeline configuration |

## Pipeline
```
Scheduler → Orchestrator (Claude) → Script → Voice (ElevenLabs)
→ Footage (Pexels) → Assemble (ffmpeg) → Thumbnail (DALL-E)
→ Upload (YouTube API) → Analytics → Memory Update
```

## Docs
- See `PROJECT_PLAN.md` for full architecture and phase roadmap
- See `CLAUDE_MEMORY.md` for learnings that improve each run
