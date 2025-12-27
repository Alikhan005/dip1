from django.urls import path

from .views import change_status_view

urlpatterns = [
    path(
        "syllabi/<int:pk>/status/<str:new_status>/",
        change_status_view,
        name="syllabus_change_status",
    ),
]
