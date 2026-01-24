from django import forms

from .models import Announcement


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ["title", "body"]
        widgets = {
            "title": forms.TextInput(attrs={"placeholder": "Заголовок", "maxlength": 160}),
            "body": forms.Textarea(attrs={"rows": 3, "placeholder": "Текст объявления"}),
        }
