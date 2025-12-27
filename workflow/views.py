from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect

from syllabi.models import Syllabus
from .services import change_status


@login_required
def change_status_view(request, pk, new_status):
    syllabus = get_object_or_404(Syllabus, pk=pk)

    if request.method == "POST":
        comment = request.POST.get("comment", "")
        change_status(request.user, syllabus, new_status, comment)

    return redirect("syllabus_detail", pk=syllabus.pk)
