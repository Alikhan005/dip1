from django.urls import path
from . import views

urlpatterns = [
    # Список всех силлабусов
    path("", views.syllabi_list, name="syllabi_list"),
    path("shared/", views.shared_syllabi_list, name="shared_syllabi_list"),

    # === ИСПРАВЛЕНИЕ: УБРАЛИ СТАРЫЙ ПУТЬ create/ ===
    # Раньше тут был path("create/", ...), но мы разделили его на два нижних:

    # 1. Путь для КОНСТРУКТОРА (ручное создание)
    path('create/manual/', views.create_constructor_view, name='create_constructor'),
    
    # 2. Путь для ЗАГРУЗКИ (Импорт файла для ИИ)
    path('create/upload/', views.upload_pdf_view, name='upload_pdf'),
    
    # Детали и PDF
    path("<int:pk>/", views.syllabus_detail, name="syllabus_detail"),
    path("<int:pk>/pdf/", views.syllabus_pdf, name="syllabus_pdf"),

    # Действия (Workflow и кнопки)
    path("<int:pk>/send_ai/", views.send_to_ai_check, name="send_to_ai_check"),
    path("<int:pk>/status/<str:new_status>/", views.syllabus_change_status, name="syllabus_change_status"),
    path("<int:pk>/upload/", views.syllabus_upload_file, name="syllabus_upload_file"),
    path("<int:pk>/share/", views.syllabus_toggle_share, name="syllabus_toggle_share"),

    # Редактирование (заглушки, которые перекидывают обратно)
    path("<int:pk>/edit-details/", views.syllabus_edit_details, name="syllabus_edit_details"),
    path("<int:pk>/edit-topics/", views.syllabus_edit_topics, name="syllabus_edit_topics"),
]