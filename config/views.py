from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from catalog.models import Course
from core.forms import AnnouncementForm
from core.models import Announcement
from syllabi.models import Syllabus
from syllabi.permissions import shared_syllabi_queryset


def _can_manage_announcements(user) -> bool:
    return user.role in ["dean", "umu"]


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

    if role in ["dean", "admin"]:
        pending_dean = (
            Syllabus.objects.filter(status=Syllabus.Status.SUBMITTED_DEAN)
            .select_related("course", "creator")
            .order_by("-updated_at")[:10]
        )

    if role in ["umu", "admin"]:
        pending_umu = (
            Syllabus.objects.filter(status=Syllabus.Status.SUBMITTED_UMU)
            .select_related("course", "creator")
            .order_by("-updated_at")[:10]
        )

    if role in ["teacher", "program_leader"]:
        my_reviews = (
            Syllabus.objects.filter(
                creator=request.user,
                status__in=[
                    Syllabus.Status.SUBMITTED_DEAN,
                    Syllabus.Status.APPROVED_DEAN,
                    Syllabus.Status.SUBMITTED_UMU,
                    Syllabus.Status.APPROVED_UMU,
                    Syllabus.Status.REJECTED,
                ],
            )
            .select_related("course")
            .order_by("-updated_at")[:10]
        )

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
