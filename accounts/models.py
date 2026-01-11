from django.contrib.auth.hashers import check_password, make_password
from django.contrib.auth.models import AbstractUser
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils.translation import gettext_lazy as _
from django.utils import timezone


USERNAME_REGEX = "^[0-9A-Za-z@.+_\\-\u0401\u0451\u0410-\u042F\u0430-\u044F]+\\Z"
username_validator = RegexValidator(
    regex=USERNAME_REGEX,
    message=_(
        "Enter a valid username. This value may contain only letters, numbers, and @/./+/-/_ characters."
    ),
    code="invalid",
)


class User(AbstractUser):
    username = models.CharField(
        _("username"),
        max_length=150,
        unique=True,
        help_text=_("Required. 150 characters or fewer. Letters, digits and @/./+/-/_ only."),
        validators=[username_validator],
        error_messages={"unique": _("A user with that username already exists.")},
    )

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
        return self.role == self.Role.TEACHER

    @property
    def can_edit_content(self) -> bool:
        return self.role == self.Role.TEACHER

    @property
    def can_view_courses(self) -> bool:
        return self.role == self.Role.TEACHER

    @property
    def can_view_shared_courses(self) -> bool:
        return self.role == self.Role.TEACHER

    def __str__(self):
        return self.get_full_name() or self.username

    class Meta(AbstractUser.Meta):
        constraints = [
            models.UniqueConstraint(
                Lower("email"),
                name="unique_user_email_ci",
                condition=~Q(email=""),
            ),
        ]


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
