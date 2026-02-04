from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from accounts.decorators import role_required
from catalog.services import ensure_default_courses
from workflow.models import SyllabusAuditLog
from workflow.services import change_status
from .forms import SyllabusForm
from .models import Syllabus, SyllabusRevision
from .permissions import can_view_syllabus, shared_syllabi_queryset
from .services import generate_syllabus_pdf


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
            "is_creator": is_creator,
            "learning_outcomes_list": _split_lines(syllabus.learning_outcomes),
            "teaching_methods_list": _split_lines(syllabus.teaching_methods),
            "main_literature_list": _split_lines(syllabus.main_literature) or derived_main_literature,
            "additional_literature_list": _split_lines(syllabus.additional_literature) or derived_additional_literature,
        },
    )


@login_required
@role_required("teacher", "program_leader")
def syllabus_edit_topics(request, pk):
    messages.info(request, "Ручное редактирование тем отключено. Пожалуйста, внесите изменения в файл и загрузите его заново.")
    return redirect("syllabus_detail", pk=pk)


@login_required
@role_required("teacher", "program_leader")
def syllabus_edit_details(request, pk):
    messages.info(request, "Ручное редактирование полей отключено. Пожалуйста, внесите изменения в файл и загрузите его заново.")
    return redirect("syllabus_detail", pk=pk)


@login_required
def syllabus_pdf(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if not _can_view_syllabus(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    if syllabus.pdf_file:
        return redirect(syllabus.pdf_file.url)
    return generate_syllabus_pdf(syllabus)


@login_required
def send_to_ai_check(request, pk):
    syllabus = get_object_or_404(Syllabus, pk=pk)
    if request.user != syllabus.creator:
        messages.error(request, "Только создатель может отправить силлабус на проверку.")
        return redirect('syllabus_detail', pk=pk)

    if syllabus.status not in [Syllabus.Status.DRAFT, Syllabus.Status.CORRECTION]:
        messages.warning(request, "Силлабус уже на проверке или утвержден.")
        return redirect('syllabus_detail', pk=pk)

    syllabus.status = Syllabus.Status.AI_CHECK
    syllabus.save(update_fields=['status'])
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
    return redirect("syllabus_detail", pk=syllabus.pk)


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