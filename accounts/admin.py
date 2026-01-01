from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import EmailVerification, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    fieldsets = BaseUserAdmin.fieldsets + (
        ("Роли и структура", {"fields": ("role", "faculty", "department", "email_verified")}),
    )
    list_display = ("username", "email", "email_verified", "role", "faculty", "department")
    list_filter = ("role", "faculty", "department", "email_verified")


@admin.register(EmailVerification)
class EmailVerificationAdmin(admin.ModelAdmin):
    list_display = ("user", "expires_at", "verified_at", "attempts", "last_sent_at")
    search_fields = ("user__username", "user__email")

