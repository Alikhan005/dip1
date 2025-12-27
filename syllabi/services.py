from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string


def generate_syllabus_pdf(syllabus):
    """
    Generate PDF or return informative 501 if WeasyPrint deps are missing.
    We import WeasyPrint lazily to avoid command-time failures when system libs aren't installed.
    """
    try:
        from weasyprint import HTML  # type: ignore
    except Exception:  # pragma: no cover - environment without system deps
        return HttpResponse(
            "Системные зависимости WeasyPrint не установлены. "
            "Установите GTK/Pango (см. https://doc.courtbouillon.org/weasyprint/stable/first_steps.html#installation) "
            "или замените реализацию генерации PDF.",
            status=501,
            content_type="text/plain; charset=utf-8",
        )

    topics = (
        syllabus.syllabus_topics.select_related("topic")
        .prefetch_related("topic__literature", "topic__questions")
        .order_by("week_number")
    )
    html = render_to_string(
        "syllabi/pdf.html",
        {
            "syllabus": syllabus,
            "topics": topics,
        },
    )

    pdf_io = BytesIO()
    HTML(string=html).write_pdf(target=pdf_io)
    pdf_io.seek(0)

    response = HttpResponse(pdf_io.getvalue(), content_type="application/pdf")
    safe_code = syllabus.course.code.replace(" ", "_")
    response["Content-Disposition"] = (
        f'attachment; filename="syllabus-{safe_code}-v{syllabus.version_number}.pdf"'
    )
    return response
