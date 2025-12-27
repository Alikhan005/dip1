from django.conf import settings
from django.db import models
from catalog.models import Course, Topic


class Syllabus(models.Model):
    LANG_CHOICES = [
        ("ru", "Русский"),
        ("kz", "Казахский"),
        ("en", "English"),
    ]

    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        SUBMITTED_DEAN = "submitted_dean", "Отправлено декану"
        APPROVED_DEAN = "approved_dean", "Утверждено деканом"
        SUBMITTED_UMU = "submitted_umu", "Отправлено в УМУ"
        APPROVED_UMU = "approved_umu", "Утверждено УМУ"
        REJECTED = "rejected", "Отклонено"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="syllabi")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="syllabi")
    semester = models.CharField(max_length=50)  # например, Fall 2025
    academic_year = models.CharField(max_length=20)  # например, 2025_2026
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.DRAFT)
    total_weeks = models.PositiveIntegerField(default=15)

    main_language = models.CharField(max_length=5, choices=LANG_CHOICES, default="ru")

    pdf_file = models.FileField(upload_to="syllabi_pdfs/", blank=True, null=True)
    is_shared = models.BooleanField(default=False)
    version_number = models.PositiveIntegerField(default=1)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.course.code} {self.semester} {self.academic_year}"


class SyllabusTopic(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name="syllabus_topics")
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT)
    week_number = models.PositiveIntegerField()
    is_included = models.BooleanField(default=True)

    custom_title = models.CharField(max_length=255, blank=True)
    custom_hours = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering = ["week_number"]

    def get_title(self):
        if self.custom_title:
            return self.custom_title
        return self.topic.get_title(self.syllabus.main_language)
