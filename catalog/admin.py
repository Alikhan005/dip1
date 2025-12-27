from django.contrib import admin
from .models import Course, Topic, TopicLiterature, TopicQuestion

class TopicLiteratureInline(admin.TabularInline):
    model = TopicLiterature
    extra = 1

class TopicQuestionInline(admin.TabularInline):
    model = TopicQuestion
    extra = 1

@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    list_display = ("code", "title_ru", "owner", "is_shared")
    list_filter = ("is_shared",)
    search_fields = ("code", "title_ru", "title_en")

@admin.register(Topic)
class TopicAdmin(admin.ModelAdmin):
    list_display = ("course", "order_index", "title_ru", "week_type", "is_active")
    list_filter = ("course", "week_type", "is_active")
    inlines = [TopicLiteratureInline, TopicQuestionInline]
