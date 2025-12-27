from django.db.models import Q

from catalog.models import Course
from .models import Syllabus

_SIMILAR_ROLES = {"teacher", "program_leader"}


def _similarity_filter(user) -> Q:
    courses = Course.objects.filter(owner=user)
    filters = Q()

    codes = list(courses.values_list("code", flat=True))
    if codes:
        filters |= Q(course__code__in=codes)

    titles_ru = list(courses.exclude(title_ru="").values_list("title_ru", flat=True))
    if titles_ru:
        filters |= Q(course__title_ru__in=titles_ru)

    titles_kz = list(courses.exclude(title_kz="").values_list("title_kz", flat=True))
    if titles_kz:
        filters |= Q(course__title_kz__in=titles_kz)

    titles_en = list(courses.exclude(title_en="").values_list("title_en", flat=True))
    if titles_en:
        filters |= Q(course__title_en__in=titles_en)

    return filters


def shared_syllabi_queryset(user):
    qs = Syllabus.objects.filter(is_shared=True).select_related("course", "creator")

    if user.role in ["admin", "dean", "umu"]:
        return qs

    if user.role not in _SIMILAR_ROLES:
        return qs.none()

    filters = _similarity_filter(user)
    if not filters:
        return qs.none()

    return qs.filter(filters)


def can_view_syllabus(user, syllabus: Syllabus) -> bool:
    if user == syllabus.creator:
        return True
    if user.role in ["admin", "dean", "umu"]:
        return True
    if syllabus.is_shared and user.role in _SIMILAR_ROLES:
        return shared_syllabi_queryset(user).filter(pk=syllabus.pk).exists()
    return False
