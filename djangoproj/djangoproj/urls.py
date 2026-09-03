"""
URL configuration for djangoproj project.
"""
from django.contrib import admin
from django.urls import path, include

from application.views import (
    InboxView,
    EmailDetailView,
    EmailContentView,
    ProfileView,
    SyncEmailsView,
    TopicListView,
    TopicCreateView,
    TopicDeleteView,
    TopicUpdateView,
    TopicDetailView,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', InboxView.as_view(), name='inbox'),
    path('emails/', InboxView.as_view(), name='inbox'),
    path('emails/<int:pk>/', EmailDetailView.as_view(), name='email_detail'),
    path('emails/<int:pk>/content/', EmailContentView.as_view(), name='email_content'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('sync/', SyncEmailsView.as_view(), name='sync_emails'),

    # Topics
    path('topics/', TopicListView.as_view(), name='topics'),
    path('topics/create/', TopicCreateView.as_view(), name='create_topic'),
    path('topics/delete/<int:pk>/', TopicDeleteView.as_view(), name='delete_topic'),
    path('topics/edit/<int:pk>/', TopicUpdateView.as_view(), name='edit_topic'),
    path('topics/<int:pk>/', TopicDetailView.as_view(), name='topic_detail'),

    # Auth
    path('accounts/', include('django.contrib.auth.urls')),
]
