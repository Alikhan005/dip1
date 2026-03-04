import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction

from syllabi.models import Syllabus

from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)
User = get_user_model()
_ALLOWED_STATUSES = {choice[0] for choice in Syllabus.Status.choices}
_REVIEW_STATUSES = {Syllabus.Status.REVIEW_DEAN, Syllabus.Status.REVIEW_UMU}


def _reviewer_label(user) -> str:
    role = getattr(user, "role", "")
    if role == "umu":
        return "УМУ"
    if role == "dean":
        return "Деканат"
    if role == "admin":
        return "Администратор"
    return user.get_full_name() or getattr(user, "username", "") or "Проверяющий"


def _status_label(status: str) -> str:
    """Return a human-readable status label when possible."""
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status


def _collect_role_emails(role_key: str) -> list[str]:
    """Collect active user emails by role key (e.g. dean, umu)."""
    qs = User.objects.filter(is_active=True, role=role_key).exclude(email="")
    emails = list(qs.values_list("email", flat=True))

    if not emails:
        logger.warning("No active users with role '%s' were found for notifications.", role_key)

    return emails


def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    """Send email without breaking workflow on notification failures."""
    if not recipients:
        return

    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@almau.edu.kz")

    try:
        send_mail(
            subject=subject,
            message=message + "\n\n--\nAlmaU Syllabus System",
            from_email=from_email,
            recipient_list=recipients,
            fail_silently=True,
        )
        logger.info("Notification '%s' sent to: %s", subject, recipients)
    except Exception as exc:
        logger.error("Email notification error: %s", exc)


