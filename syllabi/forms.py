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
            "pdf_file": "Старый PDF (необязательно)",
        }
        help_texts = {
            "pdf_file": "Можно загрузить прошлую версию, чтобы заменить ее позже.",
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
        self.fields["course"].empty_label = "Выберите курс"
        self.fields["copy_from"].empty_label = "Не использовать"
        self.fields["main_language"].widget = forms.Select(choices=Syllabus.LANG_CHOICES)

    def clean(self):
        data = super().clean()
        course = data.get("course")
        copy_from = data.get("copy_from")
        if course and copy_from and copy_from.course_id != course.id:
            self.add_error("copy_from", "Выберите силлабус этого же курса.")
        return data
