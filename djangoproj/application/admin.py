from django.contrib import admin
from application.models import Topic, Email, EmailMatch, UserMailbox, WebhookEvent

admin.site.register(Topic)
admin.site.register(Email)
admin.site.register(EmailMatch)
admin.site.register(UserMailbox)
admin.site.register(WebhookEvent)
