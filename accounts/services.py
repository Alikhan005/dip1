import random
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
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
        verification = EmailVerification.objects.filter(user=user).first()
    if verification is None:
        verification = EmailVerification(user=user)

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


def resolve_from_email() -> str:
    default_from = (getattr(settings, "DEFAULT_FROM_EMAIL", "") or "").strip()
    if default_from:
        return default_from
    host_user = (getattr(settings, "EMAIL_HOST_USER", "") or "").strip()
    return host_user or "AlmaU Syllabus <noreply@example.com>"


def send_verification_email(user, code: str, ttl_minutes: int) -> None:
    if not user.email:
        raise ValueError("User email is missing.")

    context = {
        "user": user,
        "code": code,
        "ttl_minutes": ttl_minutes,
    }
    subject = "Подтверждение email AlmaU Syllabus"
    text_body = render_to_string("registration/verify_email_email.txt", context).strip()
    html_body = render_to_string("registration/verify_email_email.html", context)
    from_email = resolve_from_email()
    email = EmailMultiAlternatives(
        subject=subject,
        body=text_body,
        from_email=from_email,
        to=[user.email],
    )
    email.attach_alternative(html_body, "text/html")
    email.send(fail_silently=False)
