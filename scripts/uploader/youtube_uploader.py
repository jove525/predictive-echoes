"""
youtube_uploader.py — YouTube Data API v3 Uploader
Uploads the assembled video from a draft JSON to YouTube.
Handles OAuth2 token caching — browser auth only required on first run.

Usage:
    python scripts/uploader/youtube_uploader.py --latest
    python scripts/uploader/youtube_uploader.py --draft outputs/drafts/your_draft.json
"""

import argparse
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(ROOT))

from config.settings import (
    YOUTUBE_CLIENT_ID,
    YOUTUBE_CLIENT_SECRET,
    YOUTUBE_CHANNEL_ID,
    DRAFTS_DIR,
)

# ── OAuth + API setup ──────────────────────────────────────────────────────────

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube.readonly",
]
TOKEN_FILE = ROOT / "config" / "youtube_token.json"
CLIENT_SECRET_FILE = ROOT / "config" / "client_secret.json"


def get_authenticated_service():
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from google.auth.transport.requests import Request
    from googleapiclient.discovery import build

    creds = None

    if TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("  Refreshing YouTube OAuth token...")
            creds.refresh(Request())
        else:
            print("  Opening browser for YouTube OAuth authorization...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        TOKEN_FILE.write_text(creds.to_json(), encoding="utf-8")
        print(f"  Token saved to {TOKEN_FILE}")

    return build("youtube", "v3", credentials=creds)


def get_upload_channel(youtube) -> str:
    """
    For brand accounts, the upload goes to whichever channel was selected during
    the OAuth consent screen — not the personal Google Account channel.
    We log which channel the token is for (informational only).
    """
    try:
        resp = youtube.channels().list(part="id,snippet", mine=True).execute()
        items = resp.get("items", [])
        if items:
            ch = items[0]
            print(f"  OAuth token channel: {ch['snippet']['title']} ({ch['id']})")
            if YOUTUBE_CHANNEL_ID and ch["id"] != YOUTUBE_CHANNEL_ID:
                print(f"  Note: Brand account uploads go to the channel selected in the")
                print(f"  OAuth consent screen, not the personal channel shown above.")
    except Exception:
        pass  # Non-fatal — just informational
    return YOUTUBE_CHANNEL_ID or ""


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


# ── Upload ─────────────────────────────────────────────────────────────────────

def upload_video(youtube, video_path: Path, title: str, description: str,
                 tags: list, category_id: str = "25") -> str:
    """
    Upload video to YouTube. Returns video_id.
    category_id 25 = News & Politics (fits geopolitics content)
    """
    from googleapiclient.http import MediaFileUpload

    body = {
        "snippet": {
            "title": title[:100],  # YouTube title limit
            "description": description,
            "tags": tags[:500],    # YouTube tags limit
            "categoryId": category_id,
            "defaultLanguage": "en",
        },
        "status": {
            "privacyStatus": "private",   # Upload as private — review before publishing
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(video_path),
        mimetype="video/mp4",
        resumable=True,
        chunksize=1024 * 1024 * 8,  # 8MB chunks
    )

    print(f"  Uploading: {video_path.name}")
    print(f"  Title    : {title[:80]}")
    print(f"  Status   : private (change to public in YouTube Studio when ready)")
    print()

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    response = None
    while response is None:
        status, response = request.next_chunk()
        if status:
            pct = int(status.progress() * 100)
            print(f"  Uploading... {pct}%", end="\r")

    print()
    video_id = response["id"]
    return video_id


# ── Agent44 extensions ─────────────────────────────────────────────────────────
# NOTE: These functions require 'youtube' (full) scope, which is broader than
# the original 'youtube.upload' + 'youtube.readonly' scopes.
# After adding these functions, delete config/youtube_token.json and re-run
# the uploader once to re-authenticate with the expanded scope.


def upload_caption(video_id: str, srt_path: str, language: str = "en") -> bool:
    """Upload SRT captions to an existing YouTube video. Returns True on success."""
    youtube = get_authenticated_service()
    from googleapiclient.http import MediaFileUpload
    try:
        youtube.captions().insert(
            part="snippet",
            body={
                "snippet": {
                    "videoId": video_id,
                    "language": language,
                    "name": "English",
                    "isDraft": False,
                }
            },
            media_body=MediaFileUpload(srt_path, mimetype="application/octet-stream"),
        ).execute()
        print(f"  Captions uploaded for video {video_id}")
        return True
    except Exception as e:
        print(f"  Caption upload failed: {e}")
        return False


def upload_thumbnail(video_id: str, thumbnail_path: str) -> bool:
    """Upload a thumbnail image to an existing YouTube video. Returns True on success."""
    youtube = get_authenticated_service()
    from googleapiclient.http import MediaFileUpload
    try:
        youtube.thumbnails().set(
            videoId=video_id,
            media_body=MediaFileUpload(thumbnail_path, mimetype="image/png"),
        ).execute()
        print(f"  Thumbnail uploaded for video {video_id}")
        return True
    except Exception as e:
        print(f"  Thumbnail upload failed: {e}")
        return False


def set_public(video_id: str) -> bool:
    """Change a YouTube video's privacy status to public. Returns True on success."""
    youtube = get_authenticated_service()
    try:
        youtube.videos().update(
            part="status",
            body={
                "id": video_id,
                "status": {"privacyStatus": "public"},
            }
        ).execute()
        print(f"  Video {video_id} set to public")
        return True
    except Exception as e:
        print(f"  set_public failed: {e}")
        return False


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Upload assembled video to YouTube")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--draft", help="Path to specific draft JSON")
    group.add_argument("--latest", action="store_true", help="Use most recent draft")
    args = parser.parse_args()

    draft_path = get_latest_draft() if args.latest else Path(args.draft)
    if args.latest:
        print(f"  Using latest draft: {draft_path.name}")

    data = load_draft(draft_path)

    # Check video is assembled
    video_info = data.get("_video", {})
    video_path = Path(video_info.get("path", ""))
    if not video_path.exists():
        print(f"  Error: Assembled video not found at {video_path}")
        print("  Run video_assembler.py first.")
        sys.exit(1)

    title = data.get("title", "Untitled")
    description = data.get("description", "")
    tags = data.get("tags", [])

    print(f"\n  Authenticating with YouTube...")
    youtube = get_authenticated_service()
    get_upload_channel(youtube)

    video_id = upload_video(youtube, video_path, title, description, tags)

    video_url = f"https://www.youtube.com/watch?v={video_id}"
    studio_url = f"https://studio.youtube.com/video/{video_id}/edit"

    # Save upload metadata back to draft
    update_draft(draft_path, "_upload", {
        "video_id": video_id,
        "video_url": video_url,
        "studio_url": studio_url,
        "uploaded_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "privacy_status": "private",
    })

    print(f"\n{'='*60}")
    print(f"  UPLOAD SUCCESSFUL")
    print(f"{'='*60}")
    print(f"  Video ID  : {video_id}")
    print(f"  Watch URL : {video_url}")
    print(f"  Studio    : {studio_url}")
    print(f"")
    print(f"  Next steps:")
    print(f"  1. Go to YouTube Studio and review the video")
    print(f"  2. Upload the SRT captions file")
    print(f"  3. Add thumbnail")
    print(f"  4. Change privacy from Private to Public when ready")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
