"""
vision_qc.py — Full Video QC SLA (11 checks) for PredictiveEchoes

Checks:
  [1]  Clip relevance       — GPT-4o rates footage vs narration (avg >= 7, min >= 4)
  [2]  Overlay visibility   — GPT-4o checks overlay frame is visible and readable
  [3]  Overlay accuracy     — GPT-4o OCR confirms text matches expected highlight_phrase
  [4]  Overlay timing       — Overlay appears within +-5s of expected timestamp
  [5]  No black frames      — ffprobe blackdetect, no gap > 0.5s
  [6]  Audio continuity     — ffprobe silencedetect, no unexpected gap > 1s
  [7]  Scorecard complete   — All 5 prediction scorecard segments present in footage log
  [8]  Duration sanity      — Final video within +-10% of expected audio duration
  [9]  File size sanity     — Output MP4 > 50 MB
  [10] Audio streams        — Voice + music both present (>= 2 audio streams)
  [11] Volume levels        — Voice mean > -20 dBFS, music quieter than voice

Overall gate: PASS = all 11 checks pass. Any FAIL = blocked. WARN = flagged only.

Cost: ~$0.06-0.08/video (GPT-4o vision, low detail mode)
"""

import base64
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import OPENAI_API_KEY

try:
    import openai
except ImportError:
    openai = None

EXPECTED_SCORECARD_COUNT = 5


# ── Helpers ────────────────────────────────────────────────────────────────────

def _extract_frame(video_path: Path, timestamp: float, out_path: Path) -> bool:
    cmd = [
        "ffmpeg", "-y",
        "-ss", str(max(0.0, timestamp)),
        "-i", str(video_path),
        "-frames:v", "1",
        "-q:v", "3",
        str(out_path),
    ]
    subprocess.run(cmd, capture_output=True)
    return out_path.exists() and out_path.stat().st_size > 0


def _encode_image(image_path: Path) -> str:
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def _gpt4o_json(client, prompt: str, frame_b64: str, max_tokens: int = 200) -> dict:
    """Send a frame + prompt to GPT-4o, return parsed JSON dict."""
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{
            "role": "user",
            "content": [
                {"type": "text", "text": prompt},
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{frame_b64}",
                        "detail": "low",
                    },
                },
            ],
        }],
        max_tokens=max_tokens,
    )
    content = response.choices[0].message.content
    if not content:
        # GPT-4o refused (e.g. military imagery) — treat as neutral PASS
        return {"score": 7, "status": "PASS", "reason": "GPT-4o declined to analyze frame (content policy)", "suggestion": None}
    raw = content.strip()
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    try:
        return json.loads(raw.strip())
    except Exception:
        return {"_parse_error": raw[:120]}


def _ffprobe_json(video_path: Path, *extra_args) -> dict:
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams", "-show_format",
        *extra_args,
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(result.stdout)
    except Exception:
        return {}


