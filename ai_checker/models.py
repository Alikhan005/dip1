from django.db import models
from syllabi.models import Syllabus

class AiCheckResult(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name="ai_checks")
    created_at = models.DateTimeField(auto_now_add=True)
    model_name = models.CharField(max_length=255)
    summary = models.TextField()
    raw_result = models.JSONField()
