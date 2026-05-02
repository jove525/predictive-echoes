"""
scheduler.py — APScheduler-based pipeline automation
Runs the full pipeline (script → voice → footage → assemble → upload) on a schedule.
Defaults to 2x/week as configured in settings.py (PUBLISH_SCHEDULE).

PIPELINE_MODE in settings.py controls behavior:
  "review" → generates video, uploads as private, waits for manual approval
  "auto"   → generates, uploads, and publishes automatically (use with caution)

Usage:
    python scripts/utils/scheduler.py            # start the scheduler (runs continuously)
    python scripts/utils/scheduler.py --run-now  # trigger one pipeline run immediately
"""

import argparse
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import PUBLISH_SCHEDULE, PIPELINE_MODE, ANALYTICS_REVIEW_HOURS

# ── Pipeline runner ────────────────────────────────────────────────────────────

def run_step(label: str, cmd: list) -> bool:
    """Run a pipeline step as a subprocess. Returns True on success."""
    print(f"\n{'─'*60}")
    print(f"  [{datetime.now().strftime('%H:%M:%S')}] STEP: {label}")
    print(f"{'─'*60}")

    result = subprocess.run(cmd, cwd=str(ROOT))
    if result.returncode != 0:
        print(f"\n  ERROR: '{label}' failed with exit code {result.returncode}")
        return False
    return True


def run_pipeline(topic: str = None):
    """
    Run the full pipeline end-to-end.
    topic: optional topic override. If None, Claude generates its own topic.
    """
    print(f"\n{'='*60}")
    print(f"  PIPELINE START — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"  Mode: {PIPELINE_MODE}")
    print(f"{'='*60}")

    python = sys.executable

    # Step 1 — Generate script
    script_cmd = [python, "scripts/generators/script_generator.py"]
    if topic:
        script_cmd += ["--topic", topic]
    if not run_step("Script generation", script_cmd):
        return False

    # Step 2 — Generate voice
    if not run_step("Voice generation", [python, "scripts/generators/voice_generator.py", "--latest"]):
        return False

    # Step 3 — Find footage + assemble video
    if not run_step("Video assembly", [python, "scripts/assembler/video_assembler.py", "--latest"]):
        return False

    # Step 4 — Upload to YouTube (always as private first)
    if not run_step("YouTube upload", [python, "scripts/uploader/youtube_uploader.py", "--latest"]):
        return False

    print(f"\n{'='*60}")
    print(f"  PIPELINE COMPLETE — {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*60}")

    if PIPELINE_MODE == "review":
        print(f"""
  Video uploaded as PRIVATE. Next steps:
  1. Review in YouTube Studio
  2. Upload SRT captions
  3. Add thumbnail
  4. Change to Public when ready

  Run analytics 72h after publish:
    python scripts/analytics/analytics_reader.py --latest
""")
    elif PIPELINE_MODE == "auto":
        print(f"""
  AUTO MODE: Video uploaded as private.
  Note: Auto-publishing not yet implemented — change to Public manually in YouTube Studio.
  (Full auto-publish requires additional OAuth scope: youtube)
""")

    return True


# ── Scheduler ─────────────────────────────────────────────────────────────────

def start_scheduler():
    try:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger
        import pytz
    except ImportError:
        print("  Error: APScheduler or pytz not installed.")
        print("  Run: pip install apscheduler pytz")
        sys.exit(1)

    days = PUBLISH_SCHEDULE.get("days", ["Tuesday", "Friday"])
    time_str = PUBLISH_SCHEDULE.get("time", "14:00")
    tz_str = PUBLISH_SCHEDULE.get("timezone", "Asia/Manila")

    hour, minute = map(int, time_str.split(":"))
    timezone = pytz.timezone(tz_str)

    # Map day names to APScheduler day_of_week format
    day_map = {
        "Monday": "mon", "Tuesday": "tue", "Wednesday": "wed",
        "Thursday": "thu", "Friday": "fri", "Saturday": "sat", "Sunday": "sun"
    }
    day_of_week = ",".join(day_map[d] for d in days if d in day_map)

    scheduler = BlockingScheduler(timezone=timezone)

    scheduler.add_job(
        run_pipeline,
        trigger=CronTrigger(
            day_of_week=day_of_week,
            hour=hour,
            minute=minute,
            timezone=timezone
        ),
        id="pipeline",
        name="PredictiveEchoes pipeline",
        misfire_grace_time=3600,  # allow up to 1h late start
    )

    print(f"\n{'='*60}")
    print(f"  SCHEDULER STARTED")
    print(f"{'='*60}")
    print(f"  Schedule : {', '.join(days)} at {time_str} {tz_str}")
    print(f"  Mode     : {PIPELINE_MODE}")
    print(f"  Next run : {scheduler.get_jobs()[0].next_run_time}")
    print(f"{'─'*60}")
    print(f"  Press Ctrl+C to stop.")
    print(f"{'='*60}\n")

    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        print("\n  Scheduler stopped.")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="PredictiveEchoes pipeline scheduler")
    parser.add_argument("--run-now", action="store_true", help="Trigger one pipeline run immediately")
    parser.add_argument("--topic", help="Topic override for --run-now")
    args = parser.parse_args()

    if args.run_now:
        run_pipeline(topic=args.topic)
    else:
        start_scheduler()


if __name__ == "__main__":
    main()