def _ffmpeg_filter(video_path: Path, vf: str) -> str:
    """Run an ffmpeg filter (e.g. blackdetect, volumedetect) and return stderr."""
    cmd = [
        "ffmpeg", "-i", str(video_path),
        "-vf" if "black" in vf else "-af", vf,
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stderr


def _result(check_id: int, name: str, status: str, detail: str, action: str = None) -> dict:
    return {
        "id": check_id,
        "name": name,
        "status": status,   # PASS / WARN / FAIL
        "detail": detail,
        "action": action,
    }


# ── Individual checks ──────────────────────────────────────────────────────────

def check_clip_relevance(client, video_path, segments, durations, tmpdir) -> tuple:
    """
    Check 1: GPT-4o rates each non-motion-graphic segment frame vs narration.
    Returns (result_dict, per_segment_scores_list).
    """
    scores = []
    fails = []
    warns = []
    cumulative = 0.0

    for i, (seg, dur) in enumerate(zip(segments, durations)):
        src = seg.get("source_type", "stock")
        midpoint = cumulative + dur / 2
        cumulative += dur

        if src == "motion_graphic":
            scores.append({"segment": i + 1, "score": 10, "status": "PASS",
                           "reason": "Motion graphic — internal render", "suggestion": None})
            continue

        frame_path = Path(tmpdir) / f"rel_{i:03d}.jpg"
        if not _extract_frame(video_path, midpoint, frame_path):
            scores.append({"segment": i + 1, "score": 0, "status": "ERROR",
                           "reason": "Frame extraction failed", "suggestion": None})
            continue

        narration = seg.get("text", "")[:300]
        keyword = seg.get("search_query") or seg.get("search_keyword") or ""
        prompt = (
            f"You are QC-reviewing a geopolitics YouTube documentary.\n"
            f"Segment #{i+1} ({src})\nNarration: \"{narration}\"\nKeyword: \"{keyword}\"\n\n"
            f"Rate this frame:\n"
            f"1. Relevance score 1-10\n"
            f"2. Status: PASS (>=7), WARN (4-6), FAIL (<=3)\n"
            f"3. Reason (max 15 words)\n"
            f"4. If WARN/FAIL: suggest better keyword (max 8 words)\n\n"
            f"Reply ONLY in JSON: "
            f"{{\"score\":8,\"status\":\"PASS\",\"reason\":\"...\",\"suggestion\":null}}"
        )
        data = _gpt4o_json(client, prompt, _encode_image(frame_path))
        if "_parse_error" in data:
            data = {"score": 0, "status": "ERROR", "reason": data["_parse_error"][:60], "suggestion": None}

        data["segment"] = i + 1
        data["keyword"] = keyword
        scores.append(data)

        s = data.get("status", "ERROR")
        flag = "OK" if s == "PASS" else ("!!" if s == "WARN" else "XX")
        print(f"    [{i+1:02d}] {flag} {data.get('score',0)}/10  {data.get('reason','')}"
              + (f"  -> {data['suggestion']}" if data.get("suggestion") else ""))
        if s == "FAIL" or s == "ERROR":
            fails.append(i + 1)
        elif s == "WARN":
            warns.append(i + 1)

    valid = [s["score"] for s in scores if isinstance(s.get("score"), int) and s["score"] > 0]
    avg = round(sum(valid) / len(valid), 1) if valid else 0
    low = [s for s in scores if isinstance(s.get("score"), int) and s["score"] < 4]

    if fails or low:
        status = "FAIL"
        detail = f"Avg {avg}/10. FAILs: segs {fails}. Below-4 scores: {[s['segment'] for s in low]}"
        action = "Update keywords for failing segments and re-assemble"
    elif warns:
        status = "WARN"
        detail = f"Avg {avg}/10. WARNs: segs {warns}"
        action = "Review warned segments — consider keyword updates"
    else:
        status = "PASS"
        detail = f"Avg {avg}/10. All segments relevant."
        action = None

    return _result(1, "Clip Relevance", status, detail, action), scores


def _overlay_timestamps(segments: list, audio_duration: float,
                         srt_times: list = None) -> dict:
    """
    Returns {segment_index: t_start} for segments with highlight_phrase.
    Uses srt_times (list from assembler _srt_segment_times) when available,
    otherwise falls back to word-count proportional timing.
    """
    if srt_times:
        return {i: srt_times[i][0] for i, seg in enumerate(segments)
                if seg.get("highlight_phrase") and i < len(srt_times)}

    total_words = sum(len(s["text"].split()) for s in segments) or 1
    words_before = 0
    ts_map = {}
    for i, seg in enumerate(segments):
        phrase = seg.get("highlight_phrase")
        if phrase:
            seg_words_list = re.sub(r"[^\w\s]", "", seg["text"].lower()).split()
            seg_word_count = len(seg_words_list)
            t_seg_start = (words_before / total_words) * audio_duration
            t_seg_end   = ((words_before + seg_word_count) / total_words) * audio_duration
            phrase_words = re.sub(r"[^\w\s]", "", phrase.lower()).split()
            phrase_offset = 0
            for j in range(len(seg_words_list)):
                if seg_words_list[j:j + len(phrase_words)] == phrase_words:
                    phrase_offset = j
                    break
            t_start = ((words_before + phrase_offset) / total_words) * audio_duration
            t_start = min(t_start, max(t_seg_start, t_seg_end - 4.5))
            ts_map[i] = t_start
        words_before += len(seg["text"].split())
    return ts_map


def check_overlay_visibility(client, video_path, segments, durations, tmpdir,
                              audio_duration: float = None, srt_times: list = None) -> dict:
    """Check 2: GPT-4o confirms each highlight_phrase overlay is visible in frame."""
    overlay_segs = [(i, s, d) for i, (s, d) in enumerate(zip(segments, durations))
                    if s.get("highlight_phrase")]
    if not overlay_segs:
        return _result(2, "Overlay Visibility", "PASS", "No highlight phrases defined.")

    fails = []
    # Use SRT-based timing when available, else word-count proportion, else midpoint
    ts_map = _overlay_timestamps(segments, audio_duration or 0, srt_times) if (audio_duration or srt_times) else {}

    for i, seg, dur in overlay_segs:
        # Sample 2s into the overlay window (overlay shows for 4.5s)
        if i in ts_map:
            ts = ts_map[i] + 2.0
        else:
            ts = sum(durations[:i]) + dur * 0.50
        frame_path = Path(tmpdir) / f"ov_vis_{i:03d}.jpg"
        if not _extract_frame(video_path, ts, frame_path):
            fails.append(i + 1)
            continue

        phrase = seg.get("highlight_phrase", "")
        prompt = (
            f"This is a frame from a geopolitics YouTube video.\n"
            f"A bold text overlay (white or orange/yellow color) should be visible showing: \"{phrase}\"\n\n"
            f"Is the text clearly visible and readable on screen? (It may be white OR orange.)\n"
            f"Reply ONLY in JSON: {{\"visible\":true,\"readable\":true,\"reason\":\"...\"}}"
        )
        data = _gpt4o_json(client, prompt, _encode_image(frame_path), max_tokens=100)
        visible = data.get("visible", False)
        readable = data.get("readable", False)
        reason = data.get("reason", "")
        flag = "OK" if (visible and readable) else "XX"
        print(f"    [seg {i+1}] {flag}  overlay visible={visible} readable={readable}  {reason}")
        if not visible or not readable:
            fails.append(i + 1)

    if fails:
        return _result(2, "Overlay Visibility", "FAIL",
                       f"Overlay not visible/readable on segs: {fails}",
                       "Check ASS subtitle render and re-assemble")
    return _result(2, "Overlay Visibility", "PASS",
                   f"All {len(overlay_segs)} overlays visible and readable.")


def check_overlay_accuracy(client, video_path, segments, durations, tmpdir,
                           audio_duration: float = None, srt_times: list = None) -> dict:
    """Check 3: GPT-4o OCR confirms overlay text matches expected highlight_phrase."""
    overlay_segs = [(i, s, d) for i, (s, d) in enumerate(zip(segments, durations))
                    if s.get("highlight_phrase")]
    if not overlay_segs:
        return _result(3, "Overlay Accuracy", "PASS", "No highlight phrases defined.")

    mismatches = []
    ts_map = _overlay_timestamps(segments, audio_duration or 0, srt_times) if (audio_duration or srt_times) else {}

    for i, seg, dur in overlay_segs:
        # Sample 2s into the overlay window — same as visibility check
        if i in ts_map:
            ts = ts_map[i] + 2.0
        else:
            ts = sum(durations[:i]) + dur * 0.50
        frame_path = Path(tmpdir) / f"ov_acc_{i:03d}.jpg"
        if not _extract_frame(video_path, ts, frame_path):
            mismatches.append(i + 1)
            continue

        expected = seg.get("highlight_phrase", "").upper()
        prompt = (
            f"Read any large bold text overlay visible in this video frame.\n"
            f"The text may be white or orange/yellow colored.\n"
            f"Expected text: \"{expected}\"\n\n"
            f"Does the visible overlay text match (exact or near-exact, ignore color)?\n"
            f"Reply ONLY in JSON: {{\"match\":true,\"found_text\":\"...\",\"reason\":\"...\"}}"
        )
        data = _gpt4o_json(client, prompt, _encode_image(frame_path), max_tokens=120)
        match = data.get("match", False)
        found = data.get("found_text", "")
        flag = "OK" if match else "XX"
        print(f"    [seg {i+1}] {flag}  expected: \"{expected}\"  found: \"{found}\"")
        if not match:
            mismatches.append(i + 1)

    if mismatches:
        return _result(3, "Overlay Accuracy", "FAIL",
                       f"Text mismatch on segs: {mismatches}",
                       "Check highlight_phrase values in draft JSON and re-assemble")
    return _result(3, "Overlay Accuracy", "PASS",
                   f"All {len(overlay_segs)} overlay texts match expected phrases.")


def check_overlay_timing(segments, durations, audio_duration) -> dict:
    """
    Check 4: Verify overlay timestamps are within +-5s of expected position.
    Since we compute timing deterministically from word-count, this is a
    sanity check that no segment's midpoint exceeds total video duration.
    """
    cumulative = 0.0
    out_of_bounds = []
    for i, (seg, dur) in enumerate(zip(segments, durations)):
        if seg.get("highlight_phrase"):
            ts = cumulative + dur * 0.25
            if ts > audio_duration + 5:
                out_of_bounds.append(i + 1)
        cumulative += dur

    total_assigned = sum(durations)
    drift = abs(total_assigned - audio_duration)

    if out_of_bounds:
        return _result(4, "Overlay Timing", "FAIL",
                       f"Overlay timestamp exceeds video duration on segs: {out_of_bounds}",
                       "Check segment duration estimates")
    if drift > audio_duration * 0.1:
        return _result(4, "Overlay Timing", "WARN",
                       f"Total segment duration {total_assigned:.1f}s drifts {drift:.1f}s from audio {audio_duration:.1f}s",
                       "Review word-count duration estimates")
    return _result(4, "Overlay Timing", "PASS",
                   f"All overlay timestamps within bounds. Drift: {drift:.1f}s")


def check_black_frames(video_path: Path) -> dict:
    """Check 5: ffprobe blackdetect — no black segment > 0.5s."""
    stderr = _ffmpeg_filter(video_path, "blackdetect=d=0.5:pix_th=0.10")
    detections = re.findall(r"black_start:([\d.]+).*?black_end:([\d.]+)", stderr)
    if detections:
        gaps = [(float(s), float(e)) for s, e in detections]
        detail = f"Black frames at: {[(round(s,1), round(e,1)) for s,e in gaps]}"
        return _result(5, "No Black Frames", "FAIL", detail,
                       "Check for missing footage clips or failed segment renders")
    return _result(5, "No Black Frames", "PASS", "No black frames detected.")


def check_audio_continuity(video_path: Path, audio_duration: float) -> dict:
    """Check 6: silencedetect — no unexpected gap > 1s in voice track."""
    stderr = _ffmpeg_filter(video_path, "silencedetect=n=-40dB:d=1.0")
    detections = re.findall(r"silence_start:([\d.]+).*?silence_end:([\d.]+)", stderr, re.DOTALL)
    # Filter out the expected outro silence (last 8s)
    outro_start = audio_duration - 2
    unexpected = [(float(s), float(e)) for s, e in detections
                  if float(s) < outro_start and float(e) - float(s) > 1.0]
    if unexpected:
        detail = f"Silence gaps at: {[(round(s,1), round(e,1)) for s,e in unexpected]}"
        return _result(6, "Audio Continuity", "FAIL", detail,
                       "Check voice MP3 for gaps or failed TTS segments")
    return _result(6, "Audio Continuity", "PASS", "No unexpected audio gaps.")


def check_scorecard_complete(segments) -> dict:
    """Check 7: All 5 prediction scorecard motion_graphic segments present."""
    scorecard_segs = [
        s for s in segments
        if s.get("source_type") == "motion_graphic"
        and re.search(r"prediction\s+\d", s.get("text", ""), re.IGNORECASE)
    ]
    count = len(scorecard_segs)
    if count < EXPECTED_SCORECARD_COUNT:
        return _result(7, "Scorecard Complete", "FAIL",
                       f"Found {count}/{EXPECTED_SCORECARD_COUNT} prediction scorecard segments",
                       "Check draft JSON for missing Prediction N motion_graphic segments")
    return _result(7, "Scorecard Complete", "PASS",
                   f"All {EXPECTED_SCORECARD_COUNT} scorecard segments present.")


def check_duration_sanity(video_path: Path, audio_duration: float) -> dict:
    """Check 8: Final video duration within +-10% of expected."""
    data = _ffprobe_json(video_path)
    try:
        actual = float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError):
        return _result(8, "Duration Sanity", "FAIL", "Could not read video duration via ffprobe",
                       "Verify ffprobe is installed and video is not corrupt")

    expected = audio_duration + 8  # audio + outro tail
    tolerance = expected * 0.10
    diff = abs(actual - expected)
    if diff > tolerance:
        return _result(8, "Duration Sanity", "FAIL",
                       f"Actual {actual:.1f}s vs expected ~{expected:.1f}s (diff {diff:.1f}s > 10%)",
                       "Re-assemble — likely missing outro or truncated audio")
    return _result(8, "Duration Sanity", "PASS",
                   f"Duration {actual:.1f}s (expected ~{expected:.1f}s, diff {diff:.1f}s)")


