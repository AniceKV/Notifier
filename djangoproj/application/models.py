from django.db import models
from django.contrib.auth.models import User
from typing import List, Any
import json

# Create your models here.

class Topic(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='topics')
    name = models.CharField(max_length=50)
    description = models.TextField(max_length=1000)

    def __str__(self):
        return self.name

    embedding = models.TextField(null=True, blank=True)

    similarity_threshold = models.FloatField(default=0.45)  # for embedding cosine score
    relevance_threshold = models.FloatField(default=0.50)   # for relevancy score

    def get_embedding_vector(self) -> List[float]:
        return json.loads(self.embedding) if self.embedding else None

    def set_embedding_vector(self, vec):
        self.embedding = json.dumps(vec)


class UserProfile(models.Model):
    """
    User settings including LM Studio / OpenAI-compatible local and remote LLM configuration.
    Sensitive credentials are encrypted at rest using SHA-256 derived AES/Fernet encryption.
    """
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    lm_studio_url = models.CharField(max_length=255, default="http://127.0.0.1:1234/v1", blank=True)
    lm_studio_model = models.CharField(max_length=150, default="qwen/qwen3-1.7b", blank=True)
    lm_studio_api_key = models.CharField(max_length=500, blank=True, null=True)
    gemini_api_key = models.CharField(max_length=500, blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def get_lm_studio_url(self) -> str:
        return (self.lm_studio_url or "http://127.0.0.1:1234/v1").strip()

    def get_lm_studio_model(self) -> str:
        return (self.lm_studio_model or "qwen/qwen3-1.7b").strip()

    def set_lm_studio_api_key(self, raw_key: str):
        from application.crypto import encrypt_credential
        if raw_key and raw_key.strip():
            self.lm_studio_api_key = encrypt_credential(raw_key.strip())
        else:
            self.lm_studio_api_key = None

    def get_lm_studio_api_key(self) -> str:
        from application.crypto import decrypt_credential
        if not self.lm_studio_api_key:
            return "lm-studio"
        return decrypt_credential(self.lm_studio_api_key)

    @property
    def has_lm_studio_custom_key(self) -> bool:
        return bool(self.lm_studio_api_key)

    @property
    def masked_lm_studio_api_key(self) -> str:
        key = self.get_lm_studio_api_key()
        if not key or key == "lm-studio":
            return "lm-studio (Default Local Key)"
        if len(key) <= 8:
            return "••••••••"
        return f"••••••••••••{key[-4:]}"

    def set_gemini_api_key(self, raw_key: str):
        from application.crypto import encrypt_credential
        if raw_key and raw_key.strip():
            self.gemini_api_key = encrypt_credential(raw_key.strip())
        else:
            self.gemini_api_key = None

    def get_gemini_api_key(self) -> str:
        from application.crypto import decrypt_credential
        if not self.gemini_api_key:
            return ""
        return decrypt_credential(self.gemini_api_key)

    @property
    def has_api_key(self) -> bool:
        return bool(self.gemini_api_key)

    @property
    def masked_gemini_api_key(self) -> str:
        key = self.get_gemini_api_key()
        if not key:
            return ""
        if len(key) <= 8:
            return "••••••••"
        return f"••••••••••••{key[-4:]}"

    def __str__(self):
        return f"Profile of {self.user.username}"


class UserMailbox(models.Model):
    """
    Platform-agnostic IMAP credentials per user.
    Passwords are encrypted at rest using SHA-256 derived AES/Fernet encryption.
    """
    PLATFORM_CHOICES = [
        ('Gmail', 'Gmail'),
        ('Outlook', 'Outlook / Hotmail / Office365'),
        ('Yahoo', 'Yahoo Mail'),
        ('iCloud', 'Apple iCloud'),
        ('Custom', 'Custom IMAP'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='mailboxes')
    platform = models.CharField(max_length=50, choices=PLATFORM_CHOICES, default='Gmail')
    email_address = models.EmailField()
    password = models.CharField(max_length=500)  # Encrypted App Password
    imap_server = models.CharField(max_length=150, default='imap.gmail.com')
    imap_port = models.IntegerField(default=993)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ('user', 'email_address')

    def save(self, *args, **kwargs):
        from application.crypto import encrypt_credential
        if self.password and not self.password.startswith("enc::"):
            self.password = encrypt_credential(self.password)
        super().save(*args, **kwargs)

    def get_decrypted_password(self) -> str:
        from application.crypto import decrypt_credential
        return decrypt_credential(self.password)

    def __str__(self):
        return f"{self.user.username} ({self.platform} - {self.email_address})"


class Email(models.Model):
    owner = models.ForeignKey(User, on_delete=models.CASCADE, related_name='emails')
    platform = models.CharField(max_length=50, default='Gmail')  # Name of platform (Gmail, Outlook, Yahoo, etc.)
    message_id = models.CharField(max_length=255, unique=True)  # IMAP Message-ID
    sender = models.CharField(max_length=255)
    subject = models.CharField(max_length=400)
    body = models.TextField()  # Raw or cleaned HTML/Plain text
    received_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"[{self.platform}] {self.subject[:50]}"


class EmailMatch(models.Model):
    email = models.ForeignKey(Email, on_delete=models.CASCADE, related_name='matches')
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name='matches')
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')

    # scores
    candidate_score = models.FloatField()
    matched_chunk = models.TextField()

    summary = models.TextField()
    match_reason = models.TextField()

    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('email', 'topic')

    def __str__(self):
        return f"{self.user.username} - {self.topic.name} - {self.email.subject[:30]}"

    @property
    def match_percentage(self):
        """Calculates a normalized match percentage for display based on embedding cosine similarity."""
        score = self.candidate_score
        if score is None:
            return 90
        if score <= 1.0:
            pct = int(min(score * 165, 99)) if score < 0.65 else int(min(score * 100, 99))
            return max(pct, 75)
        return min(int(score), 99)

    @property
    def formatted_summary_html(self):
        """
        Parses LLM markdown output into styled HTML matching the user's design palette:
        - Amber accent for SUMMARY heading with square dot
        - Sky/Cobalt blue accent for ACTION ITEMS & TAKEAWAYS heading
        - Clean em-dash bullets and high-contrast text
        """
        if not self.summary:
            return ""

        import html
        from django.utils.safestring import mark_safe

        lines = [line.strip() for line in self.summary.strip().splitlines()]
        output_parts = []
        in_list = False
        skip_section = False

        for line in lines:
            if not line:
                if in_list:
                    output_parts.append("</ul>")
                    in_list = False
                continue

            if line.startswith("#"):
                if in_list:
                    output_parts.append("</ul>")
                    in_list = False
                raw_heading = line.lstrip("#").strip()
                if "why this matched" in raw_heading.lower():
                    skip_section = True
                    continue
                else:
                    skip_section = False

                heading_text = html.escape(raw_heading)
                heading_lower = raw_heading.lower()

                indicator = '<span class="w-1.5 h-1.5 rounded-xs bg-cyan-400 inline-block shrink-0"></span>'
                title_color = "text-cyan-900 dark:text-cyan-100"

                output_parts.append(
                    f'<h4 class="font-bold {title_color} text-[11px] uppercase tracking-wider mt-3 first:mt-0 mb-1.5 flex items-center gap-1.5 font-mono">'
                    f'{indicator}<span>{heading_text}</span></h4>'
                )
            elif skip_section:
                continue
            elif line.startswith(("- ", "* ")):
                if not in_list:
                    output_parts.append('<ul class="space-y-1.5 my-1.5 pl-0.5">')
                    in_list = True
                bullet_content = html.escape(line[2:].strip())
                output_parts.append(
                    f'<li class="leading-relaxed flex items-baseline gap-2 text-xs">'
                    f'<span class="text-cyan-400/60 dark:text-cyan-400/70 select-none shrink-0 font-mono">—</span>'
                    f'<span class="text-on-surface">{bullet_content}</span></li>'
                )
            else:
                if in_list:
                    output_parts.append("</ul>")
                    in_list = False
                escaped_text = html.escape(line)
                output_parts.append(f'<p class="text-on-surface text-xs leading-relaxed mb-2">{escaped_text}</p>')

        if in_list:
            output_parts.append("</ul>")

        return mark_safe("".join(output_parts))

