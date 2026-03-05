from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Course
from core.forms import AnnouncementForm
from core.models import Announcement
from syllabi.models import Syllabus
from syllabi.permissions import shared_syllabi_queryset
from workflow.models import SyllabusStatusLog


def _can_manage_announcements(user) -> bool:
    return user.role in ["dean", "umu"]


def _reviewer_label_from_status_log(status_log: SyllabusStatusLog | None) -> str:
    if not status_log:
        return ""

    if status_log.from_status == Syllabus.Status.AI_CHECK and not status_log.changed_by:
        return "ИИ"
    if status_log.from_status == Syllabus.Status.REVIEW_UMU:
        return "УМУ"
    if status_log.from_status == Syllabus.Status.REVIEW_DEAN:
        return "деканата"

    actor_role = getattr(status_log.changed_by, "role", "")
    if actor_role == "umu":
        return "УМУ"
    if actor_role == "dean":
        return "деканата"
    if actor_role == "admin":
        return "администратора"
    return "проверяющего"


def _notification_actor_label(status_log: SyllabusStatusLog) -> str:
    if status_log.changed_by is None:
        if status_log.from_status == Syllabus.Status.AI_CHECK:
            return "ИИ"
        return "Система"

    actor_role = getattr(status_log.changed_by, "role", "")
    if actor_role == "umu":
        return "УМУ"
    if actor_role == "dean":
        return "Деканат"
    if actor_role == "admin":
        return "Администратор"
    return status_log.changed_by.get_full_name() or status_log.changed_by.username


def _notification_title(status_log: SyllabusStatusLog) -> str:
    course_code = getattr(status_log.syllabus.course, "code", f"ID {status_log.syllabus_id}")
    status_to = status_log.to_status

    if status_to == Syllabus.Status.REVIEW_DEAN:
        return f"{course_code}: отправлен на согласование декану"
    if status_to == Syllabus.Status.REVIEW_UMU:
        return f"{course_code}: отправлен на согласование в УМУ"
    if status_to == Syllabus.Status.CORRECTION:
        return f"{course_code}: возвращён на доработку"
    if status_to == Syllabus.Status.APPROVED:
        return f"{course_code}: силлабус утверждён"
    if status_to == Syllabus.Status.REJECTED:
        return f"{course_code}: силлабус отклонён"
    if status_to == Syllabus.Status.AI_CHECK:
        return f"{course_code}: отправлен на проверку ИИ"
    return f"{course_code}: статус обновлён"


def _notification_body(status_log: SyllabusStatusLog) -> str:
    comment = (status_log.comment or "").strip()
    if comment:
        return comment

    from_label = status_log.from_status_label
    to_label = status_log.to_status_label
    return f"Статус изменён: {from_label} -> {to_label}"


def _notification_logs_queryset(user):
    base_qs = (
        SyllabusStatusLog.objects.select_related("syllabus__course", "syllabus__creator", "changed_by")
        .exclude(to_status=Syllabus.Status.DRAFT)
    )

    is_admin = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_staff", False)
        or getattr(user, "role", "") == "admin"
    )
    if not is_admin:
        visibility_filter = Q(syllabus__creator=user) | Q(changed_by=user)
        role = getattr(user, "role", "")
        if role == "dean":
            visibility_filter |= Q(to_status=Syllabus.Status.REVIEW_DEAN)
        elif role == "umu":
            visibility_filter |= Q(to_status=Syllabus.Status.REVIEW_UMU)
        base_qs = base_qs.filter(visibility_filter)

    return base_qs.order_by("-changed_at").distinct()


def _count_unread_notifications(user, last_seen_at) -> int:
    logs_qs = _notification_logs_queryset(user)
    if last_seen_at is None:
        return logs_qs.count()
    return logs_qs.filter(changed_at__gt=last_seen_at).count()


def _latest_notification_changed_at(user):
    return _notification_logs_queryset(user).values_list("changed_at", flat=True).first()


def _build_dashboard_notifications(user, limit: int | None = 6) -> list[dict]:
    logs_qs = _notification_logs_queryset(user)
    logs = logs_qs[:limit] if limit is not None else logs_qs
    notifications = []
    for log in logs:
        creator = log.syllabus.creator
        creator_name = creator.get_full_name() or creator.username
        notifications.append(
            {
                "syllabus_id": log.syllabus_id,
                "title": _notification_title(log),
                "body": _notification_body(log),
                "actor_label": _notification_actor_label(log),
                "creator_name": creator_name,
                "changed_at": log.changed_at,
            }
        )
    return notifications


