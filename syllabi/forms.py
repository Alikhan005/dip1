from django import forms
from catalog.models import Course

from .models import Syllabus


class SyllabusForm(forms.ModelForm):
    copy_from = forms.ModelChoiceField(
        queryset=Syllabus.objects.none(),
        required=False,
        label="Использовать прошлый силлабус",
        help_text="Можно выбрать силлабус этого же курса и взять его структуру.",
    )
    prefill_topics = forms.BooleanField(
        required=False,
        initial=True,
        label="Заполнить темы из курса",
        help_text="Создать темы по умолчанию, чтобы сразу редактировать.",
    )

    class Meta:
        model = Syllabus
        fields = [
            "course",
            "semester",
            "academic_year",
            "total_weeks",
            "main_language",
            "pdf_file",
        ]
        labels = {
            "course": "Дисциплина",
            "pdf_file": "Старый PDF (необязательно)",
        }
        help_texts = {
            "pdf_file": (
                "Старый PDF хранится для справки. Редактирование идет в конструкторе тем и "
                "разделов; финальный PDF можно заменить после согласования."
            ),
        }

    def __init__(self, *args, **kwargs):
        user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)
        if user:
            if getattr(user, "role", None) == "admin":
                self.fields["course"].queryset = Course.objects.all()
                self.fields["copy_from"].queryset = Syllabus.objects.select_related("course", "creator")
            else:
                self.fields["course"].queryset = user.courses.all()
                self.fields["copy_from"].queryset = (
                    Syllabus.objects.filter(creator=user).select_related("course", "creator")
                )
        self.fields["course"].empty_label = "Выберите дисциплину"
        self.fields["copy_from"].empty_label = "Не использовать"
        self.fields["main_language"].widget = forms.Select(choices=Syllabus.LANG_CHOICES)

    def clean(self):
        data = super().clean()
        course = data.get("course")
        copy_from = data.get("copy_from")
        if course and copy_from and copy_from.course_id != course.id:
            self.add_error("copy_from", "Выберите силлабус этого же курса.")
        return data


class SyllabusDetailsForm(forms.ModelForm):
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
            "prerequisites": forms.Textarea(attrs={"rows": 2}),
            "instructor_contacts": forms.Textarea(attrs={"rows": 2}),
            "class_schedule": forms.Textarea(attrs={"rows": 2}),
            "course_description": forms.Textarea(attrs={"rows": 4}),
            "course_goal": forms.Textarea(attrs={"rows": 3}),
            "learning_outcomes": forms.Textarea(attrs={"rows": 4}),
            "teaching_methods": forms.Textarea(attrs={"rows": 3}),
            "teaching_philosophy": forms.Textarea(attrs={"rows": 4}),
            "course_policy": forms.Textarea(attrs={"rows": 4}),
            "academic_integrity_policy": forms.Textarea(attrs={"rows": 4}),
            "inclusive_policy": forms.Textarea(attrs={"rows": 4}),
            "assessment_policy": forms.Textarea(attrs={"rows": 4}),
            "grading_scale": forms.Textarea(attrs={"rows": 6}),
            "appendix": forms.Textarea(attrs={"rows": 4}),
            "main_literature": forms.Textarea(attrs={"rows": 4}),
            "additional_literature": forms.Textarea(attrs={"rows": 4}),
        }
