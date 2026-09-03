from django.contrib import admin
from application.models import Topic, Email, EmailMatch, UserMailbox

admin.site.register(Topic)
admin.site.register(Email)
admin.site.register(EmailMatch)
admin.site.register(UserMailbox)