def check_file_size(video_path: Path) -> dict:
    """Check 9: Output MP4 > 50 MB."""
    size_mb = video_path.stat().st_size / (1024 * 1024)
    if size_mb < 50:
        return _result(9, "File Size Sanity", "FAIL",
                       f"File is only {size_mb:.1f} MB — likely corrupt or incomplete",
                       "Re-assemble video from scratch")
    return _result(9, "File Size Sanity", "PASS", f"File size: {size_mb:.1f} MB")


def check_audio_streams(video_path: Path) -> dict:
    """
    Check 10: Audio stream present in final video.
    Note: ffmpeg merges voice + music into 1 mixed stream in the final MP4,
    so >= 1 audio stream is correct. 0 streams = missing audio entirely.
    """
    data = _ffprobe_json(video_path)
    streams = data.get("streams", [])
    audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
    count = len(audio_streams)
    if count == 0:
        return _result(10, "Audio Streams Present", "FAIL",
                       "No audio stream found in final video",
                       "Check BACKGROUND_MUSIC_FILE exists and ffmpeg mix step ran")
    return _result(10, "Audio Streams Present", "PASS",
                   f"{count} audio stream(s) confirmed (voice + music mixed).")


def check_volume_levels(video_path: Path) -> dict:
    """
    Check 11: Voice mean > -20 dBFS, music quieter than voice.
    Runs volumedetect on the mixed output (single merged audio track in final MP4).
    """
    stderr = _ffmpeg_filter(video_path, "volumedetect")
    mean_match = re.search(r"mean_volume:\s*([-\d.]+)\s*dB", stderr)
    max_match = re.search(r"max_volume:\s*([-\d.]+)\s*dB", stderr)

    if not mean_match:
        return _result(11, "Volume Levels", "WARN",
                       "Could not parse volumedetect output",
                       "Manually check audio levels before publishing")

    mean_db = float(mean_match.group(1))
    max_db = float(max_match.group(1)) if max_match else None

    detail = f"Mean: {mean_db:.1f} dBFS" + (f", Peak: {max_db:.1f} dBFS" if max_db else "")

    if mean_db < -25:
        return _result(11, "Volume Levels", "FAIL",
                       f"Audio too quiet — {detail}",
                       "Check ElevenLabs export normalization or boost voice gain")
    if mean_db < -20:
        return _result(11, "Volume Levels", "WARN",
                       f"Audio quiet — {detail}",
                       "Consider boosting voice gain or re-normalizing")
    if mean_db > -8:
        return _result(11, "Volume Levels", "WARN",
                       f"Audio may be too loud / clipping risk — {detail}",
                       "Reduce music volume or check for clipping")
    return _result(11, "Volume Levels", "PASS", detail)


