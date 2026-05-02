"""
Telegram Bot API wrapper for Agent44.
Bot: @Agent44bot (separate from @JovePMbot used by JovePM).
Three message types:
  - notify()         : fire-and-forget notification
  - send_spend_gate(): spend approval request with Approve/Reject buttons
  - send_publish_gate(): publish approval with QC summary + Studio link
  - wait_for_approval(): polls for user response, returns 'approved'/'rejected'/'timeout'
"""

import time
import logging
import requests

from config.settings import (
    AGENT44_BOT_TOKEN as BOT_TOKEN,
    TELEGRAM_CHAT_ID as CHAT_ID,
    APPROVAL_TIMEOUT_HOURS,
)

logger = logging.getLogger(__name__)

POLL_INTERVAL = 10  # seconds between getUpdates polls


def _post(method: str, payload: dict) -> dict:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/{method}"
    resp = requests.post(url, json=payload, timeout=15)
    resp.raise_for_status()
    return resp.json()


def _get_updates(offset: int = 0) -> list:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    resp = requests.get(url, params={"offset": offset, "timeout": 5}, timeout=10)
    resp.raise_for_status()
    return resp.json().get("result", [])


def notify(text: str) -> None:
    """Send a plain notification message. Fire and forget."""
    try:
        _post("sendMessage", {
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
        })
    except Exception as e:
        logger.error(f"Telegram notify failed: {e}")


def send_spend_gate(topic: str, estimated_cost: float) -> int:
    """
    Send spend approval request. Returns Telegram message_id.
    User taps Approve or Reject — tracked via wait_for_approval().
    """
    text = (
        f"*Agent44 — Spend Approval*\n\n"
        f"Ready to produce a new video.\n\n"
        f"*Topic:* {topic}\n"
        f"*Estimated cost:* ${estimated_cost:.2f}\n\n"
        f"Approve to start the pipeline."
    )
    result = _post("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": "approve_0"},
                {"text": "❌ Reject", "callback_data": "reject_0"},
            ]]
        }
    })
    msg_id = result["result"]["message_id"]
    # Re-send with correct message_id embedded in callback_data
    _post("editMessageReplyMarkup", {
        "chat_id": CHAT_ID,
        "message_id": msg_id,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve_{msg_id}"},
                {"text": "❌ Reject", "callback_data": f"reject_{msg_id}"},
            ]]
        }
    })
    return msg_id


def send_publish_gate(draft: dict, studio_url: str) -> int:
    """
    Send publish preview gate. Returns Telegram message_id.
    draft must contain: _meta.video_number, _seo.title, _qc, _costs.total
    """
    video_num = draft.get("_meta", {}).get("video_number", "?")
    title = draft.get("_seo", {}).get("title", "Untitled")
    qc = draft.get("_qc", {})
    cost = draft.get("_costs", {}).get("total", 0)

    try:
        video_num_str = f"{video_num:03d}"
    except (ValueError, TypeError):
        video_num_str = str(video_num)

    text = (
        f"*Agent44 — Video #{video_num_str} Ready*\n\n"
        f"*Title:* {title}\n"
        f"*QC:* {qc.get('pass', 0)}P / {qc.get('warn', 0)}W / {qc.get('fail', 0)}F\n"
        f"*Cost:* ${cost:.2f}\n"
        f"*Preview:* [YouTube Studio]({studio_url})\n\n"
        f"Approve to publish."
    )
    result = _post("sendMessage", {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "Markdown",
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": "approve_0"},
                {"text": "❌ Reject", "callback_data": "reject_0"},
                {"text": "🔄 Re-run footage", "callback_data": "rerun_0"},
            ]]
        }
    })
    msg_id = result["result"]["message_id"]
    _post("editMessageReplyMarkup", {
        "chat_id": CHAT_ID,
        "message_id": msg_id,
        "reply_markup": {
            "inline_keyboard": [[
                {"text": "✅ Approve", "callback_data": f"approve_{msg_id}"},
                {"text": "❌ Reject", "callback_data": f"reject_{msg_id}"},
                {"text": "🔄 Re-run footage", "callback_data": f"rerun_{msg_id}"},
            ]]
        }
    })
    return msg_id


def wait_for_approval(message_id: int, run_id: int) -> str:
    """
    Poll Telegram for callback_query on message_id.
    Returns: 'approved' | 'rejected' | 'rerun' | 'timeout'
    Polls every POLL_INTERVAL seconds up to APPROVAL_TIMEOUT_HOURS.
    run_id is accepted for caller context but not used internally;
    the orchestrator handles all DB state transitions.
    """
    deadline = time.time() + APPROVAL_TIMEOUT_HOURS * 3600
    offset = 0

    while time.time() < deadline:
        try:
            updates = _get_updates(offset=offset)
            for update in updates:
                offset = update["update_id"] + 1
                cq = update.get("callback_query")
                if not cq:
                    continue
                data = cq.get("data", "")
                try:
                    _post("answerCallbackQuery", {"callback_query_id": cq["id"]})
                except Exception:
                    pass
                if data == f"approve_{message_id}":
                    return "approved"
                if data == f"reject_{message_id}":
                    return "rejected"
                if data == f"rerun_{message_id}":
                    return "rerun"
        except Exception as e:
            logger.warning(f"Telegram poll error: {e}")

        time.sleep(POLL_INTERVAL)

    return "timeout"
