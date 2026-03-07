from django import forms
from django.forms import inlineformset_factory

from .models import Course, Topic, TopicLiterature, TopicQuestion


def _decorate_field(field, placeholder: str = "", rows: int | None = None) -> None:
    widget = field.widget
    css_class = widget.attrs.get("class", "").strip()

    if isinstance(widget, forms.Select):
        css_class = f"{css_class} form-select".strip()
    elif isinstance(widget, forms.Textarea):
        css_class = f"{css_class} form-control".strip()
        if rows is not None:
            widget.attrs.setdefault("rows", rows)
    elif isinstance(widget, forms.CheckboxInput):
        css_class = f"{css_class} form-checkbox".strip()
    else:
        css_class = f"{css_class} form-control".strip()

    widget.attrs["class"] = css_class
    if placeholder and not isinstance(widget, forms.CheckboxInput):
        widget.attrs.setdefault("placeholder", placeholder)


class CourseForm(forms.ModelForm):
    languages = forms.MultipleChoiceField(
        choices=Course.LANG_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Языки курса",
    )

    class Meta:
        model = Course
        fields = [
            "code",
            "title_ru",
            "title_kz",
            "title_en",
            "description_ru",
            "description_kz",
            "description_en",
            "is_shared",
        ]
        labels = {
            "code": "Код дисциплины",
            "title_ru": "Название на русском языке",
            "title_kz": "Название на казахском языке",
            "title_en": "Название на английском языке",
            "description_ru": "Описание на русском языке",
            "description_kz": "Описание на казахском языке",
            "description_en": "Описание на английском языке",
            "is_shared": "Сделать курс доступным для коллег",
        }
        widgets = {
            "description_ru": forms.Textarea(attrs={"rows": 4}),
            "description_kz": forms.Textarea(attrs={"rows": 4}),
            "description_en": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["languages"].initial = self.instance.get_available_languages_list()

        placeholders = {
            "code": "Например: CSCI 2201",
            "title_ru": "Введите название курса на русском",
            "title_kz": "Введите название курса на казахском",
            "title_en": "Введите название курса на английском",
            "description_ru": "Кратко опишите содержание курса",
            "description_kz": "Краткое описание на казахском",
            "description_en": "Short course description in English",
        }

        for name, field in self.fields.items():
            _decorate_field(field, placeholder=placeholders.get(name, ""), rows=4 if "description_" in name else None)

        self.fields["languages"].help_text = "Отметьте языки, на которых будет доступен курс."
        self.fields["is_shared"].help_text = "Если включить, другие преподаватели смогут копировать этот курс."

    def save(self, commit=True):
        instance = super().save(commit=False)
        langs = self.cleaned_data.get("languages", [])
        instance.available_languages = ",".join(langs)
        if commit:
            instance.save()
        return instance


class TopicForm(forms.ModelForm):
    class Meta:
        model = Topic
        fields = [
            "order_index",
            "title_ru",
            "title_kz",
            "title_en",
            "description_ru",
            "description_kz",
            "description_en",
            "default_hours",
            "week_type",
            "is_active",
        ]
        labels = {
            "order_index": "Порядок темы",
            "title_ru": "Название темы на русском языке",
            "title_kz": "Название темы на казахском языке",
            "title_en": "Название темы на английском языке",
            "description_ru": "Описание на русском языке",
            "description_kz": "Описание на казахском языке",
            "description_en": "Описание на английском языке",
            "default_hours": "Количество часов",
            "week_type": "Тип занятия",
            "is_active": "Показывать тему в курсе",
        }
        widgets = {
            "description_ru": forms.Textarea(attrs={"rows": 3}),
            "description_kz": forms.Textarea(attrs={"rows": 3}),
            "description_en": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        placeholders = {
            "order_index": "1",
            "title_ru": "Введите название темы на русском",
            "title_kz": "Введите название темы на казахском",
            "title_en": "Введите название темы на английском",
            "description_ru": "Опишите тему и её содержание",
            "description_kz": "Описание темы на казахском",
            "description_en": "Topic description in English",
            "default_hours": "2",
        }

        for name, field in self.fields.items():
            _decorate_field(field, placeholder=placeholders.get(name, ""), rows=3 if "description_" in name else None)


class TopicLiteratureForm(forms.ModelForm):
    class Meta:
        model = TopicLiterature
        fields = ["title", "author", "year", "lit_type"]
        labels = {
            "title": "Название источника",
            "author": "Автор",
            "year": "Год",
            "lit_type": "Тип литературы",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "title": "Название книги, статьи или ресурса",
            "author": "Фамилия и инициалы",
            "year": "2025",
        }
        for name, field in self.fields.items():
            _decorate_field(field, placeholder=placeholders.get(name, ""))


class TopicQuestionForm(forms.ModelForm):
    class Meta:
        model = TopicQuestion
        fields = ["question_ru", "question_kz", "question_en"]
        labels = {
            "question_ru": "Вопрос на русском языке",
            "question_kz": "Вопрос на казахском языке",
            "question_en": "Вопрос на английском языке",
        }
        widgets = {
            "question_ru": forms.Textarea(attrs={"rows": 2}),
            "question_kz": forms.Textarea(attrs={"rows": 2}),
            "question_en": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "question_ru": "Введите контрольный вопрос",
            "question_kz": "Сұрақты енгізіңіз",
            "question_en": "Enter a control question",
        }
        for name, field in self.fields.items():
            _decorate_field(field, placeholder=placeholders.get(name, ""), rows=2)


TopicLiteratureFormSet = inlineformset_factory(
    Topic,
    TopicLiterature,
    form=TopicLiteratureForm,
    extra=1,
    can_delete=True,
)

TopicQuestionFormSet = inlineformset_factory(
    Topic,
    TopicQuestion,
    form=TopicQuestionForm,
    extra=1,
    can_delete=True,
)
