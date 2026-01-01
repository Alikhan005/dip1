from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    class Role(models.TextChoices):
        TEACHER = "teacher", "Преподаватель"
        PROGRAM_LEADER = "program_leader", "Руководитель программы"
        DEAN = "dean", "Декан"
        UMU = "umu", "УМУ"
        ADMIN = "admin", "Админ"

    role = models.CharField(
        max_length=32,
        choices=Role.choices,
        default=Role.TEACHER,
    )

    faculty = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    email_verified = models.BooleanField(default=False)

    @property
    def is_teacher_like(self) -> bool:
        return self.role in {self.Role.TEACHER, self.Role.DEAN}

    @property
    def can_edit_content(self) -> bool:
        return self.role in {self.Role.TEACHER, self.Role.DEAN, self.Role.ADMIN}

    @property
    def can_view_courses(self) -> bool:
        return self.role in {self.Role.TEACHER, self.Role.DEAN, self.Role.ADMIN}

    @property
    def can_view_shared_courses(self) -> bool:
        return self.role in {
            self.Role.TEACHER,
            self.Role.PROGRAM_LEADER,
            self.Role.DEAN,
            self.Role.ADMIN,
        }

    def __str__(self):
        return self.get_full_name() or self.username


class EmailVerification(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="email_verification")
    code = models.CharField(max_length=128)
    created_at = models.DateTimeField(auto_now_add=True)
    last_sent_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    verified_at = models.DateTimeField(null=True, blank=True)

    def set_code(self, raw_code: str) -> None:
        self.code = make_password(raw_code)

    def check_code(self, raw_code: str) -> bool:
        return check_password(raw_code, self.code)

    def mark_verified(self) -> None:
        self.verified_at = timezone.now()

    def is_expired(self) -> bool:
        return timezone.now() >= self.expires_at

    def __str__(self):
        return f"EmailVerification<{self.user_id}>"
