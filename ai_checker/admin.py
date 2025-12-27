from django.contrib import admin

from .models import AiCheckResult


@admin.register(AiCheckResult)
class AiCheckResultAdmin(admin.ModelAdmin):
    list_display = ("syllabus", "model_name", "created_at")
    search_fields = ("syllabus__course__code", "model_name")