def _notify_on_status_change(syllabus: Syllabus, new_status: str, comment: str = "") -> None:
    """Send role-based notifications for status transitions."""
    try:
        subject = ""
        message = ""
        recipients: list[str] = []

        if new_status == Syllabus.Status.REVIEW_DEAN:
            recipients = _collect_role_emails("dean")
            subject = f"Syllabus requires dean review: {syllabus.course.code}"
            message = (
                "A syllabus has been submitted for your review.\n"
                f"Course: {syllabus.course.display_title}\n"
                f"Author: {syllabus.creator.get_full_name() or syllabus.creator.username}"
            )

        elif new_status == Syllabus.Status.REVIEW_UMU:
            recipients = _collect_role_emails("umu")
            subject = f"Syllabus passed dean review: {syllabus.course.code}"
            message = (
                "Dean review is complete. Final UMU review is required.\n"
                f"Course: {syllabus.course.display_title}"
            )

        elif new_status == Syllabus.Status.APPROVED:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Syllabus approved: {syllabus.course.code}"
                message = f"Your syllabus for {syllabus.course.code} has been officially approved."

        elif new_status == Syllabus.Status.CORRECTION:
            if syllabus.creator.email:
                recipients = [syllabus.creator.email]
                subject = f"Syllabus requires correction: {syllabus.course.code}"
                message = (
                    "Your syllabus was returned for correction.\n\n"
                    f"Comment:\n{comment}"
                )

        if recipients:
            _safe_send_mail(subject, message, recipients)

    except Exception as exc:
        logger.error("Notification block error: %s", exc)


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    """
    Main status transition function.
    1. Validates permissions.
    2. Updates status.
    3. Writes status/audit logs.
    4. Sends notifications.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    new_status = Syllabus.normalize_status(str(new_status))
    comment = (comment or "").strip()

    if new_status not in _ALLOWED_STATUSES:
        raise ValueError("Unsupported status transition target.")

    # Normalize legacy status values that may still exist in DB.
    if syllabus.status != old_status:
        syllabus.status = old_status

    is_admin = bool(
        user.is_superuser
        or user.is_staff
        or getattr(user, "role", "") == "admin"
        or getattr(user, "is_admin_like", False)
    )
    user_role = getattr(user, "role", "")
    is_dean = is_admin or user_role == "dean"
    is_umu = is_admin or user_role == "umu"
    is_creator = user == syllabus.creator

    if new_status == old_status:
        return syllabus

    if new_status == Syllabus.Status.REVIEW_DEAN:
        if not (is_creator or is_admin):
            raise PermissionDenied("Only the author can submit a syllabus for dean review.")

        allowed_prev = [
            Syllabus.Status.DRAFT,
            Syllabus.Status.CORRECTION,
            Syllabus.Status.AI_CHECK,
            Syllabus.Status.REVIEW_DEAN,
        ]
        if old_status not in allowed_prev and not is_admin:
            raise PermissionDenied("Invalid status for submission to dean.")

    elif new_status == Syllabus.Status.REVIEW_UMU:
        if not is_dean:
            raise PermissionDenied("Only dean can forward a syllabus to UMU.")
        if is_creator and not is_admin:
            raise PermissionDenied("Author cannot approve their own syllabus at dean stage.")
        if old_status != Syllabus.Status.REVIEW_DEAN and not is_admin:
            raise PermissionDenied("Syllabus must be in dean review status first.")

    elif new_status == Syllabus.Status.APPROVED:
        if not is_umu:
            raise PermissionDenied("Only UMU can finalize syllabus approval.")
        if is_creator and not is_admin:
            raise PermissionDenied("Author cannot finalize approval for their own syllabus.")
        if old_status != Syllabus.Status.REVIEW_UMU and not is_admin:
            raise PermissionDenied("Syllabus must be in UMU review status first.")

    elif new_status == Syllabus.Status.CORRECTION:
        if not (is_dean or is_umu):
            raise PermissionDenied("Only dean or UMU can return syllabus for correction.")
        if old_status not in _REVIEW_STATUSES and not is_admin:
            raise PermissionDenied("Syllabus must be in dean or UMU review status first.")
        if not comment:
            raise ValueError("Comment is required when returning for correction.")

    elif new_status == Syllabus.Status.REJECTED:
        if not (is_dean or is_umu):
            raise PermissionDenied("Only dean or UMU can reject a syllabus.")
        if old_status not in _REVIEW_STATUSES and not is_admin:
            raise PermissionDenied("Syllabus must be in dean or UMU review status first.")
        if not comment:
            raise ValueError("Comment is required when rejecting a syllabus.")
    else:
        raise PermissionDenied("Manual transition to this status is not allowed.")

    with transaction.atomic():
        syllabus.status = new_status
        syllabus.save(update_fields=["status"])

        SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=user,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=user,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status},
            message=(
                f"Status changed: {_status_label(old_status)} -> {_status_label(new_status)}"
                if new_status != Syllabus.Status.CORRECTION
                else f"Returned for correction by {_reviewer_label(user)}"
            ),
        )

    _notify_on_status_change(syllabus, new_status, comment)

    return syllabus


def change_status_system(
    syllabus: Syllabus,
    new_status: str,
    comment: str = "",
    ai_feedback: str | None = None,
) -> Syllabus:
    """
    Internal status transition for background workers.
    Bypasses role checks but keeps status/audit logs and notifications consistent.
    """
    old_status = Syllabus.normalize_status(syllabus.status)
    new_status = Syllabus.normalize_status(str(new_status))
    comment = (comment or "").strip()

    if new_status not in _ALLOWED_STATUSES:
        raise ValueError("Unsupported status transition target.")

    if syllabus.status != old_status:
        syllabus.status = old_status

    update_fields: list[str] = []
    if ai_feedback is not None:
        syllabus.ai_feedback = ai_feedback
        update_fields.append("ai_feedback")

    if new_status == old_status:
        if update_fields:
            syllabus.save(update_fields=update_fields)
        return syllabus

    with transaction.atomic():
        syllabus.status = new_status
        update_fields = ["status", *update_fields]
        syllabus.save(update_fields=update_fields)

        SyllabusStatusLog.objects.create(
            syllabus=syllabus,
            from_status=old_status,
            to_status=new_status,
            changed_by=None,
            comment=comment,
        )

        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=None,
            action=SyllabusAuditLog.Action.STATUS_CHANGED,
            metadata={"from": old_status, "to": new_status, "source": "system"},
            message=(
                comment
                or f"System status changed: {_status_label(old_status)} -> {_status_label(new_status)}"
            ),
        )

    _notify_on_status_change(syllabus, new_status, comment)
    return syllabus
