import os
import json
import html
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)


def _format_timestamp(received_at) -> str:
    """Helper to format datetime nicely into readable local time string."""
    if not received_at:
        return ""
    try:
        # If it's a datetime object
        if hasattr(received_at, "strftime"):
            try:
                from django.utils import timezone
                if timezone.is_aware(received_at):
                    local_dt = timezone.localtime(received_at)
                else:
                    local_dt = received_at
                return local_dt.strftime("%b %d, %Y • %I:%M %p")
            except Exception:
                return received_at.strftime("%b %d, %Y • %I:%M %p")
        return str(received_at)
    except Exception:
        return str(received_at)


def send_ntfy_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email", received_at=None) -> bool:
    """
    Sends an instant push notification to your phone via ntfy.sh (Zero bot/account setup needed).
    """
    ntfy_topic = os.getenv("NTFY_TOPIC")
    if not ntfy_topic:
        return False

    clean_summary = summary.replace("### Summary", "").replace("### Content", "").strip()
    time_str = _format_timestamp(received_at)
    time_line = f"🕒 Received: {time_str}\n" if time_str else ""

    body = (
        f"🌐 Platform: {platform}\n"
        f"{time_line}"
        f"👤 From: {sender}\n"
        f"📌 Subject: {subject}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 AI Summary:\n{clean_summary}"
    )

    url = f"https://ntfy.sh/{ntfy_topic.strip()}"
    try:
        req = urllib.request.Request(
            url,
            data=body.encode("utf-8"),
            headers={
                "Title": f"[{platform}] {topic_name}",
                "Priority": "4",
                "Tags": "incoming_envelope,bell",
            }
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"ntfy push notification sent successfully to topic: {ntfy_topic}")
                return True
    except Exception as err:
        logger.error(f"Failed to send ntfy notification: {err}")
    return False


def send_telegram_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email", chat_id: str = None, received_at=None) -> bool:
    """
    Sends a formatted notification to Telegram when an email match occurs.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not target_chat_id:
        return False

    clean_summary = summary.replace("### Summary", "").replace("### Content", "").strip()
    time_str = _format_timestamp(received_at)
    time_badge = f"  •  🕒 <b>Time:</b> {html.escape(time_str)}" if time_str else ""

    safe_topic = html.escape(topic_name)
    safe_platform = html.escape(platform)
    safe_sender = html.escape(sender)
    safe_subject = html.escape(subject)
    safe_summary = html.escape(clean_summary)

    message_text = (
        f"🔔 <b>Matched Topic:</b> {safe_topic}\n"
        f"🌐 <b>Platform:</b> {safe_platform}{time_badge}\n\n"
        f"👤 <b>From:</b> {safe_sender}\n"
        f"📌 <b>Subject:</b> {safe_subject}\n\n"
        f"━━━━━━━━━━━━━━━━━━\n"
        f"📝 <b>AI Summary:</b>\n"
        f"{safe_summary}"
    )

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": target_chat_id,
        "text": message_text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                logger.info(f"Telegram alert sent successfully for topic: {topic_name}")
                return True
            else:
                logger.warning(f"Telegram API responded with status: {response.status}")
                return False
    except Exception as err:
        logger.error(f"Failed to send Telegram notification: {err}")
        return False


def send_mobile_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email", received_at=None) -> bool:
    """
    Tries configured notification providers (ntfy.sh and Telegram) with platform identifier and email arrival timestamp.
    """
    sent_ntfy = send_ntfy_alert(topic_name, sender, subject, summary, platform=platform, received_at=received_at)
    sent_telegram = send_telegram_alert(topic_name, sender, subject, summary, platform=platform, received_at=received_at)
    return sent_ntfy or sent_telegram
