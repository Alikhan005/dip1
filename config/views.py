from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db.models import Prefetch
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
