"""
Agent44 — Autonomous YouTube pipeline orchestrator.
Drives the PredictiveEchoes video production pipeline end-to-end.

Modes (determined automatically by day of week):
  Publish day (Tue/Fri) : full pipeline run
  Other days            : lightweight monitoring + analytics

Trigger: Windows Task Scheduler, daily at 8:00 AM.
"""

import json
import logging
import subprocess
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

from config.settings import (
    CHANNEL, RETRY_BACKOFF, MAX_RETRIES, MAX_FOOTAGE_RERUNS,
    ANALYTICS_DELAY_HOURS, ESTIMATED_COST_PER_RUN, PREDICTIVE_ECHOES_ROOT,
    PE_SCRIPTS, PE_OUTPUTS, LOG_FILE, DB_PATH,
)
from state.db import (
    init_db, create_run, checkpoint, get_run, get_incomplete_run,
    fail_run, complete_run, save_analytics, get_analytics_history,
    get_past_topics,
)
from telegram_gate import (
    notify, send_spend_gate, send_publish_gate, wait_for_approval,
)
from ideator import propose_topic
from researcher import research
from seo_generator import generate as generate_seo

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

CHANNEL_NAME = CHANNEL["name"]
PUBLISH_DAYS = {"Tuesday": 1, "Friday": 4}  # weekday() values


# ── Helpers ────────────────────────────────────────────────────────────────────

def is_publish_day() -> bool:
    return datetime.now().weekday() in PUBLISH_DAYS.values()


def run_step(step_name: str, fn, *args, **kwargs):
    """
    Call fn(*args, **kwargs) with up to MAX_RETRIES attempts.
    Exponential backoff between attempts.
    Raises the last exception if all retries are exhausted.
    """
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as e:
            last_exc = e
            if attempt < MAX_RETRIES:
                wait = RETRY_BACKOFF[attempt - 1]
                logger.warning(f"[{step_name}] attempt {attempt} failed: {e} — retrying in {wait}s")
                time.sleep(wait)
            else:
                logger.error(f"[{step_name}] all {MAX_RETRIES} attempts failed: {e}")
    raise last_exc


def _run_script(script_rel_path: str, args: list) -> subprocess.CompletedProcess:
    """Run a PredictiveEchoes script via subprocess. Raises on non-zero exit."""
    script = PE_SCRIPTS / script_rel_path
    cmd = [sys.executable, str(script)] + args
    result = subprocess.run(cmd, cwd=str(PREDICTIVE_ECHOES_ROOT), capture_output=True, text=True)
    if result.stdout:
        logger.info(f"[{script_rel_path}] {result.stdout.strip()}")
    if result.returncode != 0:
        if result.stderr:
            logger.error(f"[{script_rel_path}] stderr: {result.stderr.strip()}")
        raise RuntimeError(f"{script_rel_path} exited with code {result.returncode}")
    return result


