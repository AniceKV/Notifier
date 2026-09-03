import os
import json
import html
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)

def send_ntfy_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email") -> bool:
    """
    Sends an instant push notification to your phone via ntfy.sh (Zero bot/account setup needed).
    """
    ntfy_topic = os.getenv("NTFY_TOPIC")
    if not ntfy_topic:
        return False

    clean_summary = summary.replace("### Summary", "").replace("### Content", "").strip()

    body = (
        f"Platform: {platform}\n"
        f"From: {sender}\n"
        f"Subject: {subject}\n\n"
        f"Summary:\n{clean_summary}"
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


def send_telegram_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email", chat_id: str = None) -> bool:
    """
    Sends a formatted notification to Telegram when an email match occurs.
    """
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
    target_chat_id = chat_id or os.getenv("TELEGRAM_CHAT_ID")

    if not bot_token or not target_chat_id:
        return False

    clean_summary = summary.replace("### Summary", "").replace("### Content", "").strip()

    safe_topic = html.escape(topic_name)
    safe_platform = html.escape(platform)
    safe_sender = html.escape(sender)
    safe_subject = html.escape(subject)
    safe_summary = html.escape(clean_summary)

    message_text = (
        f"🔔 <b>Matched Topic:</b> {safe_topic}\n"
        f"🌐 <b>Platform:</b> {safe_platform}\n\n"
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


def send_mobile_alert(topic_name: str, sender: str, subject: str, summary: str, platform: str = "Email") -> bool:
    """
    Tries configured notification providers (ntfy.sh and Telegram) with platform identifier.
    """
    sent_ntfy = send_ntfy_alert(topic_name, sender, subject, summary, platform=platform)
    sent_telegram = send_telegram_alert(topic_name, sender, subject, summary, platform=platform)
    return sent_ntfy or sent_telegram
