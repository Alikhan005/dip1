from django.conf import settings
from django.db import models
from catalog.models import Course, Topic


class Syllabus(models.Model):
    LANG_CHOICES = [
        ("ru", "Русский"),
        ("kz", "Казахский"),
        ("en", "English"),
    ]

    # Статусы согласования
    class Status(models.TextChoices):
        DRAFT = "draft", "Черновик"
        AI_CHECK = "ai_check", "На проверке ИИ"
        CORRECTION = "correction", "На доработке"
        REVIEW_DEAN = "review_dean", "Согласование: Декан"
        REVIEW_UMU = "review_umu", "Согласование: УМУ"
        APPROVED = "approved", "Утвержден"
        REJECTED = "rejected", "Отклонено (Архив)"

    course = models.ForeignKey(
        Course, 
        on_delete=models.CASCADE, 
        related_name="syllabi",
        verbose_name="Дисциплина"
    )
    creator = models.ForeignKey(
        settings.AUTH_USER_MODEL, 
        on_delete=models.CASCADE, 
        related_name="syllabi",
        verbose_name="Создатель"
    )
    semester = models.CharField("Семестр", max_length=50)  # например, Fall 2025
    academic_year = models.CharField("Учебный год", max_length=20)  # например, 2025-2026
    
    status = models.CharField(
        "Статус", 
        max_length=32, 
        choices=Status.choices, 
        default=Status.DRAFT
    )
    
    total_weeks = models.PositiveIntegerField("Количество недель", default=15)
    main_language = models.CharField(
        "Язык силлабуса", 
        max_length=5, 
        choices=LANG_CHOICES, 
        default="ru"
    )

    # ВАЖНО: blank=True, null=True позволяют создавать силлабус без файла (Конструктор)
    pdf_file = models.FileField(
        "Файл силлабуса", 
        upload_to="syllabi_pdfs/", 
        blank=True, 
        null=True
    )
    is_shared = models.BooleanField("Доступен другим?", default=False)
    version_number = models.PositiveIntegerField("Версия", default=1)

    ai_feedback = models.TextField("Отчет ИИ", blank=True, help_text="Замечания от автоматической проверки")

    # --- Детальные поля (заполняются или парсятся) ---
    credits_ects = models.CharField("Кредиты (ECTS)", max_length=20, blank=True)
    total_hours = models.PositiveIntegerField("Всего часов", blank=True, null=True)
    contact_hours = models.PositiveIntegerField("Аудиторные часы", blank=True, null=True)
    self_study_hours = models.PositiveIntegerField("СРО/СРОП", blank=True, null=True)
    prerequisites = models.TextField("Пререквизиты", blank=True)
    delivery_format = models.CharField("Формат обучения", max_length=100, blank=True)
    level = models.CharField("Уровень", max_length=100, blank=True)
    program_name = models.CharField("Образовательная программа", max_length=255, blank=True)
    instructor_name = models.CharField("Преподаватель", max_length=255, blank=True)
    instructor_contacts = models.TextField("Контакты преподавателя", blank=True)
    class_schedule = models.TextField("Расписание", blank=True)

    course_description = models.TextField("Описание курса", blank=True)
    course_goal = models.TextField("Цель курса", blank=True)
    learning_outcomes = models.TextField("Ожидаемые результаты", blank=True)
    teaching_methods = models.TextField("Методы обучения", blank=True)

    teaching_philosophy = models.TextField("Философия преподавания", blank=True)
    course_policy = models.TextField("Политика курса", blank=True)
    academic_integrity_policy = models.TextField("Академическая честность", blank=True)
    inclusive_policy = models.TextField("Инклюзивная политика", blank=True)
    assessment_policy = models.TextField("Политика оценивания", blank=True)
    grading_scale = models.TextField("Шкала оценки", blank=True)
    appendix = models.TextField("Приложения", blank=True)

    main_literature = models.TextField("Основная литература", blank=True)
    additional_literature = models.TextField("Дополнительная литература", blank=True)

    created_at = models.DateTimeField("Дата создания", auto_now_add=True)
    updated_at = models.DateTimeField("Дата обновления", auto_now=True)

    class Meta:
        verbose_name = "Силлабус"
        verbose_name_plural = "Силлабусы"
        ordering = ["-updated_at"]

    def __str__(self):
        return f"{self.course.code} | {self.semester} | {self.get_status_display()}"
    
    @property
    def is_editable(self):
        """Можно редактировать только в статусе Черновик или На доработке."""
        return self.status in [self.Status.DRAFT, self.Status.CORRECTION]


class SyllabusTopic(models.Model):
    syllabus = models.ForeignKey(Syllabus, on_delete=models.CASCADE, related_name="syllabus_topics")
    topic = models.ForeignKey(Topic, on_delete=models.PROTECT, verbose_name="Тема из каталога")
    week_number = models.PositiveIntegerField("Номер недели")
    is_included = models.BooleanField("Включено", default=True)

    custom_title = models.CharField("Кастомное название", max_length=255, blank=True)
    custom_hours = models.PositiveIntegerField("Часы (кастом)", null=True, blank=True)
    week_label = models.CharField("Метка недели", max_length=20, blank=True)
    tasks = models.TextField("Задания", blank=True)
    learning_outcomes = models.TextField("Результаты (тема)", blank=True)
    literature_notes = models.TextField("Литература (тема)", blank=True)
    assessment = models.TextField("Оценивание (тема)", blank=True)

    class Meta:
        ordering = ["week_number"]
        verbose_name = "Тема силлабуса"
        verbose_name_plural = "Темы силлабуса"

    def get_title(self):
        if self.custom_title:
            return self.custom_title
        # Безопасное получение названия, если у Topic есть метод get_title
        if hasattr(self.topic, 'get_title'):
             return self.topic.get_title(self.syllabus.main_language)
        return str(self.topic)


class SyllabusRevision(models.Model):
    syllabus = models.ForeignKey(
        Syllabus,
        on_delete=models.CASCADE,
        related_name="revisions",
    )
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    note = models.CharField(max_length=255, blank=True)
    version_number = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ревизия"
        verbose_name_plural = "История изменений"

    def __str__(self):
        return f"{self.syllabus_id} v{self.version_number}"