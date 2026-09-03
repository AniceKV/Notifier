from django import forms
from django.contrib.auth.models import User
from application.models import Topic, UserMailbox


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = ["name", "description"]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary',
                'placeholder': 'e.g. Machine Learning Jobs'
            }),
            'description': forms.Textarea(attrs={
                'class': 'w-full p-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary',
                'rows': 3,
                'placeholder': 'Describe keywords, categories or criteria...'
            }),
        }


class UserProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["username", "email", "first_name", "last_name"]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary'}),
            'email': forms.EmailInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary'}),
            'first_name': forms.TextInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary'}),
            'last_name': forms.TextInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary'}),
        }


class UserMailboxForm(forms.ModelForm):
    class Meta:
        model = UserMailbox
        fields = ["platform", "email_address", "password", "imap_server", "imap_port"]
        widgets = {
            'platform': forms.Select(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary'}),
            'email_address': forms.EmailInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary', 'placeholder': 'user@example.com'}),
            'password': forms.PasswordInput(render_value=True, attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary', 'placeholder': 'App password'}),
            'imap_server': forms.TextInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary', 'placeholder': 'imap.gmail.com'}),
            'imap_port': forms.NumberInput(attrs={'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary', 'placeholder': '993'}),
        }
        help_texts = {
            'password': 'For Gmail/Yahoo/Outlook, use an App Password generated in your account security settings. Stored encrypted.',
            'imap_server': 'e.g. imap.gmail.com, outlook.office365.com, imap.mail.yahoo.com, imap.mail.me.com',
        }


class GeminiApiKeyForm(forms.Form):
    gemini_api_key = forms.CharField(
        widget=forms.PasswordInput(render_value=False, attrs={
            'class': 'w-full h-9 px-3 bg-surface-container-lowest text-on-surface text-sm rounded border border-outline-variant focus:outline-none focus:ring-2 focus:ring-primary font-mono',
            'placeholder': 'AIzaSy... (Paste your Google Gemini API Key)',
            'autocomplete': 'off',
        }),
        required=True,
        help_text="Your key is encrypted with SHA-256 derived AES encryption and stored securely.",
    )