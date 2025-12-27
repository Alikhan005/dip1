from django.conf import settings
from django.db import models


class Course(models.Model):
    LANG_CHOICES = [
        ("ru", "Русский"),
        ("kz", "Казахский"),
        ("en", "English"),
    ]

    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="courses",
    )
    code = models.CharField(max_length=50)
    title_ru = models.CharField(max_length=255, blank=True)
    title_kz = models.CharField(max_length=255, blank=True)
    title_en = models.CharField(max_length=255, blank=True)

    description_ru = models.TextField(blank=True)
    description_kz = models.TextField(blank=True)
    description_en = models.TextField(blank=True)

    available_languages = models.CharField(
        max_length=50,
        help_text="Доступные языки, например: ru,kz,en",
    )

    is_shared = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.code}"

    def get_available_languages_list(self):
        return [x.strip() for x in self.available_languages.split(",") if x.strip()]

    @property
    def display_title(self):
        """Return the first non-empty localized title."""
        return self.title_ru or self.title_en or self.title_kz

    @property
    def available_languages_display(self):
        labels = dict(self.LANG_CHOICES)
        return ", ".join(labels.get(code, code) for code in self.get_available_languages_list())


class Topic(models.Model):
    class WeekType(models.TextChoices):
        LECTURE = "lecture", "Лекция"
        PRACTICE = "practice", "Практика"
        LAB = "lab", "Лабораторная"

    course = models.ForeignKey(Course, on_delete=models.CASCADE, related_name="topics")
    order_index = models.PositiveIntegerField(default=1)

    title_ru = models.CharField(max_length=255, blank=True)
    title_kz = models.CharField(max_length=255, blank=True)
    title_en = models.CharField(max_length=255, blank=True)

    description_ru = models.TextField(blank=True)
    description_kz = models.TextField(blank=True)
    description_en = models.TextField(blank=True)

    default_hours = models.PositiveIntegerField(default=2)
    week_type = models.CharField(max_length=32, choices=WeekType.choices, default=WeekType.LECTURE)
    is_active = models.BooleanField(default=True)

    def get_title(self, lang):
        mapping = {
            "ru": self.title_ru,
            "kz": self.title_kz,
            "en": self.title_en,
        }
        value = mapping.get(lang)
        if value:
            return value
        return self.title_ru or self.title_en or self.title_kz or "Без названия"

    def __str__(self):
        return f"{self.course.code} : {self.title_ru or self.title_en or 'Без темы'}"


class TopicLiterature(models.Model):
    class LitType(models.TextChoices):
        MAIN = "main", "Основная"
        ADDITIONAL = "additional", "Дополнительная"

    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="literature")
    title = models.CharField(max_length=255)
    author = models.CharField(max_length=255, blank=True)
    year = models.CharField(max_length=10, blank=True)
    lit_type = models.CharField(max_length=32, choices=LitType.choices, default=LitType.MAIN)


class TopicQuestion(models.Model):
    topic = models.ForeignKey(Topic, on_delete=models.CASCADE, related_name="questions")
    question_ru = models.TextField(blank=True)
    question_kz = models.TextField(blank=True)
    question_en = models.TextField(blank=True)
