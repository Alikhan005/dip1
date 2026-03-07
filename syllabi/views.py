import re

from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from accounts.decorators import role_required
from catalog.models import Topic
from catalog.services import ensure_default_courses
from workflow.models import SyllabusAuditLog, SyllabusStatusLog
from workflow.services import change_status
from .forms import SyllabusDetailsForm, SyllabusForm, is_allowed_syllabus_file_name
from .models import Syllabus, SyllabusRevision, SyllabusTopic
from .permissions import can_view_syllabus, shared_syllabi_queryset
from .services import generate_syllabus_pdf, validate_syllabus_structure


def _can_view_syllabus(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


AI_CHECK_START_STATUSES = [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION, Syllabus.Status.AI_CHECK]


def _can_request_ai_check(user, syllabus: Syllabus) -> bool:
    is_admin_like = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_admin_like", False)
        or getattr(user, "role", "") == "admin"
    )
    return user == syllabus.creator or is_admin_like


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


def _parse_positive_int(value):
    raw = (value or "").strip()
    if not raw:
        return None
    try:
        parsed = int(raw)
    except (TypeError, ValueError):
        return None
    if parsed <= 0:
        return None
    return parsed


def _parse_legacy_reviewer_feedback(feedback: str) -> tuple[str, str]:
    """Parse old feedback format like [UMU returned for correction] <comment>."""
    raw = (feedback or "").strip()
    if not raw:
        return "", ""

    normalized = (
        raw.replace("<br />", "\n")
        .replace("<br/>", "\n")
        .replace("<br>", "\n")
    )
    plain = re.sub(r"<[^>]+>", "", normalized).strip()
    if not plain:
        return "", ""

    lower = plain.lower()
    if "[umu returned for correction]" in lower:
        comment = re.sub(r"\[[^\]]+\]", "", plain, count=1).strip(" :\n")
        return "УМУ", comment
    if "[dean returned for correction]" in lower:
        comment = re.sub(r"\[[^\]]+\]", "", plain, count=1).strip(" :\n")
        return "Деканат", comment

    return "", plain


def _resolve_correction_context(syllabus: Syllabus) -> dict:
    """
    Build user-facing correction context:
    - source label (ИИ / Деканат / УМУ)
    - plain comment for human reviewers
    - stage marker for progress visualization
    """
    context = {
        "source_label": "",
        "comment": "",
        "stage_key": "draft",
        "is_ai_feedback": False,
    }

    latest_correction = (
        SyllabusStatusLog.objects.filter(syllabus=syllabus, to_status=Syllabus.Status.CORRECTION)
        .select_related("changed_by")
        .order_by("-changed_at")
        .first()
    )

    if latest_correction:
        from_status = latest_correction.from_status
        if from_status == Syllabus.Status.REVIEW_UMU:
            context["source_label"] = "УМУ"
            context["stage_key"] = "umu"
        elif from_status == Syllabus.Status.REVIEW_DEAN:
            context["source_label"] = "Деканат"
            context["stage_key"] = "dean"
        elif from_status == Syllabus.Status.AI_CHECK:
            context["source_label"] = "ИИ"
            context["stage_key"] = "ai_check"
            context["is_ai_feedback"] = True

        actor_role = getattr(latest_correction.changed_by, "role", "")
        if not context["source_label"]:
            if actor_role == "umu":
                context["source_label"] = "УМУ"
                context["stage_key"] = "umu"
            elif actor_role == "dean":
                context["source_label"] = "Деканат"
                context["stage_key"] = "dean"
            elif latest_correction.changed_by:
                context["source_label"] = (
                    latest_correction.changed_by.get_full_name()
                    or latest_correction.changed_by.username
                )

        context["comment"] = (latest_correction.comment or "").strip()

    if not context["source_label"] and syllabus.ai_feedback:
        legacy_source, legacy_comment = _parse_legacy_reviewer_feedback(syllabus.ai_feedback)
        if legacy_source:
            context["source_label"] = legacy_source
            context["comment"] = context["comment"] or legacy_comment
            context["stage_key"] = "umu" if legacy_source == "УМУ" else "dean"
        else:
            context["source_label"] = "ИИ"
            context["stage_key"] = "ai_check"
            context["is_ai_feedback"] = True

    if not context["source_label"]:
        context["source_label"] = "Проверяющий"

    return context


