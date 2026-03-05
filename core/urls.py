from django.urls import path

from .views import diagnostics, healthz, mark_notifications_read, workflow_guide

urlpatterns = [
    path("healthz/", healthz, name="healthz"),
    path("diagnostics/", diagnostics, name="diagnostics"),
    path("guide/", workflow_guide, name="workflow_guide"),
    path("notifications/mark-read/", mark_notifications_read, name="notifications_mark_read"),
]
