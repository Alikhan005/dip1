from collections import Counter
from io import BytesIO

from django.http import HttpResponse
from django.template.loader import render_to_string


def _split_lines(value: str) -> list[str]:
    if not value:
        return []
    items = []
    for raw in value.splitlines():
        cleaned = raw.strip().lstrip("-•").strip()
        if cleaned:
            items.append(cleaned)
    return items


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


def validate_syllabus_structure(syllabus) -> list[str]:
    errors = []
    topics = list(syllabus.syllabus_topics.all())
    if not topics:
        return ["Добавьте хотя бы одну тему."]

    week_numbers = [st.week_number for st in topics if st.week_number]
    if len(week_numbers) != len(topics):
        errors.append("Есть темы без номера недели.")

    counts = Counter(week_numbers)
    duplicates = sorted(week for week, count in counts.items() if count > 1)
    if duplicates:
        errors.append("Повторяются недели: " + ", ".join(str(week) for week in duplicates) + ".")

    if syllabus.total_weeks and week_numbers:
        max_week = max(week_numbers)
        if max_week > syllabus.total_weeks:
            errors.append(
                f"Номер недели {max_week} выходит за предел {syllabus.total_weeks}."
            )

    return errors


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
    derived_main_literature, derived_additional_literature = _build_literature_lists(topics)
    main_literature_list = _split_lines(syllabus.main_literature) or derived_main_literature
    additional_literature_list = (
        _split_lines(syllabus.additional_literature) or derived_additional_literature
    )
    learning_outcomes_list = _split_lines(syllabus.learning_outcomes)
    teaching_methods_list = _split_lines(syllabus.teaching_methods)
    html = render_to_string(
        "syllabi/pdf.html",
        {
            "syllabus": syllabus,
            "topics": topics,
            "learning_outcomes_list": learning_outcomes_list,
            "teaching_methods_list": teaching_methods_list,
            "main_literature_list": main_literature_list,
            "additional_literature_list": additional_literature_list,
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
