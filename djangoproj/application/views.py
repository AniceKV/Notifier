from django.shortcuts import render, redirect, get_object_or_404
import hmac
import json
import secrets

from django.conf import settings
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from datetime import timedelta
from django.utils import timezone

from application.models import Topic, Email, EmailMatch, UserMailbox, UserProfile
from application.forms import TopicForm, UserProfileForm, UserMailboxForm, LMStudioConfigForm, GeminiApiKeyForm
from application.tasks import sync_mailbox_task
from application.webhook_providers import (
    ensure_webhook_subscription,
    log_webhook_event,
    parse_gmail_pubsub_payload,
)
from Ingestion.summarizer import test_lm_studio_connection


class InboxView(LoginRequiredMixin, View):
    """
    Main inbox hub showing 'Relevant Mails' and 'All Mails' based on ?tab=
    with multi-dimensional filtering by topic, platform, time, and combinations.
    """
    def get(self, request):
        current_tab = request.GET.get('tab', 'relevant')
        selected_topic = request.GET.get('topic', '').strip()
        selected_platform = request.GET.get('platform', '').strip()
        selected_time = request.GET.get('time', '').strip()

        # Base querysets
        all_emails = Email.objects.filter(owner=request.user).order_by('-received_at')
        relevant_emails = Email.objects.filter(owner=request.user, matches__isnull=False).distinct().prefetch_related('matches__topic').order_by('-received_at')

        # Collect available filter choices for the user
        user_topics = request.user.topics.all().order_by('name')

        platforms_from_emails = set(Email.objects.filter(owner=request.user).values_list('platform', flat=True).distinct())
        platforms_from_mailboxes = set(request.user.mailboxes.values_list('platform', flat=True).distinct())
        available_platforms = sorted(list(platforms_from_emails | platforms_from_mailboxes))

        # 1. Filter by Topic
        if selected_topic:
            try:
                topic_id = int(selected_topic)
                relevant_emails = relevant_emails.filter(matches__topic_id=topic_id).distinct()
                all_emails = all_emails.filter(matches__topic_id=topic_id).distinct()
            except ValueError:
                relevant_emails = relevant_emails.filter(matches__topic__name__iexact=selected_topic).distinct()
                all_emails = all_emails.filter(matches__topic__name__iexact=selected_topic).distinct()

        # 2. Filter by Platform
        if selected_platform:
            relevant_emails = relevant_emails.filter(platform__iexact=selected_platform)
            all_emails = all_emails.filter(platform__iexact=selected_platform)

        # 3. Filter by Time Window
        now = timezone.now()
        if selected_time in ('24h', 'today'):
            time_threshold = now - timedelta(days=1)
            relevant_emails = relevant_emails.filter(received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)
        elif selected_time == '7d':
            time_threshold = now - timedelta(days=7)
            relevant_emails = relevant_emails.filter(received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)
        elif selected_time == '30d':
            time_threshold = now - timedelta(days=30)
            relevant_emails = relevant_emails.filter(received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)

        active_filters_count = sum(1 for val in [selected_topic, selected_platform, selected_time] if val)

        context = {
            'tab': current_tab,
            'all_emails': all_emails,
            'relevant_emails': relevant_emails,
            'relevant_matches': relevant_emails,
            'relevant_count': relevant_emails.count(),
            'all_count': all_emails.count(),
            'user_topics': user_topics,
            'available_platforms': available_platforms,
            'selected_topic': selected_topic,
            'selected_platform': selected_platform,
            'selected_time': selected_time,
            'active_filters_count': active_filters_count,
        }
        return render(request, 'inbox.html', context)


class EmailDetailView(LoginRequiredMixin, View):
    """
    Normal email reading view: shows headers, AI summary if matched, and full body.
    Supports ?partial=1 for AJAX loading into the inbox reading pane.
    """
    def get(self, request, pk):
        email_obj = get_object_or_404(Email, pk=pk, owner=request.user)
        matches = EmailMatch.objects.filter(email=email_obj, user=request.user).select_related('topic')

        ctx = {'email': email_obj, 'matches': matches}

        # Partial mode: return only the reading-pane fragment (no <html>/<head>/header)
        if request.GET.get('partial') == '1':
            return render(request, 'email_detail_partial.html', ctx)

        return render(request, 'email_detail.html', ctx)


