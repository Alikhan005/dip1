from django.urls import path
from . import views

urlpatterns = [
    path("ai-check/<int:syllabus_pk>/run/", views.run_check, name="ai_check_run"),
    path("ai-check/result/<int:pk>/", views.check_detail, name="ai_check_detail"),
    path("ai-assistant/", views.assistant_reply, name="ai_assistant"),
]