def _build_progress_context(status: str, correction_stage_key: str = "draft") -> dict:
    if status == Syllabus.Status.DRAFT:
        return {"width": 10, "bar_class": "bg-slate-400", "active_step": "draft"}
    if status == Syllabus.Status.AI_CHECK:
        return {"width": 30, "bar_class": "bg-amber-500 animate-pulse", "active_step": "ai_check"}
    if status in [Syllabus.Status.REVIEW_DEAN, Syllabus.Status.SUBMITTED_DEAN]:
        return {"width": 60, "bar_class": "bg-blue-500", "active_step": "dean"}
    if status == Syllabus.Status.REVIEW_UMU:
        return {"width": 80, "bar_class": "bg-indigo-500", "active_step": "umu"}
    if status == Syllabus.Status.APPROVED:
        return {"width": 100, "bar_class": "bg-green-500", "active_step": "approved"}
    if status == Syllabus.Status.CORRECTION:
        if correction_stage_key == "umu":
            return {"width": 80, "bar_class": "bg-red-500", "active_step": "umu"}
        if correction_stage_key == "dean":
            return {"width": 60, "bar_class": "bg-red-500", "active_step": "dean"}
        if correction_stage_key == "ai_check":
            return {"width": 30, "bar_class": "bg-red-500", "active_step": "ai_check"}
        return {"width": 10, "bar_class": "bg-red-500", "active_step": "draft"}
    return {"width": 10, "bar_class": "bg-slate-400", "active_step": "draft"}


@login_required
def syllabi_list(request):
    """Личные силлабусы преподавателя."""
    if request.user.role in ["dean", "umu", "admin"] or request.user.is_superuser:
        base_qs = Syllabus.objects.select_related("course", "creator")
        allow_creator_filter = True
    else:
        base_qs = Syllabus.objects.filter(creator=request.user).select_related("course", "creator")
        allow_creator_filter = False

    q = (request.GET.get("q") or "").strip()
    status = (request.GET.get("status") or "").strip()
    year = (request.GET.get("year") or "").strip()
    course = (request.GET.get("course") or "").strip()
    creator = (request.GET.get("creator") or "").strip()

    syllabi = base_qs
    if q:
        syllabi = syllabi.filter(
            Q(course__code__icontains=q)
            | Q(course__title_ru__icontains=q)
            | Q(course__title_kz__icontains=q)
            | Q(course__title_en__icontains=q)
            | Q(semester__icontains=q)
            | Q(academic_year__icontains=q)
            | Q(creator__first_name__icontains=q)
            | Q(creator__last_name__icontains=q)
            | Q(creator__username__icontains=q)
        )
    if status:
        syllabi = syllabi.filter(status=status)
    if year:
        syllabi = syllabi.filter(academic_year=year)
    if course:
        syllabi = syllabi.filter(course_id=course)
    if allow_creator_filter and creator:
        syllabi = syllabi.filter(creator_id=creator)

    year_options = base_qs.values_list("academic_year", flat=True).distinct().order_by("-academic_year")
    course_options = base_qs.values("course_id", "course__code").distinct().order_by("course__code")
    
    creator_options = []
    if allow_creator_filter:
        creator_ids = base_qs.values_list("creator_id", flat=True).distinct()
        User = get_user_model()
        creator_options = list(User.objects.filter(id__in=creator_ids).order_by("last_name", "first_name", "username"))

    return render(
        request,
        "syllabi/syllabi_list.html",
        {
            "syllabi": syllabi,
            "filters": {"q": q, "status": status, "year": year, "course": course, "creator": creator},
            "status_options": Syllabus.Status.choices,
            "year_options": year_options,
            "course_options": course_options,
            "creator_options": creator_options,
            "allow_creator_filter": allow_creator_filter,
        },
    )


