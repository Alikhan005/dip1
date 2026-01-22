from django.contrib import admin

from .models import SyllabusAuditLog, SyllabusStatusLog


@admin.register(SyllabusStatusLog)
class SyllabusStatusLogAdmin(admin.ModelAdmin):
    list_display = ("syllabus", "from_status", "to_status", "changed_by", "changed_at")
    list_filter = ("to_status",)
    search_fields = ("syllabus__course__code", "changed_by__username")


@admin.register(SyllabusAuditLog)
class SyllabusAuditLogAdmin(admin.ModelAdmin):
    list_display = ("syllabus", "action", "actor", "created_at")
    list_filter = ("action",)
    search_fields = ("syllabus__course__code", "actor__username")
