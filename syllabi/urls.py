from django.urls import path
from . import views

urlpatterns = [
    path("", views.syllabi_list, name="syllabi_list"),
    path("shared/", views.shared_syllabi_list, name="shared_syllabi_list"),
    path("create/", views.syllabus_create, name="syllabus_create"),
    path("<int:pk>/", views.syllabus_detail, name="syllabus_detail"),
    path("<int:pk>/edit-details/", views.syllabus_edit_details, name="syllabus_edit_details"),
    path("<int:pk>/edit-topics/", views.syllabus_edit_topics, name="syllabus_edit_topics"),
    path("<int:pk>/pdf/", views.syllabus_pdf, name="syllabus_pdf"),
    
    # --- НОВЫЙ МАРШРУТ (ВАЖНО) ---
    path("<int:pk>/send-ai/", views.send_to_ai_check, name="syllabus_send_ai"),
    
    path("<int:pk>/status/<str:new_status>/", views.syllabus_change_status, name="syllabus_change_status"),
    path("<int:pk>/upload/", views.syllabus_upload_file, name="syllabus_upload_file"),
    path("<int:pk>/share/", views.syllabus_toggle_share, name="syllabus_toggle_share"),
]