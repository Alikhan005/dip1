import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import send_mail
from django.utils import timezone

from .models import EmailVerification


def _settings_int(name: str, default: int) -> int:
    value = getattr(settings, name, default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def generate_code() -> str:
    return f"{random.randint(0, 999999):06d}"


def create_or_refresh_verification(user, verification: EmailVerification | None = None) -> tuple[str, int]:
    code = generate_code()
    now = timezone.now()
    ttl_minutes = _settings_int("EMAIL_VERIFICATION_TTL_MINUTES", 15)
    expires_at = now + timedelta(minutes=ttl_minutes)

    if verification is None:
        verification, _ = EmailVerification.objects.get_or_create(user=user)

    verification.set_code(code)
    verification.expires_at = expires_at
    verification.last_sent_at = now
    verification.attempts = 0
    verification.verified_at = None
    verification.save()
    return code, ttl_minutes


def can_resend(verification: EmailVerification) -> bool:
    cooldown = _settings_int("EMAIL_VERIFICATION_RESEND_SECONDS", 60)
    return (timezone.now() - verification.last_sent_at) >= timedelta(seconds=cooldown)


def send_verification_email(user, code: str, ttl_minutes: int) -> None:
    if not user.email:
        raise ValueError("User email is missing.")

    subject = "Подтверждение email AlmaU Syllabus"
    message = (
        f"Ваш код подтверждения: {code}\n"
        f"Код действует {ttl_minutes} минут."
    )
    send_mail(
        subject,
        message,
        settings.DEFAULT_FROM_EMAIL,
        [user.email],
        fail_silently=False,
    )