from django.views.decorators.clickjacking import xframe_options_exempt
from django.views.decorators.csrf import csrf_exempt
from django.utils.decorators import method_decorator


@method_decorator(xframe_options_exempt, name='dispatch')
class EmailContentView(LoginRequiredMixin, View):
    """
    Serves the raw email HTML/text body in an isolated, sandboxed response
    to prevent style leakage and ensure perfect legibility inside an iframe.
    """
    def get(self, request, pk):
        import html
        email_obj = get_object_or_404(Email, pk=pk, owner=request.user)
        raw_body = email_obj.body or ""

        # If plain text without HTML formatting, wrap cleanly in readable template
        if "<html" not in raw_body.lower() and "<div" not in raw_body.lower() and "<p" not in raw_body.lower():
            content = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            font-size: 14px;
            line-height: 1.6;
            color: #1a1a1a;
            background: #ffffff;
            padding: 24px;
            margin: 0;
            word-break: break-word;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>{html.escape(raw_body)}</body>
</html>"""
        else:
            content = raw_body

        response = HttpResponse(content, content_type="text/html; charset=utf-8")
        response["X-Content-Type-Options"] = "nosniff"
        return response


class ProfileView(LoginRequiredMixin, View):
    """
    Unified profile: edit user info, configure LM Studio / OpenAI-compatible AI, connect multiple email mailboxes, and manage topics.
    """
    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        user_form = UserProfileForm(instance=request.user)
        lm_config_form = LMStudioConfigForm(initial={
            'lm_studio_url': profile.get_lm_studio_url(),
            'lm_studio_model': profile.get_lm_studio_model(),
        })
        edit_mailbox_id = request.GET.get('edit_mailbox')
        edit_mailbox = request.user.mailboxes.filter(id=edit_mailbox_id).first() if edit_mailbox_id else None
        mailbox_form = UserMailboxForm(instance=edit_mailbox)
        mailboxes = request.user.mailboxes.all()
        topic_form = TopicForm()
        topics = request.user.topics.all()

        return render(request, 'profile.html', {
            'profile': profile,
            'user_form': user_form,
            'lm_config_form': lm_config_form,
            'mailbox_form': mailbox_form,
            'mailboxes': mailboxes,
            'edit_mailbox': edit_mailbox,
            'topic_form': topic_form,
            'topics': topics,
        })

    def post(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)

        # 1. Update personal info
        if 'update_profile' in request.POST:
            user_form = UserProfileForm(request.POST, instance=request.user)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, "Personal info updated successfully.")
                return redirect('profile')

        # 2. Save or update LM Studio / OpenAI-compatible settings
        elif 'save_lm_config' in request.POST:
            lm_config_form = LMStudioConfigForm(request.POST)
            if lm_config_form.is_valid():
                url = lm_config_form.cleaned_data['lm_studio_url'].strip()
                model = lm_config_form.cleaned_data['lm_studio_model'].strip()
                api_key = lm_config_form.cleaned_data.get('lm_studio_api_key', '').strip()

                profile.lm_studio_url = url
                profile.lm_studio_model = model
                if api_key:
                    profile.set_lm_studio_api_key(api_key)
                profile.save()
                messages.success(request, f"LM Studio configuration saved successfully! (Endpoint: {url}, Model: {model})")
                return redirect('profile')

        # 3. Test LM Studio Connection
        elif 'test_lm_connection' in request.POST:
            url = request.POST.get('lm_studio_url', '').strip() or profile.get_lm_studio_url()
            model = request.POST.get('lm_studio_model', '').strip() or profile.get_lm_studio_model()
            api_key = request.POST.get('lm_studio_api_key', '').strip() or profile.get_lm_studio_api_key()

            diag = test_lm_studio_connection(api_url=url, api_key=api_key, model=model)
            if diag.get("success"):
                models_str = ", ".join(diag.get("models", [])) or "None returned"
                messages.success(
                    request,
                    f"⚡ Connection Successful ({diag.get('latency_ms')}ms)! "
                    f"Reachable at {diag.get('base_url')}. Loaded models: [{models_str}]"
                )
            else:
                messages.error(
                    request,
                    f"❌ Connection Failed: {diag.get('message')}. "
                    f"Ensure LM Studio is running on {url} with the local server started."
                )
            return redirect('profile')

        # 4. Reset LM Studio settings to local defaults
        elif 'reset_lm_config' in request.POST:
            profile.lm_studio_url = "http://127.0.0.1:1234/v1"
            profile.lm_studio_model = "qwen/qwen3-1.7b"
            profile.set_lm_studio_api_key(None)
            profile.save()
            messages.success(request, "LM Studio configuration reset to local defaults (http://127.0.0.1:1234/v1, qwen/qwen3-1.7b).")
            return redirect('profile')

        # 5. Toggle webhook for an existing mailbox
        elif 'update_mailbox_webhook' in request.POST:
            mailbox_id = request.POST.get('mailbox_id')
            mailbox = request.user.mailboxes.filter(id=mailbox_id).first()
            if mailbox:
                mailbox.webhook_enabled = request.POST.get('webhook_enabled') == 'on'
                mailbox.provider_type = mailbox.detect_provider_type()
                if mailbox.webhook_enabled and mailbox.should_use_webhook():
                    mailbox.webhook_status = 'pending'
                    mailbox.save(update_fields=['webhook_enabled', 'provider_type', 'webhook_status', 'updated_at'])
                    ok, detail = ensure_webhook_subscription(mailbox)
                    if ok:
                        messages.success(request, 'Webhook enabled and activated.')
                    else:
                        mailbox.webhook_status = 'error'
                        mailbox.webhook_last_error = detail
                        mailbox.save(update_fields=['webhook_status', 'webhook_last_error', 'updated_at'])
                        messages.warning(request, f'Webhook is enabled but setup needs attention: {detail}')
                else:
                    mailbox.webhook_status = 'disabled'
                    mailbox.save(update_fields=['webhook_enabled', 'provider_type', 'webhook_status', 'updated_at'])
                    messages.success(request, 'Webhook disabled.')
            return redirect('profile')

        # 6. Add or update an IMAP mailbox
        elif 'save_mailbox' in request.POST:
            mailbox_id = request.POST.get('mailbox_id')
            existing_mailbox = request.user.mailboxes.filter(id=mailbox_id).first() if mailbox_id else None
            mailbox_form = UserMailboxForm(request.POST, instance=existing_mailbox)
            if mailbox_form.is_valid():
                original_credentials = {
                    'password': existing_mailbox.password if existing_mailbox else '',
                    'provider_access_token': existing_mailbox.provider_access_token if existing_mailbox else '',
                    'provider_refresh_token': existing_mailbox.provider_refresh_token if existing_mailbox else '',
                }
                mailbox = mailbox_form.save(commit=False)
                mailbox.user = request.user
                mailbox.provider_type = mailbox.detect_provider_type()
                for field_name, original_value in original_credentials.items():
                    if not mailbox_form.cleaned_data.get(field_name) and original_value:
                        setattr(mailbox, field_name, original_value)
                mailbox.save()
                if mailbox.webhook_enabled and mailbox.should_use_webhook():
                    mailbox.webhook_status = 'pending'
                    mailbox.save(update_fields=['webhook_status', 'updated_at'])
                    ok, detail = ensure_webhook_subscription(mailbox)
                    if ok:
                        action = "updated" if existing_mailbox else "Added"
                        messages.success(request, f"Mailbox {action} and webhook trigger activated.")
                    else:
                        mailbox.webhook_status = 'error'
                        mailbox.webhook_last_error = detail
                        mailbox.save(update_fields=['webhook_status', 'webhook_last_error', 'updated_at'])
                        messages.warning(
                            request,
                            f"Mailbox {'updated' if existing_mailbox else 'added'}, but webhook setup failed ({detail}). Fallback polling will continue."
                        )
                else:
                    mailbox.webhook_status = "disabled"
                    mailbox.save(update_fields=["webhook_status", "updated_at"])
                    action = "updated" if existing_mailbox else "Added"
                    messages.success(request, f"Mailbox {action} ({mailbox.email_address}) successfully.")
                return redirect('profile')

        # 6. Disconnect / delete a mailbox
        elif 'delete_mailbox' in request.POST:
            mailbox_id = request.POST.get('mailbox_id')
            deleted, _ = request.user.mailboxes.filter(id=mailbox_id).delete()
            if deleted:
                messages.success(request, "Mailbox disconnected.")
            return redirect('profile')

        # 6. Create a new topic
        elif 'create_topic' in request.POST:
            topic_form = TopicForm(request.POST)
            if topic_form.is_valid():
                new_topic = topic_form.save(commit=False)
                new_topic.owner = request.user
                new_topic.save()
                messages.success(request, f"Topic '{new_topic.name}' created.")
                return redirect('profile')

        return self.get(request)


class SyncEmailsView(LoginRequiredMixin, View):
    """
    Queues a background sync for the logged-in user's active mailboxes
    instead of blocking the request on IMAP + LLM calls.
    """
    def post(self, request):
        mailboxes = UserMailbox.objects.filter(user=request.user, is_active=True)

        if not mailboxes.exists():
            messages.warning(request, "No active mailboxes to sync.")
            return redirect('inbox')

        for mailbox in mailboxes:
            sync_mailbox_task.delay(mailbox.id)

        messages.success(request, "Sync started — new emails will appear in a moment.")
        return redirect('inbox')


@method_decorator(csrf_exempt, name='dispatch')
class GmailWebhookView(View):
    """
    Handles Gmail Pub/Sub push notifications and triggers mailbox-scoped sync tasks.
    """
    def post(self, request):
        shared_token = getattr(settings, "GMAIL_WEBHOOK_SHARED_TOKEN", "") or ""
        header_token = request.headers.get("X-Notifier-Webhook-Token", "")

        if not shared_token or not secrets.compare_digest(shared_token, header_token):
            log_webhook_event(provider="gmail", status="rejected", detail="Invalid shared token", payload={})
            return HttpResponseForbidden("Forbidden")

        payload = parse_gmail_pubsub_payload(request.body)
        if not payload:
            log_webhook_event(provider="gmail", status="rejected", detail="Invalid Pub/Sub payload", payload={})
            return JsonResponse({"ok": False, "detail": "Invalid payload"}, status=400)

        email_address = (payload.get("emailAddress") or "").strip().lower()
        history_id = payload.get("historyId")
        if not email_address:
            log_webhook_event(provider="gmail", status="rejected", detail="Missing emailAddress in payload", payload=payload)
            return JsonResponse({"ok": False, "detail": "Missing emailAddress"}, status=400)

        mailbox = (
            UserMailbox.objects.filter(
                email_address__iexact=email_address,
                provider_type="gmail",
                webhook_enabled=True,
                is_active=True,
            )
            .order_by("-updated_at")
            .first()
        )
        if not mailbox:
            log_webhook_event(provider="gmail", status="rejected", detail=f"Mailbox not found for {email_address}", payload=payload)
            return JsonResponse({"ok": True, "detail": "No mailbox mapped"}, status=202)

        mailbox.webhook_last_event_at = timezone.now()
        mailbox.webhook_status = "active"
        mailbox.webhook_last_error = ""
        if history_id:
            mailbox.webhook_cursor = str(history_id)
        mailbox.save(update_fields=["webhook_last_event_at", "webhook_status", "webhook_last_error", "webhook_cursor", "updated_at"])

        trigger_context = {
            "provider": "gmail",
            "history_id": str(history_id) if history_id else "",
            "event_type": "gmail.watch.push",
        }
        sync_mailbox_task.delay(mailbox.id, trigger_context=trigger_context)
        log_webhook_event(
            mailbox=mailbox,
            provider="gmail",
            event_type="gmail.watch.push",
            status="queued",
            detail="Webhook accepted and sync task queued",
            payload={"history_id": history_id, "email_address": email_address},
        )
        return JsonResponse({"ok": True})


@method_decorator(csrf_exempt, name='dispatch')
class OutlookWebhookView(View):
    """
    Handles Microsoft Graph webhook validation + change notifications.
    """
    def get(self, request):
        validation_token = request.GET.get("validationToken")
        if validation_token:
            return HttpResponse(validation_token, content_type="text/plain")
        return JsonResponse({"ok": True})

    def post(self, request):
        validation_token = request.GET.get("validationToken")
        if validation_token:
            return HttpResponse(validation_token, content_type="text/plain")

        try:
            body = json.loads((request.body or b"{}").decode("utf-8"))
        except json.JSONDecodeError:
            log_webhook_event(provider="outlook", status="rejected", detail="Invalid JSON", payload={})
            return JsonResponse({"ok": False, "detail": "Invalid JSON"}, status=400)

        notifications = body.get("value") or []
        if not isinstance(notifications, list):
            log_webhook_event(provider="outlook", status="rejected", detail="Missing value[] notifications", payload=body)
            return JsonResponse({"ok": False, "detail": "Invalid payload"}, status=400)

        queued = 0
        rejected = 0
        for item in notifications:
            sub_id = item.get("subscriptionId") or ""
            if not sub_id:
                rejected += 1
                continue

            mailbox = (
                UserMailbox.objects.filter(
                    webhook_subscription_id=sub_id,
                    provider_type="outlook",
                    webhook_enabled=True,
                    is_active=True,
                )
                .order_by("-updated_at")
                .first()
            )
            if not mailbox:
                rejected += 1
                log_webhook_event(provider="outlook", status="rejected", detail=f"Unknown subscription {sub_id}", payload=item)
                continue

            expected_state = mailbox.get_webhook_secret_token()
            provided_state = item.get("clientState") or ""
            if not expected_state or not hmac.compare_digest(expected_state, provided_state):
                rejected += 1
                log_webhook_event(mailbox=mailbox, provider="outlook", status="rejected", detail="Invalid clientState", payload=item)
                continue

            resource_data = item.get("resourceData") or {}
            message_id = resource_data.get("id")
            delta_link = item.get("deltaLink") or mailbox.webhook_cursor
            mailbox.webhook_last_event_at = timezone.now()
            mailbox.webhook_status = "active"
            mailbox.webhook_last_error = ""
            mailbox.save(update_fields=["webhook_last_event_at", "webhook_status", "webhook_last_error", "updated_at"])

            trigger_context = {
                "provider": "outlook",
                "delta_token": delta_link,
                "message_ids": [message_id] if message_id else [],
                "event_type": item.get("changeType") or "updated",
            }
            sync_mailbox_task.delay(mailbox.id, trigger_context=trigger_context)
            queued += 1
            log_webhook_event(
                mailbox=mailbox,
                provider="outlook",
                event_type=trigger_context["event_type"],
                status="queued",
                detail="Webhook accepted and sync task queued",
                payload={"subscription_id": sub_id, "message_id": message_id},
            )

        return JsonResponse({"ok": True, "queued": queued, "rejected": rejected})


# --- Existing Topic CRUD views ---

class TopicListView(LoginRequiredMixin, ListView):
    context_object_name = 'all_topics'
    model = Topic
    template_name = 'topics.html'

    def get_queryset(self):
        return self.request.user.topics.all()


class TopicCreateView(LoginRequiredMixin, CreateView):
    model = Topic
    form_class = TopicForm
    template_name = 'create_topic.html'
    success_url = reverse_lazy('profile')

    def form_valid(self, form):
        self.object = form.save(commit=False)
        self.object.owner = self.request.user
        self.object.save()
        return super().form_valid(form)


class TopicDeleteView(LoginRequiredMixin, DeleteView):
    model = Topic
    success_url = reverse_lazy('profile')

    def get_queryset(self):
        return self.request.user.topics.all()


class TopicUpdateView(LoginRequiredMixin, UpdateView):
    model = Topic
    form_class = TopicForm
    template_name = 'edit_topic.html'
    success_url = reverse_lazy('profile')

    def get_queryset(self):
        return self.request.user.topics.all()


class TopicDetailView(LoginRequiredMixin, DetailView):
    model = Topic
    template_name = 'topic_detail.html'

    def get_queryset(self):
        return self.request.user.topics.all()
