from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from .forms import SyllabusForm
from .models import Syllabus, SyllabusTopic
from .permissions import can_view_syllabus, shared_syllabi_queryset
from .services import generate_syllabus_pdf
from workflow.services import change_status


def _can_view_syllabus(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


@login_required
def syllabi_list(request):
    if request.user.role in ["admin", "dean", "umu"]:
        syllabi = Syllabus.objects.select_related("course", "creator")
    else:
        syllabi = Syllabus.objects.filter(creator=request.user).select_related("course", "creator")
    return render(request, "syllabi/syllabi_list.html", {"syllabi": syllabi})


@login_required
@role_required("teacher", "program_leader", "admin", "dean", "umu")
def shared_syllabi_list(request):
    syllabi = shared_syllabi_queryset(request.user).order_by("-updated_at")
    return render(request, "syllabi/shared_syllabi_list.html", {"syllabi": syllabi})


@login_required
@role_required("teacher", "admin")
def syllabus_create(request):
    if request.method == "POST":
        form = SyllabusForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            syllabus = form.save(commit=False)
            syllabus.creator = request.user
            syllabus.save()
            copy_from = form.cleaned_data.get("copy_from")
            prefill_topics = form.cleaned_data.get("prefill_topics")
            if copy_from:
                source_topics = (
                    copy_from.syllabus_topics.select_related("topic").order_by("week_number")
                )
                SyllabusTopic.objects.bulk_create(
                    [
                        SyllabusTopic(
                            syllabus=syllabus,
                            topic=st.topic,
                            week_number=st.week_number,
                            is_included=st.is_included,
                            custom_title=st.custom_title,
                            custom_hours=st.custom_hours,
                        )
                        for st in source_topics
                    ]
                )
            elif prefill_topics:
                course_topics = (
                    syllabus.course.topics.filter(is_active=True)
                    .order_by("order_index", "id")
                )
                SyllabusTopic.objects.bulk_create(
                    [
                        SyllabusTopic(
                            syllabus=syllabus,
                            topic=topic,
                            week_number=index,
                            is_included=True,
                        )
                        for index, topic in enumerate(course_topics, start=1)
                    ]
                )
            return redirect("syllabus_edit_topics", pk=syllabus.pk)
    else:
        form = SyllabusForm(user=request.user)
    return render(request, "syllabi/syllabus_form.html", {"form": form})


@login_required
def syllabus_detail(request, pk):
    syllabus = get_object_or_404(Syllabus.objects.select_related("course", "creator"), pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )
    is_creator = request.user == syllabus.creator
    role = request.user.role
    can_submit_dean = is_creator and syllabus.status in ["draft", "rejected"]
    can_approve_dean = role == "dean" and syllabus.status == "submitted_dean"
    can_submit_umu = syllabus.status == "approved_dean" and role in ["teacher", "dean", "admin"]
    can_approve_umu = role == "umu" and syllabus.status == "submitted_umu"
    can_reject_umu = role == "umu" and syllabus.status == "submitted_umu"
    can_upload = is_creator or role in ["admin", "dean", "umu"]
    can_share = is_creator or role == "admin"

    return render(
        request,
        "syllabi/syllabus_detail.html",
        {
            "syllabus": syllabus,
            "topics": topics,
            "can_submit_dean": can_submit_dean,
            "can_approve_dean": can_approve_dean,
            "can_submit_umu": can_submit_umu,
            "can_approve_umu": can_approve_umu,
            "can_reject_umu": can_reject_umu,
            "can_upload": can_upload,
            "can_share": can_share,
            "is_creator": is_creator,
        },
    )


@login_required
@role_required("teacher", "admin")
def syllabus_edit_topics(request, pk):
    if request.user.role == "admin":
        syllabus = get_object_or_404(Syllabus, pk=pk)
    else:
        syllabus = get_object_or_404(Syllabus, pk=pk, creator=request.user)

    course_topics = syllabus.course.topics.filter(is_active=True).order_by("order_index")

    if request.method == "POST":
        SyllabusTopic.objects.filter(syllabus=syllabus).delete()
        entries = []

        for topic in course_topics:
            included = request.POST.get(f"include_{topic.id}") == "on"
            if not included:
                continue

            custom_title = request.POST.get(f"title_{topic.id}", "").strip()
            hours_raw = request.POST.get(f"hours_{topic.id}", "").strip()
            week_raw = request.POST.get(f"week_{topic.id}", "").strip()

            try:
                custom_hours = int(hours_raw) if hours_raw else None
            except ValueError:
                custom_hours = None
            if custom_hours is not None and custom_hours <= 0:
                custom_hours = None

            try:
                week_number = int(week_raw) if week_raw else None
            except ValueError:
                week_number = None
            if week_number is not None and week_number <= 0:
                week_number = None

            entries.append(
                {
                    "topic": topic,
                    "custom_title": custom_title,
                    "custom_hours": custom_hours,
                    "week_number": week_number,
                }
            )

        used_weeks = {entry["week_number"] for entry in entries if entry["week_number"]}
        next_week = 1
        for entry in entries:
            if entry["week_number"] is None:
                while next_week in used_weeks:
                    next_week += 1
                entry["week_number"] = next_week
                used_weeks.add(next_week)

        for entry in entries:
            SyllabusTopic.objects.create(
                syllabus=syllabus,
                topic=entry["topic"],
                week_number=entry["week_number"],
                custom_title=entry["custom_title"],
                custom_hours=entry["custom_hours"],
                is_included=True,
            )

        syllabus.version_number += 1
        syllabus.save()

        return redirect("syllabus_detail", pk=syllabus.pk)

    topics_with_state = []
    existing = {st.topic_id: st for st in syllabus.syllabus_topics.all()}
    for topic in course_topics:
        st = existing.get(topic.id)
        topics_with_state.append(
            {
                "topic": topic,
                "included": bool(st),
                "custom_title": st.custom_title if st else "",
                "custom_hours": st.custom_hours if st else "",
                "week_number": st.week_number if st else "",
                "display_title": topic.get_title(syllabus.main_language),
            }
        )

    return render(
        request,
        "syllabi/syllabus_edit_topics.html",
        {
            "syllabus": syllabus,
            "topics": topics_with_state,
        },
    )


@login_required
def syllabus_pdf(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    return generate_syllabus_pdf(syllabus)


@login_required
def syllabus_change_status(request, pk, new_status):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.method == "POST":
        comment = request.POST.get("comment", "")
        change_status(request.user, syllabus, new_status, comment)
    return redirect("syllabus_detail", pk=syllabus.pk)


@login_required
def syllabus_upload_file(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.method != "POST":
        return redirect("syllabus_detail", pk=pk)

    if request.user != syllabus.creator and request.user.role not in ["admin", "dean", "umu"]:
        raise PermissionDenied("У вас нет прав на загрузку файла для этого силлабуса.")

    uploaded = request.FILES.get("attachment")
    if uploaded:
        syllabus.pdf_file.save(uploaded.name, uploaded, save=False)
        syllabus.version_number += 1
        syllabus.save()

    return redirect("syllabus_detail", pk=pk)


@login_required
@role_required("teacher", "program_leader", "admin")
def syllabus_toggle_share(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.user != syllabus.creator and request.user.role != "admin":
        raise PermissionDenied("Недостаточно прав, чтобы менять доступ к силлабусу.")

    if request.method == "POST":
        syllabus.is_shared = not syllabus.is_shared
        syllabus.save(update_fields=["is_shared"])

    return redirect("syllabus_detail", pk=pk)
