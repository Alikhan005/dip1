from django.contrib import admin

from .models import Syllabus, SyllabusTopic, SyllabusRevision


@admin.register(Syllabus)
class SyllabusAdmin(admin.ModelAdmin):
    list_display = ("course", "semester", "academic_year", "status", "creator", "updated_at")
    list_filter = ("status", "main_language")
    search_fields = ("course__code", "course__title_ru", "course__title_en")


@admin.register(SyllabusTopic)
class SyllabusTopicAdmin(admin.ModelAdmin):
    list_display = ("syllabus", "week_number", "topic", "custom_hours", "is_included")
    list_filter = ("syllabus",)
    search_fields = ("syllabus__course__code", "topic__title_ru", "topic__title_en")


@admin.register(SyllabusRevision)
class SyllabusRevisionAdmin(admin.ModelAdmin):
    list_display = ("syllabus", "version_number", "changed_by", "created_at", "note")
    list_filter = ("created_at",)
    search_fields = ("syllabus__course__code", "note", "changed_by__username")
