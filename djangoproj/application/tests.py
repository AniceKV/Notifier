import base64
import json
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse

from application.models import UserMailbox


class WebhookEndpointTests(TestCase):
    def setUp(self):
        self.user = User.objects.create(username="alice", email="alice@example.com")
        self.user.set_password("test-pass-123")
        self.user.save(update_fields=["password"])
        self.gmail_mailbox = UserMailbox(
            user=self.user,
            platform="Gmail",
            provider_type="gmail",
            trigger_mode="webhook",
            webhook_enabled=True,
            email_address="alice@gmail.com",
            imap_server="imap.gmail.com",
            imap_port=993,
            webhook_cursor="100",
        )
        setattr(self.gmail_mailbox, "password", "app-pass")
        self.gmail_mailbox.save()
        self.outlook_mailbox = UserMailbox(
            user=self.user,
            platform="Outlook",
            provider_type="outlook",
            trigger_mode="webhook",
            webhook_enabled=True,
            email_address="alice@outlook.com",
            imap_server="outlook.office365.com",
            imap_port=993,
            webhook_subscription_id="sub-123",
        )
        setattr(self.outlook_mailbox, "password", "app-pass")
        self.outlook_mailbox.save()
        self.outlook_mailbox.set_webhook_secret_token("state-secret")
        self.outlook_mailbox.save(update_fields=["webhook_secret_token", "updated_at"])

    def _gmail_payload(self):
        msg = {"emailAddress": "alice@gmail.com", "historyId": "101"}
        encoded = base64.urlsafe_b64encode(json.dumps(msg).encode("utf-8")).decode("utf-8")
        return {"message": {"data": encoded}}

    @patch("application.views.sync_mailbox_task.delay")
    @patch("application.views.settings.GMAIL_WEBHOOK_SHARED_TOKEN", "shared-token")
    def test_gmail_webhook_queues_sync_on_valid_token(self, delay_mock):
        resp = self.client.post(
            reverse("gmail_webhook"),
            data=json.dumps(self._gmail_payload()),
            content_type="application/json",
            headers={"X-Notifier-Webhook-Token": "shared-token"},
        )
        self.assertEqual(resp.status_code, 200)
        delay_mock.assert_called_once()

    @patch("application.views.settings.GMAIL_WEBHOOK_SHARED_TOKEN", "shared-token")
    def test_gmail_webhook_rejects_invalid_token(self):
        resp = self.client.post(
            reverse("gmail_webhook"),
            data=json.dumps(self._gmail_payload()),
            content_type="application/json",
            headers={"X-Notifier-Webhook-Token": "wrong"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_outlook_webhook_validation_handshake(self):
        resp = self.client.get(reverse("outlook_webhook"), {"validationToken": "abc123"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.content.decode("utf-8"), "abc123")

    @patch("application.views.sync_mailbox_task.delay")
    def test_outlook_webhook_rejects_bad_client_state(self, delay_mock):
        payload = {
            "value": [
                {
                    "subscriptionId": "sub-123",
                    "clientState": "wrong-state",
                    "changeType": "created",
                    "resourceData": {"id": "msg-id-1"},
                }
            ]
        }
        resp = self.client.post(
            reverse("outlook_webhook"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json().get("queued"), 0)
        delay_mock.assert_not_called()
