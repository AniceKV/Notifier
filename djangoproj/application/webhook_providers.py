import base64
import json
import logging
import secrets
import urllib.error
import urllib.parse
import urllib.request
from datetime import timedelta
from typing import Dict, List, Optional, Tuple

from django.utils import timezone

from application.models import UserMailbox, WebhookEvent

logger = logging.getLogger(__name__)


GMAIL_WATCH_URL = "https://gmail.googleapis.com/gmail/v1/users/me/watch"
GMAIL_HISTORY_URL = "https://gmail.googleapis.com/gmail/v1/users/me/history"
OUTLOOK_SUBSCRIPTION_URL = "https://graph.microsoft.com/v1.0/subscriptions"
OUTLOOK_MESSAGES_DELTA_URL = "https://graph.microsoft.com/v1.0/me/mailFolders/inbox/messages/delta"
OUTLOOK_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"


def _request_json(url: str, method: str = "GET", body: Optional[Dict] = None, headers: Optional[Dict[str, str]] = None):
    data = None
    req_headers = {"Accept": "application/json"}
    if headers:
        req_headers.update(headers)
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        req_headers.setdefault("Content-Type", "application/json")

    req = urllib.request.Request(url, data=data, method=method, headers=req_headers)
    with urllib.request.urlopen(req, timeout=20) as response:
        payload = response.read().decode("utf-8") if response.readable() else ""
        if not payload:
            return {}
        return json.loads(payload)


def log_webhook_event(
    provider: str,
    status: str,
    detail: str,
    payload: Optional[Dict] = None,
    mailbox: Optional[UserMailbox] = None,
    event_type: str = "",
):
    WebhookEvent.objects.create(
        mailbox=mailbox,
        provider=provider,
        event_type=event_type,
        status=status,
        detail=detail,
        payload=payload or {},
        processed_at=timezone.now() if status in {"processed", "error", "rejected"} else None,
    )


def ensure_mailbox_tokens(mailbox: UserMailbox):
    updated = False
    if not mailbox.get_webhook_secret_token():
        mailbox.set_webhook_secret_token(secrets.token_urlsafe(32))
        updated = True
    if not mailbox.get_webhook_validation_token():
        mailbox.set_webhook_validation_token(secrets.token_urlsafe(24))
        updated = True
    if updated:
        mailbox.save(update_fields=["webhook_secret_token", "webhook_validation_token", "updated_at"])


