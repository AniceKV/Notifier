from celery import shared_task
from django.contrib.auth.models import User
from application.models import UserMailbox
import time
import logging

logger = logging.getLogger(__name__)

@shared_task(bind=True, autoretry_for=(Exception,), retry_backoff=True, max_retries=5)
def sync_mailbox_task(self, mailbox_id):
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
        call_command('sync_mails', user_id=mailbox.user.id, stdout=out, stderr=out)
        
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
        # Enqueue the individual mailbox sync task
        sync_mailbox_task.delay(mailbox.id)
    
    logger.info(f"Enqueued sync tasks for {mailboxes.count()} active mailboxes.")