def _build_dashboard_context(request, announcement_form=None):
    role = request.user.role
    my_courses_count = Course.objects.filter(owner=request.user).count()
    shared_courses_count = Course.objects.filter(is_shared=True).count()
    syllabi_count = Syllabus.objects.filter(creator=request.user).count()
    shared_syllabi_count = shared_syllabi_queryset(request.user).count()
    announcements = Announcement.objects.select_related("created_by").all()[:6]
    can_manage_announcements = _can_manage_announcements(request.user)

    pending_dean = Syllabus.objects.none()
    pending_umu = Syllabus.objects.none()
    my_reviews = Syllabus.objects.none()

    # ДЕКАН: Видит силлабусы в статусе "Согласование: Декан"
    if role in ["dean", "admin"]:
        pending_dean = (
            Syllabus.objects.filter(status=Syllabus.Status.REVIEW_DEAN)
            .select_related("course", "creator")
            .order_by("-updated_at")[:10]
        )

    # УМУ: Видит силлабусы в статусе "Согласование: УМУ"
    if role in ["umu", "admin"]:
        pending_umu = (
            Syllabus.objects.filter(status=Syllabus.Status.REVIEW_UMU)
            .select_related("course", "creator")
            .order_by("-updated_at")[:10]
        )

    # ПРЕПОДАВАТЕЛЬ: Видит свои силлабусы во всех активных статусах
    if role in ["teacher", "program_leader"]:
        correction_logs_qs = (
            SyllabusStatusLog.objects.filter(to_status=Syllabus.Status.CORRECTION)
            .select_related("changed_by")
            .order_by("-changed_at")
        )
        my_reviews = list(
            Syllabus.objects.filter(
                creator=request.user,
                status__in=[
                    Syllabus.Status.AI_CHECK,
                    Syllabus.Status.CORRECTION,
                    Syllabus.Status.REVIEW_DEAN,
                    Syllabus.Status.REVIEW_UMU,
                    Syllabus.Status.APPROVED,
                    Syllabus.Status.REJECTED,
                ],
            )
            .select_related("course")
            .prefetch_related(
                Prefetch("status_logs", queryset=correction_logs_qs, to_attr="correction_logs_prefetched")
            )
            .order_by("-updated_at")[:10]
        )
        for syllabus in my_reviews:
            syllabus.correction_source_label = ""
            syllabus.correction_comment_preview = ""
            if syllabus.status != Syllabus.Status.CORRECTION:
                continue

            correction_logs = getattr(syllabus, "correction_logs_prefetched", [])
            latest_log = correction_logs[0] if correction_logs else None
            if not latest_log:
                continue

            syllabus.correction_source_label = _reviewer_label_from_status_log(latest_log)
            syllabus.correction_comment_preview = (latest_log.comment or "").strip()

    if announcement_form is None and can_manage_announcements:
        announcement_form = AnnouncementForm()

    return {
        "role": role,
        "my_courses_count": my_courses_count,
        "shared_courses_count": shared_courses_count,
        "syllabi_count": syllabi_count,
        "shared_syllabi_count": shared_syllabi_count,
        "pending_dean": pending_dean,
        "pending_umu": pending_umu,
        "my_reviews": my_reviews,
        "announcements": announcements,
        "announcement_form": announcement_form,
        "can_manage_announcements": can_manage_announcements,
    }


@login_required
def dashboard(request):
    context = _build_dashboard_context(request)
    return render(request, "dashboard.html", context)


@login_required
@require_POST
def create_announcement(request):
    if not _can_manage_announcements(request.user):
        raise PermissionDenied("Нет доступа.")

    form = AnnouncementForm(request.POST)
    if form.is_valid():
        announcement = form.save(commit=False)
        announcement.created_by = request.user
        announcement.save()
        messages.success(request, "Объявление опубликовано.")
        return redirect("dashboard")

    messages.error(request, "Заполните заголовок и текст.")
    context = _build_dashboard_context(request, announcement_form=form)
    return render(request, "dashboard.html", context)
