from django.conf import settings
from django.db import models

from syllabi.models import Syllabus


class SyllabusStatusLog(models.Model):
    syllabus = models.ForeignKey(
        "syllabi.Syllabus",
        on_delete=models.CASCADE,
        related_name="status_logs",
    )
    from_status = models.CharField(max_length=32, blank=True)
    to_status = models.CharField(max_length=32)
    comment = models.TextField(blank=True)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    changed_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-changed_at"]

    def __str__(self):
        return f"{self.syllabus_id}, {self.from_status} -> {self.to_status}"

    @staticmethod
    def _status_label(value: str) -> str:
        if not value:
            return "-"
        try:
            return Syllabus.Status(value).label
        except ValueError:
            return value

    @property
    def from_status_label(self) -> str:
        return self._status_label(self.from_status)

    @property
    def to_status_label(self) -> str:
        return self._status_label(self.to_status)


class SyllabusAuditLog(models.Model):
    class Action(models.TextChoices):
        DETAILS_UPDATED = "details_updated", "Обновлены разделы"
        TOPICS_UPDATED = "topics_updated", "Обновлены темы"
        TOPICS_CLEARED = "topics_cleared", "Темы очищены"
        PDF_UPLOADED = "pdf_uploaded", "Загружен PDF"
        STATUS_CHANGED = "status_changed", "Сменен статус"

    syllabus = models.ForeignKey(
        "syllabi.Syllabus",
        on_delete=models.CASCADE,
        related_name="audit_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    action = models.CharField(max_length=32, choices=Action.choices)
    message = models.TextField(blank=True)
    metadata = models.JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.syllabus_id} {self.action}"
