"""
Standalone Email Grabber (Diagnostic / Legacy Tool).

Note: In the Notifier application, emails are automatically fetched and 
processed dynamically per-user via:
    python manage.py sync_mails
or via the 'Sync Emails' button in the web UI.

Credentials are now securely stored and managed per-user in the database
(UserMailbox model) rather than hardcoded in .env.
"""
import sys
from pathlib import Path
import imaplib
import time

BASE_DIR = Path(__file__).resolve().parent.parent
DJANGO_DIR = BASE_DIR / "djangoproj"

if str(DJANGO_DIR) not in sys.path:
    sys.path.insert(0, str(DJANGO_DIR))

EMAIL_DIR = Path(__file__).resolve().parent / "fetched_emails"
EMAIL_DIR.mkdir(exist_ok=True)


def run_grabber():
    import os
    import django

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "djangoproj.settings")
    django.setup()

    from application.models import UserMailbox

    mailbox = UserMailbox.objects.filter(is_active=True).first()
    if not mailbox:
        print("No active mailbox configured. Connect one in your Profile settings.")
        return

    print(f"Connecting to {mailbox.platform} ({mailbox.imap_server}:{mailbox.imap_port}) for {mailbox.email_address}...")
    try:
        mail = imaplib.IMAP4_SSL(mailbox.imap_server, mailbox.imap_port)
        mail.login(mailbox.email_address, mailbox.password)
        mail.select("INBOX")
    except Exception as err:
        print(f"Connection failed: {err}")
        return

    # Determine latest fetch time from existing downloaded .eml files
    eml_files = list(EMAIL_DIR.glob("*.eml"))
    if eml_files:
        latest_mtime = max(f.stat().st_mtime for f in eml_files)
        since_epoch = int(latest_mtime) - 60  # 1-minute safety buffer
        query = f'"category:primary after:{since_epoch}"'
        print(f"Fetching emails newer than {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(latest_mtime))}...")
    else:
        query = '"category:primary newer_than:7d"'
        print("Initial fetch: searching all primary emails from the last 7 days...")

    status, messages = mail.search(None, "X-GM-RAW", query)
    print(f"Status: {status} | Found: {len(messages[0].split())} email(s)")

    for email_id in messages[0].split():
        status, data = mail.fetch(email_id, "(BODY.PEEK[])")
        if status != "OK":
            print(f"Failed to fetch {email_id}")
            continue

        raw_email = data[0][1]
        filepath = EMAIL_DIR / f"{email_id.decode()}.eml"

        with open(filepath, "wb") as f:
            f.write(raw_email)

        print(f"Saved: {filepath}")

    mail.logout()


if __name__ == "__main__":
    run_grabber()