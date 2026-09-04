from django.shortcuts import render, redirect, get_object_or_404
from django.http import HttpResponse
from django.views import View
from django.views.generic import ListView, CreateView, UpdateView, DeleteView, DetailView
from django.urls import reverse_lazy
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib import messages
from datetime import timedelta
from django.utils import timezone

from application.models import Topic, Email, EmailMatch, UserMailbox, UserProfile
from application.forms import TopicForm, UserProfileForm, UserMailboxForm, GeminiApiKeyForm
from application.tasks import sync_mailbox_task


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
        relevant_matches = EmailMatch.objects.filter(user=request.user).select_related('email', 'topic').order_by('-created_at')

        # Collect available filter choices for the user
        user_topics = request.user.topics.all().order_by('name')

        platforms_from_emails = set(Email.objects.filter(owner=request.user).values_list('platform', flat=True).distinct())
        platforms_from_mailboxes = set(request.user.mailboxes.values_list('platform', flat=True).distinct())
        available_platforms = sorted(list(platforms_from_emails | platforms_from_mailboxes))

        # 1. Filter by Topic
        if selected_topic:
            try:
                topic_id = int(selected_topic)
                relevant_matches = relevant_matches.filter(topic_id=topic_id)
                all_emails = all_emails.filter(matches__topic_id=topic_id).distinct()
            except ValueError:
                relevant_matches = relevant_matches.filter(topic__name__iexact=selected_topic)
                all_emails = all_emails.filter(matches__topic__name__iexact=selected_topic).distinct()

        # 2. Filter by Platform
        if selected_platform:
            relevant_matches = relevant_matches.filter(email__platform__iexact=selected_platform)
            all_emails = all_emails.filter(platform__iexact=selected_platform)

        # 3. Filter by Time Window
        now = timezone.now()
        if selected_time in ('24h', 'today'):
            time_threshold = now - timedelta(days=1)
            relevant_matches = relevant_matches.filter(email__received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)
        elif selected_time == '7d':
            time_threshold = now - timedelta(days=7)
            relevant_matches = relevant_matches.filter(email__received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)
        elif selected_time == '30d':
            time_threshold = now - timedelta(days=30)
            relevant_matches = relevant_matches.filter(email__received_at__gte=time_threshold)
            all_emails = all_emails.filter(received_at__gte=time_threshold)

        active_filters_count = sum(1 for val in [selected_topic, selected_platform, selected_time] if val)

        context = {
            'tab': current_tab,
            'all_emails': all_emails,
            'relevant_matches': relevant_matches,
            'relevant_count': relevant_matches.count(),
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
    """
    def get(self, request, pk):
        email_obj = get_object_or_404(Email, pk=pk, owner=request.user)
        matches = EmailMatch.objects.filter(email=email_obj, user=request.user).select_related('topic')

        return render(request, 'email_detail.html', {
            'email': email_obj,
            'matches': matches,
        })


from django.views.decorators.clickjacking import xframe_options_exempt
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
    Unified profile: edit user info, configure BYOK Gemini API key, connect multiple email mailboxes, and manage topics.
    """
    def get(self, request):
        profile, _ = UserProfile.objects.get_or_create(user=request.user)
        user_form = UserProfileForm(instance=request.user)
        api_key_form = GeminiApiKeyForm()
        mailbox_form = UserMailboxForm()
        mailboxes = request.user.mailboxes.all()
        topic_form = TopicForm()
        topics = request.user.topics.all()

        return render(request, 'profile.html', {
            'profile': profile,
            'user_form': user_form,
            'api_key_form': api_key_form,
            'mailbox_form': mailbox_form,
            'mailboxes': mailboxes,
            'topic_form': topic_form,
            'topics': topics,
        })

    def post(self, request):
        # 1. Update personal info
        if 'update_profile' in request.POST:
            user_form = UserProfileForm(request.POST, instance=request.user)
            if user_form.is_valid():
                user_form.save()
                messages.success(request, "Personal info updated successfully.")
                return redirect('profile')

        # 2. BYOK: Save or update Gemini API key
        elif 'save_api_key' in request.POST:
            api_key_form = GeminiApiKeyForm(request.POST)
            if api_key_form.is_valid():
                raw_key = api_key_form.cleaned_data['gemini_api_key']
                profile, _ = UserProfile.objects.get_or_create(user=request.user)
                profile.set_gemini_api_key(raw_key)
                profile.save()
                messages.success(request, "Google Gemini API key saved and encrypted successfully.")
                return redirect('profile')

        # 3. BYOK: Remove Gemini API key
        elif 'delete_api_key' in request.POST:
            profile, _ = UserProfile.objects.get_or_create(user=request.user)
            profile.set_gemini_api_key(None)
            profile.save()
            messages.success(request, "Gemini API key removed.")
            return redirect('profile')

        # 4. Add an IMAP mailbox
        elif 'save_mailbox' in request.POST:
            mailbox_form = UserMailboxForm(request.POST)
            if mailbox_form.is_valid():
                mailbox = mailbox_form.save(commit=False)
                mailbox.user = request.user
                mailbox.save()
                messages.success(request, f"Added {mailbox.platform} mailbox ({mailbox.email_address}) successfully.")
                return redirect('profile')

        # 5. Disconnect / delete a mailbox
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
