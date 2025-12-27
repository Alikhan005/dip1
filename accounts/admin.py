from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Роли и структура", {"fields": ("role", "faculty", "department")}),
    )
    list_display = ("username", "email", "role", "faculty", "department")
    list_filter = ("role", "faculty", "department")
