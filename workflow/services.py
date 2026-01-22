import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail

from syllabi.models import Syllabus
from syllabi.services import validate_syllabus_structure
from .models import SyllabusAuditLog, SyllabusStatusLog

logger = logging.getLogger(__name__)


def _status_label(status: str) -> str:
    try:
        return Syllabus.Status(status).label
    except Exception:
        return status


def _collect_role_emails(role: str) -> list[str]:
    User = get_user_model()
    qs = User.objects.filter(role=role, is_active=True).exclude(email="")
    if hasattr(User, "email_verified"):
        qs = qs.filter(email_verified=True)
    return list(qs.values_list("email", flat=True))


def _safe_send_mail(subject: str, message: str, recipients: list[str]) -> None:
    if not recipients:
        return
    from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "") or None
    try:
        send_mail(subject, message, from_email, recipients, fail_silently=False)
    except Exception:
        logger.exception("Failed to send workflow notification email.")


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    old_status = syllabus.status
    comment = (comment or "").strip()
    is_admin_like = getattr(user, "is_admin_like", False) or user.role == "admin" or user.is_superuser
    is_dean = user.role == "dean" or is_admin_like
    is_umu = user.role == "umu" or is_admin_like
    is_teacher_like = user.is_teacher_like
    is_creator = user == syllabus.creator

    if new_status == old_status:
        return syllabus

    if new_status == Syllabus.Status.SUBMITTED_DEAN:
        if user != syllabus.creator:
            raise PermissionDenied("Только автор силлабуса может отправить его декану.")
        if not is_teacher_like:
            raise PermissionDenied("Отправлять декану может только преподаватель.")
        if old_status not in [Syllabus.Status.DRAFT, Syllabus.Status.REJECTED]:
            raise PermissionDenied("Этот силлабус уже отправлен на согласование.")
        errors = validate_syllabus_structure(syllabus)
        if errors:
            raise ValueError("Нельзя отправить на согласование: " + "; ".join(errors))

    if new_status == Syllabus.Status.APPROVED_DEAN:
        if not is_dean:
            raise PermissionDenied("Только декан может утверждать.")
        if is_creator:
            raise PermissionDenied("Нельзя утверждать собственный силлабус.")
        if old_status != Syllabus.Status.SUBMITTED_DEAN:
            raise PermissionDenied("Силлабус должен быть отправлен декану.")

    if new_status == Syllabus.Status.REJECTED:
        if not comment:
            raise ValueError("Комментарий обязателен при отклонении.")
        if is_dean:
            if old_status != Syllabus.Status.SUBMITTED_DEAN:
                raise PermissionDenied("Силлабус должен быть отправлен декану.")
            if is_creator:
                raise PermissionDenied("Нельзя отклонять собственный силлабус.")
        elif is_umu:
            if old_status != Syllabus.Status.SUBMITTED_UMU:
                raise PermissionDenied("Силлабус должен быть отправлен в УМУ.")
            if is_creator:
                raise PermissionDenied("Нельзя отклонять собственный силлабус.")
        else:
            raise PermissionDenied("Отклонять могут только декан или УМУ.")

    if new_status == Syllabus.Status.SUBMITTED_UMU:
        if user != syllabus.creator:
            raise PermissionDenied("Отправить в УМУ может только автор силлабуса.")
        if not is_teacher_like:
            raise PermissionDenied("Отправлять в УМУ может только преподаватель.")
        if old_status != Syllabus.Status.APPROVED_DEAN:
            raise PermissionDenied("Сначала силлабус должен быть утвержден деканом.")
        errors = validate_syllabus_structure(syllabus)
        if errors:
            raise ValueError("Нельзя отправить в УМУ: " + "; ".join(errors))

    if new_status == Syllabus.Status.APPROVED_UMU:
        if not is_umu:
            raise PermissionDenied("Только УМУ может финально утверждать силлабус.")
        if is_creator:
            raise PermissionDenied("Нельзя утверждать собственный силлабус.")
        if old_status != Syllabus.Status.SUBMITTED_UMU:
            raise PermissionDenied("Силлабус должен быть отправлен в УМУ.")

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
        metadata={"from_status": old_status, "to_status": new_status, "comment": comment},
        message=f"Статус изменен: {_status_label(old_status)} -> {_status_label(new_status)}",
    )

    subject = None
    message = None
    recipients: list[str] = []
    if new_status == Syllabus.Status.SUBMITTED_DEAN:
        recipients = _collect_role_emails("dean")
        subject = f"Силлабус отправлен декану: {syllabus.course.code} {syllabus.semester}"
        message = (
            f"Силлабус {syllabus.course.code} {syllabus.semester} отправлен на согласование.\n"
            f"Автор: {syllabus.creator.get_full_name() or syllabus.creator.username}\n"
            f"Статус: {_status_label(new_status)}"
        )
    elif new_status == Syllabus.Status.SUBMITTED_UMU:
        recipients = _collect_role_emails("umu")
        subject = f"Силлабус отправлен в УМУ: {syllabus.course.code} {syllabus.semester}"
        message = (
            f"Силлабус {syllabus.course.code} {syllabus.semester} отправлен в УМУ.\n"
            f"Автор: {syllabus.creator.get_full_name() or syllabus.creator.username}\n"
            f"Статус: {_status_label(new_status)}"
        )
    elif new_status in {Syllabus.Status.APPROVED_DEAN, Syllabus.Status.APPROVED_UMU, Syllabus.Status.REJECTED}:
        if syllabus.creator.email:
            recipients = [syllabus.creator.email]
            subject = f"Статус силлабуса изменен: {_status_label(new_status)}"
            message = (
                f"Силлабус {syllabus.course.code} {syllabus.semester}.\n"
                f"Новый статус: {_status_label(new_status)}.\n"
            )
            if comment:
                message += f"Комментарий: {comment}\n"

    if subject and message and recipients:
        _safe_send_mail(subject, message, recipients)

    return syllabus
