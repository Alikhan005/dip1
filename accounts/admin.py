from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    # Добавляем наши кастомные поля (роль, факультет, кафедра) в форму редактирования
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Роли и структура", {"fields": ("role", "faculty", "department")}),
    )
    
    # Настраиваем отображение списка пользователей
    list_display = ("username", "email", "first_name", "last_name", "role", "faculty", "department", "is_active")
    list_filter = ("role", "faculty", "department", "is_active")
    search_fields = ("username", "email", "first_name", "last_name")