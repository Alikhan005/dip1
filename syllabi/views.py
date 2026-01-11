from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from catalog.services import ensure_default_courses
from .forms import SyllabusForm, SyllabusDetailsForm
from .models import Syllabus, SyllabusTopic, SyllabusRevision
from .permissions import can_view_syllabus, shared_syllabi_queryset
from .services import generate_syllabus_pdf
from workflow.services import change_status


def _can_view_syllabus(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


def _split_lines(value: str) -> list[str]:
    if not value:
        return []
    lines = []
    for raw in value.splitlines():
        cleaned = raw.strip().lstrip("-•").strip()
        if cleaned:
            lines.append(cleaned)
    return lines


def _build_literature_lists(topics):
    main_items = []
    additional_items = []
    seen = set()
    for st in topics:
        for lit in st.topic.literature.all():
            key = (lit.title, lit.author, lit.year, lit.lit_type)
            if key in seen:
                continue
            seen.add(key)
            entry = lit.title
            if lit.author:
                entry = f"{entry} - {lit.author}"
            if lit.year:
                entry = f"{entry} ({lit.year})"
            if lit.lit_type == lit.LitType.MAIN:
                main_items.append(entry)
            else:
                additional_items.append(entry)
    return main_items, additional_items


@login_required
def syllabi_list(request):
    if request.user.role in ["dean", "umu"]:
        syllabi = Syllabus.objects.select_related("course", "creator")
    else:
        syllabi = Syllabus.objects.filter(creator=request.user).select_related("course", "creator")
    return render(request, "syllabi/syllabi_list.html", {"syllabi": syllabi})


@login_required
@role_required("teacher")
def shared_syllabi_list(request):
    syllabi = shared_syllabi_queryset(request.user).order_by("-updated_at")
    return render(request, "syllabi/shared_syllabi_list.html", {"syllabi": syllabi})


@login_required
@role_required("teacher")
def syllabus_create(request):
    ensure_default_courses(request.user)
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
                            week_label=st.week_label,
                            tasks=st.tasks,
                            learning_outcomes=st.learning_outcomes,
                            literature_notes=st.literature_notes,
                            assessment=st.assessment,
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
    has_copy_from = form.fields["copy_from"].queryset.exists()
    if not has_copy_from:
        form.fields["copy_from"].disabled = True
    return render(
        request,
        "syllabi/syllabus_form.html",
        {"form": form, "has_copy_from": has_copy_from},
    )


@login_required
def syllabus_detail(request, pk):
    syllabus = get_object_or_404(Syllabus.objects.select_related("course", "creator"), pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    is_frozen = syllabus.status == Syllabus.Status.APPROVED_UMU
    is_creator = request.user == syllabus.creator
    role = request.user.role
    is_dean = role == "dean"
    is_umu = role == "umu"
    is_teacher_like = request.user.is_teacher_like

    can_edit_topics = not is_frozen and is_creator
    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )
    derived_main_literature, derived_additional_literature = _build_literature_lists(topics)
    can_submit_dean = (
        is_creator
        and syllabus.status in ["draft", "rejected"]
        and is_teacher_like
    )
    can_approve_dean = (
        syllabus.status == "submitted_dean"
        and is_dean
        and not is_creator
    )
    can_submit_umu = (
        syllabus.status == "approved_dean"
        and is_creator
        and is_teacher_like
    )
    can_approve_umu = (
        syllabus.status == "submitted_umu"
        and is_umu
        and not is_creator
    )
    can_reject_umu = can_approve_umu
    can_upload = (is_creator and not is_frozen) or (is_umu and is_frozen)
    can_share = is_creator

    return render(
        request,
        "syllabi/syllabus_detail.html",
        {
            "syllabus": syllabus,
            "topics": topics,
            "is_frozen": is_frozen,
            "can_edit_topics": can_edit_topics,
            "can_submit_dean": can_submit_dean,
            "can_approve_dean": can_approve_dean,
            "can_submit_umu": can_submit_umu,
            "can_approve_umu": can_approve_umu,
            "can_reject_umu": can_reject_umu,
            "can_upload": can_upload,
            "can_share": can_share,
            "is_creator": is_creator,
            "learning_outcomes_list": _split_lines(syllabus.learning_outcomes),
            "teaching_methods_list": _split_lines(syllabus.teaching_methods),
            "main_literature_list": _split_lines(syllabus.main_literature)
            or derived_main_literature,
            "additional_literature_list": _split_lines(syllabus.additional_literature)
            or derived_additional_literature,
        },
    )


@login_required
@role_required("teacher")
def syllabus_edit_topics(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk, creator=request.user)
    if syllabus.status == Syllabus.Status.APPROVED_UMU:
        messages.error(request, "Силлабус утвержден УМУ и заморожен.")
        return redirect("syllabus_detail", pk=syllabus.pk)

    course_topics = syllabus.course.topics.filter(is_active=True).order_by("order_index")

    if request.method == "POST":
        entries = []

        for topic in course_topics:
            included = request.POST.get(f"include_{topic.id}") == "on"
            if not included:
                continue

            custom_title = request.POST.get(f"title_{topic.id}", "").strip()
            hours_raw = request.POST.get(f"hours_{topic.id}", "").strip()
            week_raw = request.POST.get(f"week_{topic.id}", "").strip()
            week_label = request.POST.get(f"week_label_{topic.id}", "").strip()
            tasks = request.POST.get(f"tasks_{topic.id}", "").strip()
            outcomes = request.POST.get(f"outcomes_{topic.id}", "").strip()
            literature_notes = request.POST.get(f"literature_{topic.id}", "").strip()
            assessment = request.POST.get(f"assessment_{topic.id}", "").strip()

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
                    "week_label": week_label,
                    "tasks": tasks,
                    "learning_outcomes": outcomes,
                    "literature_notes": literature_notes,
                    "assessment": assessment,
                }
            )

        if not entries:
            messages.error(request, "Выберите хотя бы одну тему для силлабуса.")
            return redirect("syllabus_edit_topics", pk=syllabus.pk)

        used_weeks = {entry["week_number"] for entry in entries if entry["week_number"]}
        next_week = 1
        for entry in entries:
            if entry["week_number"] is None:
                while next_week in used_weeks:
                    next_week += 1
                entry["week_number"] = next_week
                used_weeks.add(next_week)

        with transaction.atomic():
            SyllabusTopic.objects.filter(syllabus=syllabus).delete()
            for entry in entries:
                if not entry["week_label"] and entry["week_number"]:
                    entry["week_label"] = str(entry["week_number"])
                SyllabusTopic.objects.create(
                    syllabus=syllabus,
                    topic=entry["topic"],
                    week_number=entry["week_number"],
                    custom_title=entry["custom_title"],
                    custom_hours=entry["custom_hours"],
                    week_label=entry["week_label"],
                    tasks=entry["tasks"],
                    learning_outcomes=entry["learning_outcomes"],
                    literature_notes=entry["literature_notes"],
                    assessment=entry["assessment"],
                    is_included=True,
                )

            syllabus.version_number += 1
            syllabus.save()
            SyllabusRevision.objects.create(
                syllabus=syllabus,
                changed_by=request.user,
                version_number=syllabus.version_number,
                note="Обновлены темы и недели",
            )

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
                "week_label": st.week_label if st else "",
                "tasks": st.tasks if st else "",
                "learning_outcomes": st.learning_outcomes if st else "",
                "literature_notes": st.literature_notes if st else "",
                "assessment": st.assessment if st else "",
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
@role_required("teacher")
def syllabus_edit_details(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk, creator=request.user)

    if syllabus.status == Syllabus.Status.APPROVED_UMU:
        messages.error(request, "Силлабус утвержден и недоступен для редактирования.")
        return redirect("syllabus_detail", pk=syllabus.pk)

    if request.method == "POST":
        form = SyllabusDetailsForm(request.POST, instance=syllabus)
        if form.is_valid():
            syllabus = form.save(commit=False)
            syllabus.version_number += 1
            syllabus.save()
            SyllabusRevision.objects.create(
                syllabus=syllabus,
                changed_by=request.user,
                version_number=syllabus.version_number,
                note="Обновлены основные данные",
            )
            messages.success(request, "Данные силлабуса обновлены.")
            return redirect("syllabus_detail", pk=syllabus.pk)
    else:
        initial = {}
        if not syllabus.instructor_name:
            initial["instructor_name"] = request.user.get_full_name() or request.user.username
        if not syllabus.instructor_contacts and request.user.email:
            initial["instructor_contacts"] = request.user.email
        form = SyllabusDetailsForm(instance=syllabus, initial=initial)

    return render(
        request,
        "syllabi/syllabus_edit_details.html",
        {
            "syllabus": syllabus,
            "form": form,
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
        comment = request.POST.get("comment", "").strip()
        try:
            change_status(request.user, syllabus, new_status, comment)
            messages.success(request, "Статус силлабуса обновлен.")
        except (PermissionDenied, ValueError) as exc:
            messages.error(request, str(exc) or "Недостаточно прав.")
    return redirect("syllabus_detail", pk=syllabus.pk)


@login_required
def syllabus_upload_file(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.method != "POST":
        return redirect("syllabus_detail", pk=pk)

    can_upload = (
        request.user == syllabus.creator and syllabus.status != Syllabus.Status.APPROVED_UMU
    ) or (
        request.user.role == "umu" and syllabus.status == Syllabus.Status.APPROVED_UMU
    )
    if not can_upload:
        raise PermissionDenied("У вас нет прав на загрузку файла для этого силлабуса.")

    uploaded = request.FILES.get("attachment")
    if uploaded:
        syllabus.pdf_file.save(uploaded.name, uploaded, save=False)
        syllabus.version_number += 1
        syllabus.save()
        SyllabusRevision.objects.create(
            syllabus=syllabus,
            changed_by=request.user,
            version_number=syllabus.version_number,
            note="Загружен PDF",
        )

    return redirect("syllabus_detail", pk=pk)


@login_required
@role_required("teacher")
def syllabus_toggle_share(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.user != syllabus.creator:
        raise PermissionDenied("Недостаточно прав, чтобы менять доступ к силлабусу.")

    if request.method == "POST":
        syllabus.is_shared = not syllabus.is_shared
        syllabus.save(update_fields=["is_shared"])

    return redirect("syllabus_detail", pk=pk)
