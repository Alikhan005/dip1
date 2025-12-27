from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from catalog.models import Course
from syllabi.models import Syllabus
from syllabi.permissions import shared_syllabi_queryset


@login_required
def dashboard(request):
    role = request.user.role
    my_courses_count = Course.objects.filter(owner=request.user).count()
    shared_courses_count = Course.objects.filter(is_shared=True).count()
    syllabi_count = Syllabus.objects.filter(creator=request.user).count()
    shared_syllabi_count = shared_syllabi_queryset(request.user).count()

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
                    Syllabus.Status.REJECTED,
                ],
            )
            .select_related("course")
            .order_by("-updated_at")[:10]
        )

    return render(
        request,
        "dashboard.html",
        {
            "role": role,
            "my_courses_count": my_courses_count,
            "shared_courses_count": shared_courses_count,
            "syllabi_count": syllabi_count,
            "shared_syllabi_count": shared_syllabi_count,
            "pending_dean": pending_dean,
            "pending_umu": pending_umu,
            "my_reviews": my_reviews,
        },
    )
