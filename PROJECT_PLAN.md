# PredictiveEchoes — Project Plan

## Vision
Autonomous YouTube channel publishing 2 faceless videos per week on geopolitics, empire cycles, predictive history, and big-idea thinkers. Primary inspiration: Prof. Jiang Xueqin's Predictive History framework. The channel curates, contextualizes, and extends these ideas for curious minds who love debate.

## Channel Identity
- **Channel:** [@PredictiveEchoes](https://www.youtube.com/@PredictiveEchoes)
- **Niche:** Geopolitics / Empire Cycles / Predictive History
- **Format:** Faceless commentary — voiceover + stock footage + subtitles
- **Voice:** Pre-built ElevenLabs voice (consistent across all videos)
- **Tone:** Authoritative, conversational, short punchy sentences, rhetorical questions
- **CTA pattern:** Ask audience for debate/opinion in comments, link original sources
- **Publish cadence:** 2x per week (scale up once costs/quality are validated)

## Content Formula (derived from first video)
1. Hook — current event or provocative claim (2–3 sentences)
2. Introduce the thinker/source as authority
3. Core thesis — stripped of jargon
4. Historical parallels — 3 patterns
5. Numbered predictions — typically 5
6. Engagement CTA + subscribe ask
7. Link to original source in description

## Tech Stack
| Component | Tool |
|---|---|
| Orchestration / Script | Claude API (claude-sonnet-4-6) |
| Text-to-Speech | ElevenLabs API |
| Video Assembly | ffmpeg (CLI) |
| Subtitles | OpenAI Whisper → SRT → ffmpeg |
| Stock Footage | Pexels API + Pixabay API |
| Thumbnail | DALL-E 3 or Canva API |
| Upload | YouTube Data API v3 |
| Scheduling | Python APScheduler / cron |
| Analytics | YouTube Analytics API v2 |
| Language | Python 3.11+ |
| Secrets | python-dotenv (.env file) |

## Architecture Overview
```
Scheduler (APScheduler)
    ↓
Orchestrator Agent (Claude)
    ├── source_monitor.py     → detect new Prof. Jiang content + trending topics
    ├── script_generator.py   → generate script using content formula
    ├── voice_generator.py    → ElevenLabs TTS → MP3
    ├── footage_finder.py     → Pexels/Pixabay search by keyword
    ├── video_assembler.py    → ffmpeg: footage + audio + subtitles + title cards
    ├── thumbnail_gen.py      → DALL-E 3 image + text overlay
    ├── uploader.py           → YouTube Data API upload + metadata
    └── analytics_reader.py   → pull CTR/retention → feed back to Claude memory
```

## Phases

### Phase 1 — MVP (Complete)
- [x] Project foundations (this file, logs, memory, config)
- [x] API keys setup (Claude, ElevenLabs, Pexels/Pixabay, YouTube Data API OAuth)
- [x] script_generator.py — Claude generates script from topic/source; reads CLAUDE_MEMORY.md + STYLE_GUIDE.md before each call
- [x] voice_generator.py — ElevenLabs TTS → MP3, streams to assets/audio/
- [x] footage_finder.py — Pexels + Pixabay search by abstract evocative keywords (not literal — e.g. "chess kings dark board" not "Trump Xi Putin"); 3 clips per keyword; 1080p preferred
- [x] clip_reviewer.py — Claude vision scores clips 0–10, auto-rejects green screen; picks best clip per segment
- [x] video_assembler.py — ffmpeg: footage + audio + background music (8% vol) + ASS subtitles + title cards + fade outro
- [x] youtube_uploader.py — YouTube Data API v3 OAuth2; uploads as private; token cached at config/youtube_token.json. NOTE: during OAuth, select "Epic Playlists" (brand account name) to route to @PredictiveEchoes
- [x] analytics_reader.py — YouTube Analytics API v2; pulls views/CTR/retention 72h post-publish
- [x] First video published to @PredictiveEchoes — ID: i4GzVn8QLKM (Feb 25, 2026)

### Phase 2 — Scheduling + Approval Gate (In Progress)
- [x] scheduler.py — APScheduler 2x/week (Tue + Fri 2PM Manila); PIPELINE_MODE=review; --run-now flag
- [x] Pull analytics on first video — 7 views/45.6% retention at day 7; discovery issue not content issue
- [ ] Telegram/email notification with video preview link for human approval gate
- [x] Run pipeline #2 — video #002 assembled + uploaded private (ID: YJBmr6LjuWk) — multi-source footage pipeline
- [ ] Establish consistent 2x/week cadence (scheduler running unattended)

### Phase 3 — Full Autonomy + Self-Improvement
- [ ] Claude reads own memory before each script → applies learnings
- [ ] Topic selection fully autonomous (trending + channel gap analysis)
- [ ] Thumbnail A/B testing
- [ ] Auto-adjust publish times based on analytics
- [ ] Cost dashboard

## Cost Tracking (Actuals — updated 2026-02-28)
| Item | Estimated | Actual |
|---|---|---|
| Claude API (script gen) | ~$0.10–0.30 | ~$0.06/script |
| Claude vision (clip review) | not estimated | ~$0.61/video |
| ElevenLabs TTS | ~$0.10–0.30 | ~$2.20–2.52/video |
| Pexels/Pixabay footage | Free tier | $0.00 |
| DALL-E 3 thumbnail | ~$0.04 | $0.04 (not yet in regular use) |
| YouTube API | Free | $0.00 |
| **Total per video (actual)** | **~$0.25–0.65** | **~$2.87** |
| **Per week (2 videos)** | **~$0.50–1.30** | **~$5.74** |

*ElevenLabs dominates cost (~76%). Vision review second (~21%). Script gen is negligible.*
*Full cost log in ACTIVITY_LOG.md.*

## Key Decisions Log
| Date | Decision | Reason |
|---|---|---|
| 2026-02-21 | Python over Node.js | Broader ML/media library ecosystem |
| 2026-02-21 | ffmpeg over CapCut | CapCut has no API; ffmpeg is scriptable |
| 2026-02-21 | Start at 2 videos/week | Cost and quality validation before scaling |
| 2026-02-21 | Pre-built ElevenLabs voice | Consistent channel identity, no clone needed |
| 2026-02-22 | Kling AI tested and dropped | 5s clips loop visibly, ~5 min/clip, content moderation blocks politicians — not viable at 2x/week cadence |
| 2026-02-22 | Abstract/symbolic keywords instead of literal | "chess kings dark board" beats "Trump Xi Putin" — Pexels can match it, Kling won't block it |
| 2026-02-22 | Background music at 8% volume | Adds cinematic weight without competing with voiceover |
| 2026-02-23 | OAuth → "Epic Playlists" for @PredictiveEchoes | Brand account routing — must select brand name (old: Epic Playlists) not personal account during OAuth |