def refresh_outlook_access_token(mailbox: UserMailbox) -> bool:
    refresh_token = mailbox.get_provider_refresh_token()
    client_id = mailbox.webhook_event_meta.get("client_id") or ""
    client_secret = mailbox.webhook_event_meta.get("client_secret") or ""

    if not refresh_token or not client_id or not client_secret:
        return False

    payload = urllib.parse.urlencode({
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
        "scope": "offline_access Mail.Read",
    }).encode("utf-8")

    req = urllib.request.Request(
        OUTLOOK_TOKEN_URL,
        data=payload,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            data = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        logger.error("Failed token refresh for mailbox %s: %s", mailbox.id, exc)
        return False

    token = data.get("access_token")
    if not token:
        return False

    mailbox.set_provider_access_token(token)
    new_refresh = data.get("refresh_token")
    if new_refresh:
        mailbox.set_provider_refresh_token(new_refresh)

    expires_in = int(data.get("expires_in", 3600))
    mailbox.provider_token_expires_at = timezone.now() + timedelta(seconds=max(expires_in - 60, 60))
    mailbox.save(update_fields=["provider_access_token", "provider_refresh_token", "provider_token_expires_at", "updated_at"])
    return True


def get_provider_access_token(mailbox: UserMailbox) -> str:
    token = mailbox.get_provider_access_token()
    if not token:
        return ""

    if mailbox.provider_type != "outlook":
        return token

    if mailbox.provider_token_expires_at and mailbox.provider_token_expires_at > timezone.now() + timedelta(minutes=2):
        return token

    if refresh_outlook_access_token(mailbox):
        return mailbox.get_provider_access_token()
    return token


def register_gmail_watch(mailbox: UserMailbox) -> Tuple[bool, str]:
    token = get_provider_access_token(mailbox)
    topic_name = mailbox.webhook_event_meta.get("topic_name") or ""
    if not token or not topic_name:
        return False, "Missing Gmail access token or Pub/Sub topic name"

    payload = {
        "topicName": topic_name,
        "labelIds": ["INBOX"],
        "labelFilterBehavior": "INCLUDE",
    }

    try:
        resp = _request_json(
            GMAIL_WATCH_URL,
            method="POST",
            body=payload,
            headers={"Authorization": "Bearer " + token},
        )
    except Exception as exc:
        return False, f"Gmail watch registration failed: {exc}"

    mailbox.webhook_subscription_id = resp.get("historyId", "")
    mailbox.webhook_cursor = resp.get("historyId", mailbox.webhook_cursor)
    expiration = resp.get("expiration")
    if expiration:
        try:
            mailbox.webhook_expires_at = timezone.datetime.fromtimestamp(int(expiration) / 1000, tz=timezone.utc)
        except Exception:
            mailbox.webhook_expires_at = timezone.now() + timedelta(hours=24)
    else:
        mailbox.webhook_expires_at = timezone.now() + timedelta(hours=24)

    mailbox.webhook_status = "active"
    mailbox.webhook_last_error = ""
    mailbox.save(update_fields=[
        "webhook_subscription_id",
        "webhook_cursor",
        "webhook_expires_at",
        "webhook_status",
        "webhook_last_error",
        "updated_at",
    ])
    return True, "Gmail watch registered"


def register_outlook_subscription(mailbox: UserMailbox) -> Tuple[bool, str]:
    token = get_provider_access_token(mailbox)
    callback_url = mailbox.webhook_event_meta.get("callback_url") or ""
    if not token or not callback_url:
        return False, "Missing Outlook access token or callback URL"

    ensure_mailbox_tokens(mailbox)

    expiration = timezone.now() + timedelta(hours=68)
    payload = {
        "changeType": "created",
        "notificationUrl": callback_url,
        "resource": "me/mailFolders('inbox')/messages",
        "expirationDateTime": expiration.isoformat().replace("+00:00", "Z"),
        "clientState": mailbox.get_webhook_secret_token(),
    }

    try:
        resp = _request_json(
            OUTLOOK_SUBSCRIPTION_URL,
            method="POST",
            body=payload,
            headers={"Authorization": "Bearer " + token},
        )
    except Exception as exc:
        return False, f"Outlook subscription registration failed: {exc}"

    mailbox.webhook_subscription_id = resp.get("id", mailbox.webhook_subscription_id)
    mailbox.webhook_resource_id = resp.get("resource", mailbox.webhook_resource_id)
    exp = resp.get("expirationDateTime")
    if exp:
        mailbox.webhook_expires_at = timezone.datetime.fromisoformat(exp.replace("Z", "+00:00"))
    else:
        mailbox.webhook_expires_at = expiration
    mailbox.webhook_status = "active"
    mailbox.webhook_last_error = ""
    mailbox.save(update_fields=[
        "webhook_subscription_id",
        "webhook_resource_id",
        "webhook_expires_at",
        "webhook_status",
        "webhook_last_error",
        "updated_at",
    ])
    return True, "Outlook subscription registered"


def ensure_webhook_subscription(mailbox: UserMailbox) -> Tuple[bool, str]:
    if not mailbox.should_use_webhook():
        mailbox.webhook_status = "disabled"
        mailbox.save(update_fields=["webhook_status", "updated_at"])
        return False, "Webhook mode disabled"

    try:
        if mailbox.provider_type == "gmail":
            return register_gmail_watch(mailbox)
        if mailbox.provider_type == "outlook":
            return register_outlook_subscription(mailbox)
        mailbox.webhook_status = "disabled"
        mailbox.save(update_fields=["webhook_status", "updated_at"])
        return False, "Provider has no webhook support"
    except Exception as exc:
        mailbox.webhook_status = "error"
        mailbox.webhook_last_error = str(exc)
        mailbox.save(update_fields=["webhook_status", "webhook_last_error", "updated_at"])
        return False, str(exc)


def renew_due_subscriptions() -> Dict[str, int]:
    now = timezone.now()
    mailboxes = UserMailbox.objects.filter(is_active=True, webhook_enabled=True)
    stats = {"checked": 0, "renewed": 0, "failed": 0}
    for mailbox in mailboxes:
        stats["checked"] += 1
        if mailbox.provider_type not in {"gmail", "outlook"}:
            continue
        needs_renew = (
            mailbox.webhook_status != "active"
            or mailbox.webhook_expires_at is None
            or mailbox.webhook_expires_at <= now + timedelta(hours=6)
        )
        if not needs_renew:
            continue
        ok, message = ensure_webhook_subscription(mailbox)
        if ok:
            stats["renewed"] += 1
            log_webhook_event(mailbox=mailbox, provider=mailbox.provider_type, status="processed", detail=message, payload={"kind": "renewal"}, event_type="renewal")
        else:
            stats["failed"] += 1
            mailbox.webhook_enabled = False
            mailbox.webhook_status = "error"
            mailbox.webhook_last_error = message
            mailbox.save(update_fields=["webhook_enabled", "webhook_status", "webhook_last_error", "updated_at"])
            log_webhook_event(mailbox=mailbox, provider=mailbox.provider_type, status="error", detail=message, payload={"kind": "renewal"}, event_type="renewal")
    return stats


def parse_gmail_pubsub_payload(raw_body: bytes) -> Dict:
    try:
        incoming = json.loads(raw_body.decode("utf-8") or "{}")
    except Exception:
        return {}

    message = incoming.get("message") or {}
    encoded = message.get("data")
    if not encoded:
        return {}

    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8")
        return json.loads(decoded)
    except Exception:
        return {}


def fetch_changed_message_ids(mailbox: UserMailbox, trigger_context: Optional[Dict] = None) -> Tuple[List[str], str]:
    context = trigger_context or {}
    provider = context.get("provider") or mailbox.provider_type

    if provider == "outlook":
        return _fetch_outlook_delta(mailbox, context)
    if provider == "gmail":
        return _fetch_gmail_history(mailbox, context)

    ids = context.get("message_ids") or []
    if isinstance(ids, str):
        ids = [item.strip() for item in ids.split(",") if item.strip()]
    return ids, mailbox.webhook_cursor


def _fetch_gmail_history(mailbox: UserMailbox, context: Dict) -> Tuple[List[str], str]:
    token = get_provider_access_token(mailbox)
    if not token:
        return [], mailbox.webhook_cursor

    start_history = context.get("history_id") or mailbox.webhook_cursor
    if not start_history:
        return [], mailbox.webhook_cursor

    url = f"{GMAIL_HISTORY_URL}?startHistoryId={start_history}&historyTypes=messageAdded"
    try:
        data = _request_json(url, headers={"Authorization": "Bearer " + token})
    except urllib.error.HTTPError as exc:
        logger.warning("Gmail history fetch failed for mailbox %s: %s", mailbox.id, exc)
        return [], mailbox.webhook_cursor
    except Exception:
        return [], mailbox.webhook_cursor

    message_ids = []
    for history_item in data.get("history", []):
        for msg_item in history_item.get("messagesAdded", []):
            msg = msg_item.get("message") or {}
            msg_id = msg.get("id")
            if msg_id:
                message_ids.append(msg_id)

    new_cursor = data.get("historyId") or str(context.get("history_id") or mailbox.webhook_cursor)
    mailbox.webhook_cursor = new_cursor
    mailbox.save(update_fields=["webhook_cursor", "updated_at"])
    return list(dict.fromkeys(message_ids)), new_cursor


def _fetch_outlook_delta(mailbox: UserMailbox, context: Dict) -> Tuple[List[str], str]:
    token = get_provider_access_token(mailbox)
    if not token:
        return [], mailbox.webhook_cursor

    delta_link = context.get("delta_token") or mailbox.webhook_cursor
    url = delta_link if delta_link and delta_link.startswith("http") else OUTLOOK_MESSAGES_DELTA_URL

    headers = {"Authorization": "Bearer " + token}
    try:
        data = _request_json(url, headers=headers)
    except Exception as exc:
        logger.warning("Outlook delta fetch failed for mailbox %s: %s", mailbox.id, exc)
        return [], mailbox.webhook_cursor

    message_ids = []
    for item in data.get("value", []):
        msg_id = item.get("internetMessageId") or item.get("id")
        if msg_id:
            message_ids.append(msg_id)

    new_cursor = data.get("@odata.deltaLink") or data.get("@odata.nextLink") or mailbox.webhook_cursor
    if new_cursor:
        mailbox.webhook_cursor = new_cursor
        mailbox.save(update_fields=["webhook_cursor", "updated_at"])
    return list(dict.fromkeys(message_ids)), new_cursor or mailbox.webhook_cursor
