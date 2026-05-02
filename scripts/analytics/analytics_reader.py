"""
analytics_reader.py — YouTube Analytics API reader
Pulls performance stats for a video from the YouTube Analytics API.
Run manually 72h after publish to evaluate video performance.

Usage:
    python scripts/analytics/analytics_reader.py --latest
    python scripts/analytics/analytics_reader.py --draft outputs/drafts/your_draft.json
    python scripts/analytics/analytics_reader.py --video-id i4GzVn8QLKM
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import DRAFTS_DIR, YOUTUBE_CHANNEL_ID

# ── OAuth setup ────────────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/youtube.readonly",
    "https://www.googleapis.com/auth/yt-analytics.readonly",
]
TOKEN_FILE = ROOT / "config" / "youtube_token.json"
CLIENT_SECRET_FILE = ROOT / "config" / "client_secret.json"


def get_authenticated_services():
    """Returns (youtube, youtubeAnalytics) service clients."""
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None
    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing OAuth token...")
            creds.refresh(Request())
        else:
            print("  Opening browser for OAuth authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)
        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print(f"  Token saved to {TOKEN_FILE}")

    youtube = build("youtube", "v3", credentials=creds)
    yt_analytics = build("youtubeAnalytics", "v2", credentials=creds)
    return youtube, yt_analytics


# ── Draft helpers ──────────────────────────────────────────────────────────────

def get_latest_draft() -> Path:
    drafts = sorted(DRAFTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not drafts:
        raise FileNotFoundError(f"No drafts found in {DRAFTS_DIR}")
    return drafts[0]


def load_draft(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def update_draft(path: Path, key: str, value):
    data = load_draft(path)
    data[key] = value
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


# ── Analytics fetchers ─────────────────────────────────────────────────────────

def get_video_details(youtube, video_id: str) -> dict:
    """Pull basic video metadata + public stats from Data API."""
    resp = youtube.videos().list(
        part="snippet,statistics,status",
        id=video_id
    ).execute()

    items = resp.get("items", [])
    if not items:
        print(f"  Warning: Video {video_id} not found or not accessible.")
        return {}

    item = items[0]
    stats = item.get("statistics", {})
    snippet = item.get("snippet", {})

    return {
        "title": snippet.get("title", ""),
        "published_at": snippet.get("publishedAt", ""),
        "privacy_status": item.get("status", {}).get("privacyStatus", ""),
        "views": int(stats.get("viewCount", 0)),
        "likes": int(stats.get("likeCount", 0)),
        "comments": int(stats.get("commentCount", 0)),
        "favorites": int(stats.get("favoriteCount", 0)),
    }


def get_analytics(yt_analytics, video_id: str, published_at: str) -> dict:
    """Pull detailed analytics from YouTube Analytics API."""
    if published_at:
        start_date = published_at[:10]  # YYYY-MM-DD
    else:
        start_date = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d")

    end_date = datetime.utcnow().strftime("%Y-%m-%d")

    try:
        resp = yt_analytics.reports().query(
            ids=f"channel==MINE",
            startDate=start_date,
            endDate=end_date,
            metrics="views,estimatedMinutesWatched,averageViewDuration,averageViewPercentage,subscribersGained,likes,comments,shares",
            dimensions="video",
            filters=f"video=={video_id}",
            sort="-views"
        ).execute()

        rows = resp.get("rows", [])
        if not rows:
            return {}

        row = rows[0]
        headers = [h["name"] for h in resp.get("columnHeaders", [])]
        data = dict(zip(headers, row))

        return {
            "views": int(data.get("views", 0)),
            "estimated_minutes_watched": round(float(data.get("estimatedMinutesWatched", 0)), 1),
            "avg_view_duration_seconds": round(float(data.get("averageViewDuration", 0)), 1),
            "avg_view_percentage": round(float(data.get("averageViewPercentage", 0)), 1),
            "subscribers_gained": int(data.get("subscribersGained", 0)),
            "likes": int(data.get("likes", 0)),
            "comments": int(data.get("comments", 0)),
            "shares": int(data.get("shares", 0)),
        }

    except Exception as e:
        print(f"  Warning: Analytics API error: {e}")
        print("  Note: Analytics data may not be available yet (can take 24-48h after publish).")
        return {}


# ── Report printer ─────────────────────────────────────────────────────────────

def print_report(video_id: str, details: dict, analytics: dict):
    title = details.get("title", video_id)
    published = details.get("published_at", "unknown")
    privacy = details.get("privacy_status", "unknown")

    print(f"\n{'='*60}")
    print(f"  ANALYTICS REPORT")
    print(f"{'='*60}")
    print(f"  Video  : {title[:55]}")
    print(f"  ID     : {video_id}")
    print(f"  Status : {privacy}  |  Published: {published[:10]}")
    print(f"{'-'*60}")

    if not analytics:
        print(f"  No analytics data available yet.")
        print(f"  Try again 24-72h after the video goes public.")
    else:
        views = analytics.get("views", 0)
        avg_pct = analytics.get("avg_view_percentage", 0)
        avg_dur = analytics.get("avg_view_duration_seconds", 0)
        subs = analytics.get("subscribers_gained", 0)
        minutes = analytics.get("estimated_minutes_watched", 0)
        likes = analytics.get("likes", 0)
        comments = analytics.get("comments", 0)
        shares = analytics.get("shares", 0)

        avg_dur_fmt = f"{int(avg_dur // 60)}m {int(avg_dur % 60)}s"

        print(f"  Views              : {views:,}")
        print(f"  Avg view duration  : {avg_dur_fmt} ({avg_pct}% of video)")
        print(f"  Minutes watched    : {minutes:,}")
        print(f"  Subscribers gained : {subs:+}")
        print(f"  Likes              : {likes:,}")
        print(f"  Comments           : {comments:,}")
        print(f"  Shares             : {shares:,}")

        # Simple performance verdict
        print(f"{'-'*60}")
        if views == 0:
            verdict = "No views yet — check back after 72h"
        elif avg_pct >= 50:
            verdict = "Good retention"
        else:
            verdict = "Early - more data needed"
        print(f"  Verdict: {verdict}")

    print(f"{'='*60}\n")


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Pull YouTube analytics for a video")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--latest", action="store_true", help="Use most recent draft")
    group.add_argument("--draft", help="Path to specific draft JSON")
    group.add_argument("--video-id", help="YouTube video ID directly")
    args = parser.parse_args()

    draft_path = None
    video_id = None
    published_at = ""

    if args.video_id:
        video_id = args.video_id
    else:
        draft_path = get_latest_draft() if args.latest else Path(args.draft)
        if args.latest:
            print(f"  Using latest draft: {draft_path.name}")
        data = load_draft(draft_path)
        upload_info = data.get("_upload", {})
        video_id = upload_info.get("video_id")
        if not video_id:
            print("  Error: No video_id found in draft. Run youtube_uploader.py first.")
            sys.exit(1)
        published_at = upload_info.get("uploaded_at", "")

    print(f"\n  Fetching analytics for video: {video_id}")
    print(f"  Authenticating...")

    youtube, yt_analytics = get_authenticated_services()

    details = get_video_details(youtube, video_id)
    if details.get("published_at"):
        published_at = details["published_at"]

    analytics = get_analytics(yt_analytics, video_id, published_at)

    print_report(video_id, details, analytics)

    # Save analytics back to draft if available
    if draft_path and analytics:
        update_draft(draft_path, "_analytics", {
            "pulled_at": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S"),
            **analytics
        })
        print(f"  Analytics saved to draft JSON.")


if __name__ == "__main__":
    main()
