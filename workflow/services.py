from django.core.exceptions import PermissionDenied
from syllabi.models import Syllabus
from syllabi.services import validate_syllabus_structure
from .models import SyllabusStatusLog


def change_status(user, syllabus: Syllabus, new_status: str, comment: str = ""):
    old_status = syllabus.status
    comment = (comment or "").strip()
    is_dean = user.role == "dean"
    is_umu = user.role == "umu"
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

    return syllabus
