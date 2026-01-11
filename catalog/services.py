from catalog.models import Course


DEFAULT_COURSES = [
    {
        "code": "CS101",
        "title_ru": "Основы программирования",
        "available_languages": "ru",
    },
    {
        "code": "IT102",
        "title_ru": "Информационные технологии",
        "available_languages": "ru",
    },
    {
        "code": "MATH101",
        "title_ru": "Высшая математика",
        "available_languages": "ru",
    },
    {
        "code": "STAT201",
        "title_ru": "Статистика",
        "available_languages": "ru",
    },
    {
        "code": "ECON101",
        "title_ru": "Экономика",
        "available_languages": "ru",
    },
    {
        "code": "FIN201",
        "title_ru": "Финансы",
        "available_languages": "ru",
    },
    {
        "code": "MKT201",
        "title_ru": "Маркетинг",
        "available_languages": "ru",
    },
    {
        "code": "MGMT101",
        "title_ru": "Менеджмент",
        "available_languages": "ru",
    },
    {
        "code": "LAW101",
        "title_ru": "Основы права",
        "available_languages": "ru",
    },
    {
        "code": "ENG101",
        "title_ru": "Английский язык (профильный)",
        "available_languages": "ru",
    },
]


def ensure_default_courses(user) -> list[Course]:
    if not user:
        return []
    if Course.objects.filter(owner=user).exists():
        return []

    created = []
    for item in DEFAULT_COURSES:
        created.append(
            Course.objects.create(
                owner=user,
                is_shared=False,
                **item,
            )
        )
    return created