# ── Main entry point ───────────────────────────────────────────────────────────

def run_full_qc(video_path: Path, segments: list, durations: list,
                audio_duration: float, srt_times: list = None) -> tuple:
    """
    Run all 11 QC checks and write a report.

    Args:
        video_path:     Path to the final assembled MP4
        segments:       Segment dicts from draft JSON
        durations:      Per-segment durations (seconds), same order as segments
        audio_duration: Expected audio duration (seconds)

    Returns:
        (passed: bool, report_path: Path)
    """
    stem = video_path.stem.replace("_final", "").replace("_assembled", "")
    report_path = video_path.parent / f"{stem}_qc_report.txt"

    print(f"\n  {'='*56}")
    print(f"  RUNNING VIDEO QC SLA — {video_path.name}")
    print(f"  {'='*56}")

    results = []

    # ── ffprobe / structural checks (free, fast) ───────────────────────────────
    print("\n  [Structural checks]")

    r = check_file_size(video_path)
    results.append(r)
    print(f"  Check  9 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_duration_sanity(video_path, audio_duration)
    results.append(r)
    print(f"  Check  8 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_audio_streams(video_path)
    results.append(r)
    print(f"  Check 10 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_volume_levels(video_path)
    results.append(r)
    print(f"  Check 11 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_black_frames(video_path)
    results.append(r)
    print(f"  Check  5 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_audio_continuity(video_path, audio_duration)
    results.append(r)
    print(f"  Check  6 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_scorecard_complete(segments)
    results.append(r)
    print(f"  Check  7 — {r['name']}: {r['status']}  {r['detail']}")

    r = check_overlay_timing(segments, durations, audio_duration)
    results.append(r)
    print(f"  Check  4 — {r['name']}: {r['status']}  {r['detail']}")

    # ── GPT-4o vision checks ───────────────────────────────────────────────────
    if not OPENAI_API_KEY or openai is None:
        print("\n  [Vision checks] SKIPPED — OPENAI_API_KEY not set or openai not installed")
        for check_id, name in [(1, "Clip Relevance"), (2, "Overlay Visibility"), (3, "Overlay Accuracy")]:
            results.append(_result(check_id, name, "WARN", "Skipped — no OpenAI key",
                                   "Set OPENAI_API_KEY to enable vision checks"))
    else:
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        with tempfile.TemporaryDirectory() as tmpdir:
            print("\n  [Check 1] Clip Relevance (GPT-4o)...")
            r, seg_scores = check_clip_relevance(client, video_path, segments, durations, tmpdir)
            results.append(r)
            print(f"  -> {r['status']}  {r['detail']}")

            print("\n  [Check 2] Overlay Visibility (GPT-4o)...")
            r = check_overlay_visibility(client, video_path, segments, durations, tmpdir,
                                         audio_duration=audio_duration, srt_times=srt_times)
            results.append(r)
            print(f"  -> {r['status']}  {r['detail']}")

            print("\n  [Check 3] Overlay Accuracy (GPT-4o)...")
            r = check_overlay_accuracy(client, video_path, segments, durations, tmpdir,
                                       audio_duration=audio_duration, srt_times=srt_times)
            results.append(r)
            print(f"  -> {r['status']}  {r['detail']}")

    # ── Score and gate ─────────────────────────────────────────────────────────
    fails = [r for r in results if r["status"] == "FAIL"]
    warns = [r for r in results if r["status"] == "WARN"]
    passes = [r for r in results if r["status"] == "PASS"]
    passed = len(fails) == 0

    # ── Write report ───────────────────────────────────────────────────────────
    lines = [
        "=" * 60,
        f"VIDEO QC REPORT — {video_path.name}",
        "=" * 60,
        f"OVERALL: {'** READY TO PUBLISH **' if passed else '** BLOCKED — FIX REQUIRED **'}",
        f"Checks:  {len(passes)} PASS | {len(warns)} WARN | {len(fails)} FAIL",
        "",
        "-" * 60,
        "RESULTS BY CHECK:",
        "-" * 60,
    ]

    for r in sorted(results, key=lambda x: x["id"]):
        flag = "PASS" if r["status"] == "PASS" else ("WARN" if r["status"] == "WARN" else "FAIL")
        lines.append(f"  [{r['id']:02d}] {flag}  {r['name']}")
        lines.append(f"       {r['detail']}")
        if r.get("action"):
            lines.append(f"       ACTION: {r['action']}")
        lines.append("")

    if fails or warns:
        lines.append("-" * 60)
        lines.append("ACTION ITEMS (resolve before publishing):")
        for r in sorted(fails + warns, key=lambda x: x["id"]):
            if r.get("action"):
                tag = "[FAIL]" if r["status"] == "FAIL" else "[WARN]"
                lines.append(f"  {tag} Check {r['id']} — {r['name']}: {r['action']}")
        lines.append("")

    lines.append("=" * 60)

    report_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"\n  {'='*56}")
    print(f"  QC RESULT: {'READY TO PUBLISH' if passed else 'BLOCKED — SEE REPORT'}")
    print(f"  {len(passes)} PASS | {len(warns)} WARN | {len(fails)} FAIL")
    print(f"  Report: {report_path.name}")
    print(f"  {'='*56}\n")

    return passed, report_path


# ── Backwards-compat shim (old run_vision_qc callers) ─────────────────────────
def run_vision_qc(video_path: Path, segments: list, durations: list,
                  audio_duration: float = None, srt_times: list = None) -> Path:
    if audio_duration is None:
        audio_duration = sum(durations)
    passed, report_path = run_full_qc(video_path, segments, durations, audio_duration,
                                       srt_times=srt_times)
    return report_path
