from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from syllabi.models import Syllabus
from syllabi.permissions import can_view_syllabus
from .assistant import answer_syllabus_question
from .models import AiCheckResult
from .services import run_ai_check


def _can_view(user, syllabus: Syllabus) -> bool:
    return can_view_syllabus(user, syllabus)


@login_required
def run_check(request, syllabus_pk):
    syllabus = get_object_or_404(Syllabus, pk=syllabus_pk)
    if not _can_view(request.user, syllabus):
        raise PermissionDenied("Нет доступа к этому силлабусу.")
    if request.method == "POST":
        check = run_ai_check(syllabus)
        return redirect("ai_check_detail", pk=check.pk)
    return redirect("syllabus_detail", pk=syllabus.pk)


@login_required
def check_detail(request, pk):
    check = get_object_or_404(AiCheckResult, pk=pk)
    if not _can_view(request.user, check.syllabus):
        raise PermissionDenied("Нет доступа к результату проверки.")
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
            raise PermissionDenied("Нет доступа к выбранному силлабусу.")

    if not message:
        return render(
            request,
            "ai_checker/assistant_response.html",
            {
                "question": "",
                "answer": "Введите вопрос, чтобы получить подсказку.",
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
