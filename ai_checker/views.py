from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from syllabi.models import Syllabus
from syllabi.permissions import can_view_syllabus
from .assistant import answer_syllabus_question
from .models import AiCheckResult


AI_CHECK_START_STATUSES = {
    Syllabus.Status.DRAFT,
    Syllabus.Status.CORRECTION,
    Syllabus.Status.AI_CHECK,
}


def _can_view(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


def _can_request_ai_check(user, syllabus: Syllabus) -> bool:
    is_admin_like = bool(
        getattr(user, "is_superuser", False)
        or getattr(user, "is_admin_like", False)
        or getattr(user, "role", "") == "admin"
    )
    return user == syllabus.creator or is_admin_like


@login_required
def run_check(request, syllabus_pk):
    syllabus = get_object_or_404(Syllabus, pk=syllabus_pk)
    if not _can_view(request.user, syllabus):
        raise PermissionDenied("Access denied to this syllabus.")
    if not _can_request_ai_check(request.user, syllabus):
        raise PermissionDenied("Insufficient rights to run AI check.")
    if syllabus.status not in AI_CHECK_START_STATUSES:
        messages.error(
            request,
            "AI check can be started only from draft, correction, or AI_CHECK.",
        )
        return redirect("syllabus_detail", pk=syllabus.pk)
    if request.method == "POST":
        if syllabus.status != Syllabus.Status.AI_CHECK:
            syllabus.status = Syllabus.Status.AI_CHECK
            syllabus.ai_feedback = ""
            syllabus.save(update_fields=["status", "ai_feedback"])
            messages.success(request, "AI check started. Refresh after a while.")
        else:
            messages.info(request, "AI check is already running.")
        return redirect("syllabus_detail", pk=syllabus.pk)
    return redirect("syllabus_detail", pk=syllabus.pk)


@login_required
def check_detail(request, pk):
    check = get_object_or_404(AiCheckResult, pk=pk)
    if not _can_view(request.user, check.syllabus):
        raise PermissionDenied("Access denied to AI check result.")
    return render(request, "ai_checker/check_detail.html", {"check": check})


@login_required
@require_POST
def assistant_reply(request):
    message = request.POST.get("message", "").strip()
    syllabus_id = request.POST.get("syllabus_id", "").strip()
    syllabus = None

    if syllabus_id:
        syllabus = get_object_or_404(Syllabus, pk=syllabus_id)
        if not _can_view(request.user, syllabus):
            raise PermissionDenied("Access denied to selected syllabus.")

    if not message:
        return render(
            request,
            "ai_checker/assistant_response.html",
            {
                "question": "",
                "answer": "Enter a question to get an answer.",
                "model_name": "",
            },
        )

    answer, model_name = answer_syllabus_question(message, syllabus)
    if model_name == "rules-only":
        model_name = ""
    return render(
        request,
        "ai_checker/assistant_response.html",
        {
            "question": message,
            "answer": answer,
            "model_name": model_name,
        },
    )
