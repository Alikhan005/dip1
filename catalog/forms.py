from django import forms
from django.forms import inlineformset_factory
from .models import Course, Topic, TopicLiterature, TopicQuestion


class CourseForm(forms.ModelForm):
    languages = forms.MultipleChoiceField(
        choices=Course.LANG_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        label="Доступные языки",
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields["languages"].initial = self.instance.get_available_languages_list()

    def clean(self):
        data = super().clean()
        langs = self.cleaned_data.get("languages", [])
        self.instance.available_languages = ",".join(langs)
        return data


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


TopicLiteratureFormSet = inlineformset_factory(
    Topic,
    TopicLiterature,
    fields=["title", "author", "year", "lit_type"],
    extra=1,
    can_delete=True,
)

TopicQuestionFormSet = inlineformset_factory(
    Topic,
    TopicQuestion,
    fields=["question_ru", "question_kz", "question_en"],
    extra=1,
    can_delete=True,
)