def _latest_draft() -> Path:
    """Return the most recently modified draft JSON in PE outputs."""
    drafts = sorted(PE_OUTPUTS.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No draft JSON found in {PE_OUTPUTS}")
    return drafts[0]


def _read_draft(path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def _write_draft(path, data: dict):
    Path(path).write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Pipeline step wrappers ─────────────────────────────────────────────────────

def run_script_generator(topic: str, facts_bundle: dict) -> str:
    """Run script_generator.py and return path to produced draft JSON."""
    import tempfile
    with tempfile.NamedTemporaryFile(
        mode="w", suffix="_facts.json", delete=False, encoding="utf-8"
    ) as fh:
        json.dump(facts_bundle, fh)
        facts_path = fh.name
    try:
        _run_script("generators/script_generator.py", [
            "--topic", topic,
            "--facts", facts_path,
        ])
    finally:
        Path(facts_path).unlink(missing_ok=True)
    return str(_latest_draft())


def run_voice_generator(draft_path: str):
    _run_script("generators/voice_generator.py", ["--draft", draft_path])


def run_footage_pipeline(draft_path: str):
    _run_script("assembler/footage_finder.py", ["--draft", draft_path])


def run_video_assembler(draft_path: str):
    _run_script("assembler/video_assembler.py", ["--draft", draft_path])


def run_uploader(draft_path: str) -> str:
    """Upload video, captions, thumbnail; set public. Returns video_id."""
    sys.path.insert(0, str(PREDICTIVE_ECHOES_ROOT))
    from scripts.uploader.youtube_uploader import (
        get_authenticated_service, upload_caption, upload_thumbnail, set_public,
    )

    # Upload video (private) via existing CLI script
    _run_script("uploader/youtube_uploader.py", ["--draft", draft_path])
    draft = _read_draft(draft_path)  # re-read after upload writes video_id
    video_id = draft.get("_upload", {}).get("video_id", "")
    if not video_id:
        raise RuntimeError("Upload completed but no video_id found in draft JSON")

    youtube = get_authenticated_service()

    srt_path = draft.get("_audio", {}).get("srt_path", "")
    if srt_path and Path(srt_path).exists():
        if not upload_caption(youtube, video_id, srt_path):
            logger.warning(f"Caption upload failed for {video_id} — continuing")

    thumb_path = draft.get("_video", {}).get("thumbnail_path", "")
    if thumb_path and Path(thumb_path).exists():
        if not upload_thumbnail(youtube, video_id, thumb_path):
            logger.warning(f"Thumbnail upload failed for {video_id} — continuing")

    if not set_public(youtube, video_id):
        raise RuntimeError(f"set_public failed for {video_id}")

    return video_id


# ── Analytics ──────────────────────────────────────────────────────────────────

def pull_analytics_if_due(video_id: str) -> dict:
    """Run analytics_reader.py for video_id. Returns parsed metrics or None."""
    try:
        result = subprocess.run(
            [sys.executable, str(PE_SCRIPTS / "analytics/analytics_reader.py"),
             "--video-id", video_id, "--json-out"],
            cwd=str(PREDICTIVE_ECHOES_ROOT),
            capture_output=True, text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
    except Exception as e:
        logger.warning(f"Analytics pull failed for {video_id}: {e}")
    return None


# ── Monitoring mode ────────────────────────────────────────────────────────────

def run_monitoring_mode(channel: str):
    """Non-publish day: pull pending analytics, check sources."""
    logger.info("Monitoring mode — non-publish day")
    from state.db import get_conn

    deadline = datetime.utcnow() - timedelta(hours=ANALYTICS_DELAY_HOURS)

    with get_conn() as conn:
        rows = conn.execute(
            """SELECT r.id, r.video_id, r.updated_at FROM runs r
               LEFT JOIN analytics a ON a.run_id = r.id
               WHERE r.channel=? AND r.status='completed'
               AND r.video_id IS NOT NULL AND a.id IS NULL""",
            (channel,),
        ).fetchall()

    for row in rows:
        published_at = datetime.fromisoformat(row["updated_at"])
        if published_at <= deadline:
            metrics = pull_analytics_if_due(row["video_id"])
            if metrics:
                save_analytics(
                    row["id"], row["video_id"],
                    views=metrics.get("views", 0),
                    ctr=metrics.get("ctr", 0.0),
                    retention=metrics.get("retention", 0.0),
                    subs_gained=metrics.get("subs_gained", 0),
                )
                notify(
                    f"*Analytics — Video {row['video_id']}*\n"
                    f"Views: {metrics.get('views', 0)} | "
                    f"CTR: {metrics.get('ctr', 0):.1%} | "
                    f"Retention: {metrics.get('retention', 0):.1%}"
                )
                logger.info(f"Analytics saved for {row['video_id']}")


# ── Publish pipeline ───────────────────────────────────────────────────────────

def run_publish_pipeline(channel: str) -> int:
    """
    Full video production + publish pipeline.
    Returns run_id of the completed run.
    """
    logger.info(f"Starting publish pipeline for {channel}")

    # ── Resume incomplete run or start fresh ──────────────────────────────────
    run = get_incomplete_run(channel)
    if run:
        logger.info(f"Resuming run #{run['id']} from step: {run['current_step']}")
        run_id = run["id"]
        draft_path = run.get("draft_json_path") or ""
    else:
        run_id = None
        draft_path = ""

    analytics_history = get_analytics_history(channel, limit=10)

    # ── IDEATOR ───────────────────────────────────────────────────────────────
    if not run_id or run["current_step"] is None:
        proposal = run_step("ideator", propose_topic, channel)
        topic = proposal["topic"]
        angle = proposal["angle"]
        source_urls = proposal["source_urls"]

        run_id = create_run(channel, topic, angle, source_urls, ESTIMATED_COST_PER_RUN)
        checkpoint(run_id, "ideator", "")
        logger.info(f"Run #{run_id} created. Topic: {topic}")
    else:
        run = get_run(run_id)
        topic = run["topic"]
        angle = run["angle"]
        source_urls = json.loads(run["source_urls"])

    # ── SPEND GATE ────────────────────────────────────────────────────────────
    run = get_run(run_id)
    if run["current_step"] in (None, "ideator"):
        msg_id = send_spend_gate(f"{topic} — {angle}", ESTIMATED_COST_PER_RUN)
        decision = wait_for_approval(msg_id, run_id)
        if decision != "approved":
            fail_run(run_id, "spend_gate", f"User {decision} spend approval")
            notify(f"Run #{run_id} cancelled at spend gate ({decision}).")
            logger.info(f"Run #{run_id} cancelled: {decision}")
            return run_id
        checkpoint(run_id, "spend_gate", "")

    # ── RESEARCHER ────────────────────────────────────────────────────────────
    run = get_run(run_id)
    facts_file = DB_PATH.parent / f"facts_{run_id}.json"
    facts_bundle = None
    if run["current_step"] in ("ideator", "spend_gate"):
        facts_bundle = run_step(
            "researcher", research,
            topic=topic, angle=angle, source_urls=source_urls,
        )
        # Persist facts so the script generator can reload them on resume
        facts_file.write_text(json.dumps(facts_bundle), encoding="utf-8")
        checkpoint(run_id, "researcher", "")

    # ── SCRIPT GENERATOR ──────────────────────────────────────────────────────
    run = get_run(run_id)
    if run["current_step"] in ("researcher",):
        if facts_bundle is None:
            # Resuming after a crash between researcher and script_generator
            if facts_file.exists():
                facts_bundle = json.loads(facts_file.read_text(encoding="utf-8"))
            else:
                raise RuntimeError(f"facts file missing for run #{run_id} — cannot resume script generator")
        draft_path = run_step(
            "script_generator", run_script_generator,
            topic=f"{topic} — {angle}",
            facts_bundle=facts_bundle,
        )
        facts_file.unlink(missing_ok=True)  # clean up after successful use
        checkpoint(run_id, "script_generator", draft_path)

    # ── SEO GENERATOR ─────────────────────────────────────────────────────────
    run = get_run(run_id)
    if run["current_step"] in ("script_generator",):
        dp = run["draft_json_path"] or draft_path
        draft = _read_draft(dp)
        seo = run_step("seo_generator", generate_seo, draft=draft, analytics_history=analytics_history)
        draft["_seo"] = seo
        draft["title"] = seo["title"]
        _write_draft(dp, draft)
        checkpoint(run_id, "seo_generator", dp)

    # ── VOICE GENERATOR ───────────────────────────────────────────────────────
    run = get_run(run_id)
    dp = run["draft_json_path"] or draft_path
    if run["current_step"] in ("seo_generator",):
        run_step("voice_generator", run_voice_generator, dp)
        checkpoint(run_id, "voice_generator", dp)

    # ── FOOTAGE + ASSEMBLY ────────────────────────────────────────────────────
    run = get_run(run_id)
    dp = run["draft_json_path"] or draft_path
    if run["current_step"] in ("voice_generator",):
        run_step("footage_pipeline", run_footage_pipeline, dp)
        checkpoint(run_id, "footage_pipeline", dp)

    run = get_run(run_id)
    dp = run["draft_json_path"] or draft_path
    rerun_count = 0
    while True:
        if run["current_step"] in ("footage_pipeline", "rerun_footage"):
            run_step("video_assembler", run_video_assembler, dp)
            checkpoint(run_id, "video_assembler", dp)

        # ── PUBLISH GATE ──────────────────────────────────────────────────────
        run = get_run(run_id)
        dp = run["draft_json_path"] or draft_path
        if run["current_step"] in ("video_assembler",):
            draft = _read_draft(dp)
            studio_url = draft.get("_upload", {}).get("studio_url", "https://studio.youtube.com")
            msg_id = send_publish_gate(draft, studio_url)
            decision = wait_for_approval(msg_id, run_id)

            if decision == "approved":
                break
            elif decision == "rerun" and rerun_count < MAX_FOOTAGE_RERUNS:
                rerun_count += 1
                logger.info(f"Re-running footage (attempt {rerun_count})")
                run_step("footage_pipeline", run_footage_pipeline, dp)
                checkpoint(run_id, "rerun_footage", dp)
                run = get_run(run_id)
            else:
                fail_run(run_id, "publish_gate", f"User {decision} publish approval")
                notify(f"Run #{run_id} cancelled at publish gate ({decision}).")
                return run_id

    # ── UPLOAD ────────────────────────────────────────────────────────────────
    run = get_run(run_id)
    dp = run["draft_json_path"] or draft_path
    if not dp:
        raise RuntimeError(f"draft_json_path is empty for run #{run_id} — cannot upload")
    video_id = run_step("uploader", run_uploader, dp)
    complete_run(run_id, video_id, ESTIMATED_COST_PER_RUN)

    notify(
        f"*Agent44 — Video published!*\n"
        f"Video ID: {video_id}\n"
        f"https://www.youtube.com/watch?v={video_id}"
    )
    logger.info(f"Run #{run_id} complete. Video: {video_id}")
    return run_id


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    init_db()
    channel = CHANNEL_NAME

    if is_publish_day():
        logger.info("Publish day — running full pipeline")
        try:
            run_publish_pipeline(channel)
        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            notify(f"*Agent44 ERROR*\n{e}")
    else:
        run_monitoring_mode(channel)


if __name__ == "__main__":
    main()
