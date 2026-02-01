from django import forms
from catalog.models import Course
from .models import Syllabus

class SyllabusForm(forms.ModelForm):
    """
    Основная форма для загрузки силлабуса.
    Реализует подход 'File-First': преподаватель выбирает курс и сразу грузит файл.
    """
    class Meta:
        model = Syllabus
        fields = [
            "course",
            "semester",
            "academic_year",
            "main_language",
            "pdf_file",
        ]
        widgets = {
            "course": forms.Select(attrs={"class": "form-control"}),
            "semester": forms.TextInput(attrs={"class": "form-control", "placeholder": "Fall 2025"}),
            "academic_year": forms.TextInput(attrs={"class": "form-control", "placeholder": "2025-2026"}),
            "main_language": forms.Select(attrs={"class": "form-select"}),
            # Принимаем PDF, Docx, Doc
            "pdf_file": forms.FileInput(attrs={"class": "form-control", "accept": ".pdf,.docx,.doc"}),
        }
        labels = {
            "course": "Дисциплина",
            "semester": "Семестр",
            "academic_year": "Учебный год",
            "main_language": "Язык силлабуса",
            "pdf_file": "Файл силлабуса (PDF или Word)",
        }
        help_texts = {
            "pdf_file": "Загрузите готовый файл. Система автоматически отправит его на проверку ИИ.",
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        
        # Самое важное: делаем файл ОБЯЗАТЕЛЬНЫМ
        self.fields['pdf_file'].required = True
        
        if user:
            # Фильтрация курсов: Админ видит всё, Препод — только свои
            if getattr(user, "role", None) in ["admin", "dean", "umu"] or user.is_superuser:
                self.fields["course"].queryset = Course.objects.all()
            else:
                self.fields["course"].queryset = user.courses.all()
        
        self.fields["course"].empty_label = "Выберите дисциплину"


class SyllabusDetailsForm(forms.ModelForm):
    """
    Форма для редактирования деталей.
    Нужна, если преподаватель захочет поправить метаданные после загрузки,
    или если мы потом прикрутим парсинг полей из PDF.
    """
    class Meta:
        model = Syllabus
        fields = [
            "credits_ects",
            "total_hours",
            "contact_hours",
            "self_study_hours",
            "prerequisites",
            "delivery_format",
            "level",
            "program_name",
            "instructor_name",
            "instructor_contacts",
            "class_schedule",
            "course_description",
            "course_goal",
            "learning_outcomes",
            "teaching_methods",
            "teaching_philosophy",
            "course_policy",
            "academic_integrity_policy",
            "inclusive_policy",
            "assessment_policy",
            "grading_scale",
            "appendix",
            "main_literature",
            "additional_literature",
        ]
        labels = {
            "credits_ects": "Кредиты (ECTS)",
            "total_hours": "Всего часов",
            "contact_hours": "Аудиторные часы",
            "self_study_hours": "Самостоятельная работа (СРОП, СРО)",
            "prerequisites": "Пререквизиты",
            "delivery_format": "Формат обучения",
            "level": "Уровень обучения",
            "program_name": "Образовательная программа",
            "instructor_name": "Преподаватель",
            "instructor_contacts": "Контакты преподавателя",
            "class_schedule": "Время и место проведения занятий",
            "course_description": "Краткое описание курса",
            "course_goal": "Цель курса",
            "learning_outcomes": "Ожидаемые результаты",
            "teaching_methods": "Методы обучения",
            "teaching_philosophy": "Философия преподавания и обучения",
            "course_policy": "Политика курса",
            "academic_integrity_policy": "Академическая честность и использование ИИ",
            "inclusive_policy": "Инклюзивное академическое сообщество",
            "assessment_policy": "Политика оценивания",
            "grading_scale": "Балльно-рейтинговая шкала",
            "appendix": "Приложения и рубрикаторы",
            "main_literature": "Обязательная литература",
            "additional_literature": "Дополнительная литература",
        }
        widgets = {
            "prerequisites": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "instructor_contacts": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "class_schedule": forms.Textarea(attrs={"rows": 2, "class": "form-control"}),
            "course_description": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "course_goal": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "learning_outcomes": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "teaching_methods": forms.Textarea(attrs={"rows": 3, "class": "form-control"}),
            "teaching_philosophy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "course_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "academic_integrity_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "inclusive_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "assessment_policy": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "grading_scale": forms.Textarea(attrs={"rows": 6, "class": "form-control"}),
            "appendix": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "main_literature": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
            "additional_literature": forms.Textarea(attrs={"rows": 4, "class": "form-control"}),
        }