@login_required
@role_required("teacher", "program_leader")
def shared_syllabi_list(request):
    """Общие силлабусы (только утвержденные)."""
    base_qs = shared_syllabi_queryset(request.user).filter(status=Syllabus.Status.APPROVED).order_by("-updated_at")

    q = (request.GET.get("q") or "").strip()
    year = (request.GET.get("year") or "").strip()
    course = (request.GET.get("course") or "").strip()
    creator = (request.GET.get("creator") or "").strip()

    syllabi = base_qs
    if q:
        syllabi = syllabi.filter(
            Q(course__code__icontains=q)
            | Q(course__title_ru__icontains=q)
            | Q(course__title_kz__icontains=q)
            | Q(course__title_en__icontains=q)
            | Q(semester__icontains=q)
            | Q(academic_year__icontains=q)
            | Q(creator__first_name__icontains=q)
            | Q(creator__last_name__icontains=q)
            | Q(creator__username__icontains=q)
        )
    if year:
        syllabi = syllabi.filter(academic_year=year)
    if course:
        syllabi = syllabi.filter(course_id=course)
    if creator:
        syllabi = syllabi.filter(creator_id=creator)

    year_options = base_qs.values_list("academic_year", flat=True).distinct().order_by("-academic_year")
    course_options = base_qs.values("course_id", "course__code").distinct().order_by("course__code")
    
    creator_ids = base_qs.values_list("creator_id", flat=True).distinct()
    User = get_user_model()
    creator_options = list(User.objects.filter(id__in=creator_ids).order_by("last_name", "first_name", "username"))

    return render(
        request,
        "syllabi/shared_syllabi_list.html",
        {
            "syllabi": syllabi,
            "filters": {"q": q, "year": year, "course": course, "creator": creator},
            "year_options": year_options,
            "course_options": course_options,
            "creator_options": creator_options,
        },
    )


# =========================================================
#  ФУНКЦИЯ СОЗДАНИЯ (ТОЛЬКО ИМПОРТ PDF/WORD)
# =========================================================

@login_required
@role_required("teacher", "program_leader")
def syllabus_create(request):
    """
    Backward-compatible create endpoint.
    Allows creating a draft without a file and supports optional upload.
    """
    ensure_default_courses(request.user)

    if request.method == "POST":
        form = SyllabusForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            syllabus = form.save(commit=False)
            syllabus.creator = request.user

            if syllabus.pdf_file:
                syllabus.status = Syllabus.Status.AI_CHECK
                success_message = "File uploaded. AI check started."
            else:
                syllabus.status = Syllabus.Status.DRAFT
                success_message = "Syllabus created as draft."

            syllabus.save()
            messages.success(request, success_message)
            return redirect("syllabus_detail", pk=syllabus.pk)
    else:
        form = SyllabusForm(user=request.user)

    if not form.fields["course"].queryset.exists():
        messages.warning(request, "You have no available courses. Please contact admin.")

    return render(request, "syllabi/upload_pdf.html", {"form": form})


@login_required
@role_required("teacher", "program_leader")
def upload_pdf_view(request):
    """
    Сценарий: ИМПОРТ ФАЙЛА.
    Загрузка PDF/Word. Статус = AI_CHECK.
    """
    ensure_default_courses(request.user)

    if request.method == "POST":
        form = SyllabusForm(request.POST, request.FILES, user=request.user)
        if form.is_valid():
            syllabus = form.save(commit=False)
            syllabus.creator = request.user
            
            # Проверка наличия файла
            if not syllabus.pdf_file:
                messages.error(request, "Для проверки ИИ необходимо загрузить файл!")
            else:
                syllabus.status = Syllabus.Status.AI_CHECK # На проверку ИИ
                syllabus.save()
                messages.success(request, "Файл загружен! Запущена автоматическая проверка ИИ.")
                return redirect("syllabus_detail", pk=syllabus.pk)
    else:
        form = SyllabusForm(user=request.user)

    if not form.fields["course"].queryset.exists():
        messages.warning(request, "У вас нет доступных дисциплин. Обратитесь к администратору.")

    # Используем шаблон С полем загрузки файла
    return render(request, "syllabi/upload_pdf.html", {"form": form})

# =========================================================


