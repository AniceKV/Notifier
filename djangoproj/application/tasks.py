from celery import shared_task
from django.contrib.auth.models import User
from application.models import UserMailbox
import time
import logging
from application.webhook_providers import renew_due_subscriptions

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_mailbox_task(self, mailbox_id, trigger_context=None):
    """
    Synchronizes emails for a specific mailbox.
    Uses exponential backoff for retries if an Exception occurs (e.g., IMAP timeout).
    """
    try:
        mailbox = UserMailbox.objects.get(id=mailbox_id)
        if not mailbox.is_active:
            logger.info(f"Mailbox {mailbox.id} is not active. Skipping.")
            return

        logger.info(f"Starting sync for mailbox: {mailbox.email_address} (Platform: {mailbox.platform})")
        
        from django.core.management import call_command
        from io import StringIO
        
        # Capture the stdout from the management command to log it
        out = StringIO()
        trigger_context = trigger_context or {}
        event_message_ids = trigger_context.get("message_ids") or []
        if isinstance(event_message_ids, (list, tuple)):
            event_message_ids = ",".join(str(v) for v in event_message_ids if v)

        call_command(
            'sync_mails',
            user_id=mailbox.user.id,
            mailbox_id=mailbox.id,
            trigger_provider=trigger_context.get("provider") or "",
            event_history_id=trigger_context.get("history_id") or "",
            event_delta_token=trigger_context.get("delta_token") or "",
            event_message_ids=event_message_ids,
            stdout=out,
            stderr=out,
        )
        
        logger.info(f"Successfully synced mailbox: {mailbox.email_address}\nOutput:\n{out.getvalue()}")

        
    except UserMailbox.DoesNotExist:
        logger.error(f"Mailbox {mailbox_id} does not exist.")
    except Exception as e:
        logger.error(f"Error syncing mailbox {mailbox_id}: {e}")
        # Re-raise to trigger the autoretry
        raise


@shared_task
def sync_all_users_emails():
    """
    Periodic task to trigger synchronization for all active mailboxes.
    Called by Celery Beat every 5 minutes.
    """
    mailboxes = UserMailbox.objects.filter(is_active=True)
    for mailbox in mailboxes:
        if mailbox.should_poll():
            sync_mailbox_task.delay(mailbox.id, trigger_context={"provider": "polling", "event_type": "scheduled_poll"})
    
    logger.info(f"Enqueued polling sync tasks for eligible mailboxes out of {mailboxes.count()} active mailboxes.")


@shared_task
def renew_webhook_subscriptions():
    """
    Periodic lightweight task to renew provider webhook subscriptions and
    auto-fallback to polling when renewal fails.
    """
    stats = renew_due_subscriptions()
    logger.info(
        "Webhook renewal cycle completed. checked=%s renewed=%s failed=%s",
        stats.get("checked", 0),
        stats.get("renewed", 0),
        stats.get("failed", 0),
    )