@login_required
def syllabus_detail(request, pk):
    syllabus = get_object_or_404(Syllabus.objects.select_related("course", "creator"), pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    
    is_frozen = syllabus.status == Syllabus.Status.APPROVED
    is_creator = request.user == syllabus.creator
    role = request.user.role
    is_admin_like = request.user.is_admin_like or request.user.is_superuser
    is_dean = role == "dean" or is_admin_like
    is_umu = role == "umu" or is_admin_like
    is_teacher_like = request.user.is_teacher_like

    topics = list(
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )
    has_topics = bool(topics)
    derived_main_literature, derived_additional_literature = _build_literature_lists(topics)
    
    can_submit_dean = (
        is_creator
        and syllabus.status in [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION]
        and is_teacher_like
    )
    can_approve_dean = (
        syllabus.status == Syllabus.Status.REVIEW_DEAN
        and is_dean
        and not is_creator
    )
    can_approve_umu = (
        syllabus.status == Syllabus.Status.REVIEW_UMU
        and is_umu
        and not is_creator
    )
    can_upload = (is_creator and not is_frozen and is_teacher_like) or (is_umu and is_frozen)
    can_share = is_creator and is_teacher_like
    can_edit_constructor = (
        is_creator
        and is_teacher_like
        and syllabus.status in [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION]
    )
    correction_context = (
        _resolve_correction_context(syllabus)
        if syllabus.status == Syllabus.Status.CORRECTION
        else {"source_label": "", "comment": "", "stage_key": "draft", "is_ai_feedback": False}
    )
    progress_context = _build_progress_context(
        syllabus.status,
        correction_stage_key=correction_context.get("stage_key", "draft"),
    )

    return render(
        request,
        "syllabi/syllabus_detail.html",
        {
            "syllabus": syllabus,
            "topics": topics,
            "has_topics": has_topics,
            "is_frozen": is_frozen,
            "can_submit_dean": can_submit_dean,
            "can_approve_dean": can_approve_dean,
            "can_approve_umu": can_approve_umu,
            "can_reject_umu": can_approve_umu,
            "can_upload": can_upload,
            "can_share": can_share,
            "can_edit_constructor": can_edit_constructor,
            "is_creator": is_creator,
            "learning_outcomes_list": _split_lines(syllabus.learning_outcomes),
            "teaching_methods_list": _split_lines(syllabus.teaching_methods),
            "main_literature_list": _split_lines(syllabus.main_literature) or derived_main_literature,
            "additional_literature_list": _split_lines(syllabus.additional_literature) or derived_additional_literature,
            "correction_source_label": correction_context.get("source_label", ""),
            "correction_comment": correction_context.get("comment", ""),
            "correction_is_ai_feedback": correction_context.get("is_ai_feedback", False),
            "status_progress_width": progress_context["width"],
            "status_progress_class": progress_context["bar_class"],
            "status_progress_step": progress_context["active_step"],
        },
    )


@login_required
@role_required("teacher", "program_leader")
def syllabus_edit_topics(request, pk):
    syllabus = get_object_or_404(Syllabus.objects.select_related("course", "creator"), pk=pk)
    if request.user != syllabus.creator:
        raise PermissionDenied("Недостаточно прав для редактирования тем.")
    if syllabus.status not in [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION]:
        messages.warning(request, "Редактирование тем доступно только для черновика и доработки.")
        return redirect("syllabus_detail", pk=pk)

    course_topics = list(
        Topic.objects.filter(course=syllabus.course, is_active=True).order_by("order_index", "id")
    )
    existing_topics = {
        st.topic_id: st
        for st in syllabus.syllabus_topics.select_related("topic").filter(topic__is_active=True)
    }

    if request.method == "POST":
        included_topic_ids = []
        explicit_weeks = {}
        payload_by_topic_id = {}

        for topic in course_topics:
            topic_id = topic.id
            if f"include_{topic_id}" not in request.POST:
                continue

            included_topic_ids.append(topic_id)
            explicit_weeks[topic_id] = _parse_positive_int(request.POST.get(f"week_{topic_id}"))
            payload_by_topic_id[topic_id] = {
                "week_label": (request.POST.get(f"week_label_{topic_id}") or "").strip(),
                "custom_title": (request.POST.get(f"title_{topic_id}") or "").strip(),
                "custom_hours": _parse_positive_int(request.POST.get(f"hours_{topic_id}")),
                "tasks": (request.POST.get(f"tasks_{topic_id}") or "").strip(),
                "learning_outcomes": (request.POST.get(f"outcomes_{topic_id}") or "").strip(),
                "literature_notes": (request.POST.get(f"literature_{topic_id}") or "").strip(),
                "assessment": (request.POST.get(f"assessment_{topic_id}") or "").strip(),
            }

        used_weeks = {week for week in explicit_weeks.values() if week is not None}
        next_week = 1

        with transaction.atomic():
            syllabus.syllabus_topics.exclude(topic_id__in=included_topic_ids).delete()

            for topic_id in included_topic_ids:
                week_number = explicit_weeks.get(topic_id)
                if week_number is None:
                    while next_week in used_weeks:
                        next_week += 1
                    week_number = next_week
                    used_weeks.add(week_number)
                    next_week += 1

                syllabus_topic = existing_topics.get(topic_id)
                if syllabus_topic is None:
                    syllabus_topic = SyllabusTopic(syllabus=syllabus, topic_id=topic_id)

                payload = payload_by_topic_id[topic_id]
                syllabus_topic.week_number = week_number
                syllabus_topic.is_included = True
                syllabus_topic.week_label = payload["week_label"]
                syllabus_topic.custom_title = payload["custom_title"]
                syllabus_topic.custom_hours = payload["custom_hours"]
                syllabus_topic.tasks = payload["tasks"]
                syllabus_topic.learning_outcomes = payload["learning_outcomes"]
                syllabus_topic.literature_notes = payload["literature_notes"]
                syllabus_topic.assessment = payload["assessment"]
                syllabus_topic.save()

        SyllabusRevision.objects.create(
            syllabus=syllabus,
            changed_by=request.user,
            version_number=syllabus.version_number,
            note="Обновлена структура тем",
        )
        messages.success(request, "Темы силлабуса сохранены.")
        return redirect("syllabus_edit_details", pk=pk)

    topic_rows = []
    for topic in course_topics:
        existing = existing_topics.get(topic.id)
        topic_rows.append(
            {
                "topic": topic,
                "included": bool(existing and existing.is_included),
                "week_number": existing.week_number if existing else None,
                "week_label": existing.week_label if existing else "",
                "display_title": topic.get_title(syllabus.main_language),
                "custom_hours": existing.custom_hours if existing else None,
                "custom_title": existing.custom_title if existing else "",
                "tasks": existing.tasks if existing else "",
                "learning_outcomes": existing.learning_outcomes if existing else "",
                "literature_notes": existing.literature_notes if existing else "",
                "assessment": existing.assessment if existing else "",
            }
        )

    if not topic_rows:
        messages.info(request, "В банке тем пока нет активных тем для этой дисциплины.")

    return render(
        request,
        "syllabi/syllabus_edit_topics.html",
        {"syllabus": syllabus, "topics": topic_rows},
    )


@login_required
@role_required("teacher", "program_leader")
def syllabus_edit_details(request, pk):
    syllabus = get_object_or_404(Syllabus.objects.select_related("course", "creator"), pk=pk)
    if request.user != syllabus.creator:
        raise PermissionDenied("Недостаточно прав для редактирования деталей.")
    if syllabus.status not in [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION]:
        messages.warning(request, "Редактирование деталей доступно только для черновика и доработки.")
        return redirect("syllabus_detail", pk=pk)

    if request.method == "POST":
        form = SyllabusDetailsForm(request.POST, instance=syllabus)
        if form.is_valid():
            form.save()
            SyllabusRevision.objects.create(
                syllabus=syllabus,
                changed_by=request.user,
                version_number=syllabus.version_number,
                note="Обновлены детали силлабуса",
            )
            messages.success(request, "Детали силлабуса сохранены.")
            return redirect("syllabus_detail", pk=pk)
    else:
        form = SyllabusDetailsForm(instance=syllabus)

    return render(
        request,
        "syllabi/syllabus_edit_details.html",
        {"syllabus": syllabus, "form": form},
    )


@login_required
def syllabus_pdf(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    if syllabus.pdf_file:
        return redirect(syllabus.pdf_file.url)
    return generate_syllabus_pdf(syllabus)


@login_required
@require_POST
def send_to_ai_check(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if not _can_request_ai_check(request.user, syllabus):
        messages.error(request, "Нет прав для отправки на проверку ИИ.")
        return redirect('syllabus_detail', pk=pk)

    if syllabus.status not in AI_CHECK_START_STATUSES:
        messages.warning(request, "Силлабус уже на проверке или утвержден.")
        return redirect('syllabus_detail', pk=pk)

    validation_errors = validate_syllabus_structure(syllabus)
    if validation_errors:
        for error in validation_errors:
            messages.error(request, error)
        return redirect("syllabus_detail", pk=pk)

    syllabus.status = Syllabus.Status.AI_CHECK
    syllabus.ai_feedback = ""
    syllabus.save(update_fields=['status', 'ai_feedback'])
    SyllabusRevision.objects.create(
        syllabus=syllabus, changed_by=request.user, version_number=syllabus.version_number, note="Отправлено на проверку ИИ"
    )
    messages.success(request, "Силлабус отправлен на проверку ИИ. Ожидайте результата.")
    return redirect('syllabus_detail', pk=pk)


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
    redirect_candidates = [
        request.POST.get("next", "").strip(),
        request.GET.get("next", "").strip(),
        (request.META.get("HTTP_REFERER") or "").strip(),
    ]
    for candidate in redirect_candidates:
        if candidate and url_has_allowed_host_and_scheme(
            candidate,
            allowed_hosts={request.get_host()},
            require_https=request.is_secure(),
        ):
            return redirect(candidate)

    return redirect(reverse("syllabus_detail", args=[syllabus.pk]))


@login_required
def syllabus_upload_file(request, pk):
    """Загрузка файла внутри Деталей силлабуса (обновление версии)."""
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.method != "POST":
        return redirect("syllabus_detail", pk=pk)

    is_frozen = syllabus.status == Syllabus.Status.APPROVED
    is_creator = request.user == syllabus.creator
    is_umu = request.user.role == "umu" or request.user.is_superuser
    
    can_upload = (is_creator and not is_frozen) or (is_umu and is_frozen)
    if not can_upload:
        raise PermissionDenied("У вас нет прав на загрузку файла.")

    uploaded = request.FILES.get("attachment")
    if uploaded:
        if not is_allowed_syllabus_file_name(uploaded.name):
            messages.error(request, "Неверный тип файла. Загрузите PDF или Word (.pdf, .doc, .docx).")
            return redirect("syllabus_detail", pk=pk)

        syllabus.pdf_file.save(uploaded.name, uploaded, save=False)
        syllabus.version_number += 1
        
        # Если загрузил автор и статус позволяет - отправляем на ИИ
        if is_creator and syllabus.status in [Syllabus.Status.CORRECTION, Syllabus.Status.DRAFT]:
            syllabus.status = Syllabus.Status.AI_CHECK
            syllabus.ai_feedback = ""
            messages.success(request, "Файл обновлен! Запущен повторный анализ ИИ.")
        else:
             messages.success(request, "Файл обновлен.")
        
        syllabus.save()
        
        SyllabusRevision.objects.create(
            syllabus=syllabus,
            changed_by=request.user,
            version_number=syllabus.version_number,
            note="Загружен новый PDF (авто-проверка)",
        )
        SyllabusAuditLog.objects.create(
            syllabus=syllabus,
            actor=request.user,
            action=SyllabusAuditLog.Action.PDF_UPLOADED,
            metadata={"filename": uploaded.name},
            message="Загружен PDF",
        )

    return redirect("syllabus_detail", pk=pk)


@login_required
@role_required("teacher", "program_leader")
def syllabus_toggle_share(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.user != syllabus.creator:
        raise PermissionDenied("Недостаточно прав.")
    if request.method == "POST":
        syllabus.is_shared = not syllabus.is_shared
        syllabus.save(update_fields=["is_shared"])
    return redirect("syllabus_detail", pk=pk)
