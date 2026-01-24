from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.utils import timezone

from ai_checker.models import AiCheckResult
from catalog.models import Course, Topic, TopicLiterature, TopicQuestion
from core.models import Announcement
from syllabi.models import Syllabus, SyllabusRevision, SyllabusTopic
from workflow.services import change_status


class Command(BaseCommand):
    help = "Seed demo data for testing."

    def handle(self, *args, **options):
        original_email_backend = settings.EMAIL_BACKEND
        settings.EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
        try:
            users = _ensure_users()
            courses = _ensure_courses(users)
            _ensure_topics(courses)
            syllabi = _ensure_syllabi(courses, users)
            _ensure_ai_checks(syllabi)
            _ensure_announcements(users)
        finally:
            settings.EMAIL_BACKEND = original_email_backend

        self.stdout.write(self.style.SUCCESS("Demo data ready."))


def _ensure_users():
    User = get_user_model()
    defaults = [
        ("teacher1", "teacher", "Aruzhan", "Suleimen", "teacher1@almau.demo"),
        ("teacher2", "teacher", "Daniyar", "Kenzhe", "teacher2@almau.demo"),
        ("leader1", "program_leader", "Aigerim", "Tulen", "leader1@almau.demo"),
        ("dean1", "dean", "Bolat", "Nur", "dean1@almau.demo"),
        ("umu1", "umu", "Dana", "Bek", "umu1@almau.demo"),
    ]
    users = {}
    for username, role, first_name, last_name, email in defaults:
        user = User.objects.filter(username=username).first()
        if not user:
            user = User(
                username=username,
                first_name=first_name,
                last_name=last_name,
                email=email,
                role=role,
                is_active=True,
            )
            if hasattr(user, "email_verified"):
                user.email_verified = True
            user.set_password("Test1234!")
            user.save()
        users[username] = user
    return users


def _ensure_courses(users):
    courses_data = [
        {
            "code": "DEMO-IS101",
            "title_ru": "Информационные системы",
            "title_kz": "Ақпараттық жүйелер",
            "title_en": "Information Systems",
            "description_ru": "Базовые принципы создания и внедрения информационных систем.",
            "description_kz": "Ақпараттық жүйелерді жобалау және енгізу негіздері.",
            "description_en": "Core concepts of designing and implementing information systems.",
            "owner": users["teacher1"],
            "is_shared": True,
        },
        {
            "code": "DEMO-DS201",
            "title_ru": "Основы Data Science",
            "title_kz": "Data Science негіздері",
            "title_en": "Data Science Fundamentals",
            "description_ru": "Данные, статистика и первые модели машинного обучения.",
            "description_kz": "Деректер, статистика және машиналық оқытуға кіріспе.",
            "description_en": "Data, statistics, and introductory machine learning.",
            "owner": users["teacher1"],
            "is_shared": True,
        },
        {
            "code": "DEMO-SE210",
            "title_ru": "Инженерия программного обеспечения",
            "title_kz": "Бағдарламалық қамтамасыз ету инженериясы",
            "title_en": "Software Engineering",
            "description_ru": "Полный цикл разработки ПО и командные практики.",
            "description_kz": "Бағдарламалық өнімді әзірлеу өмірлік циклі.",
            "description_en": "Full software lifecycle and team practices.",
            "owner": users["teacher2"],
            "is_shared": False,
        },
        {
            "code": "DEMO-BA220",
            "title_ru": "Бизнес-аналитика",
            "title_kz": "Бизнес-аналитика",
            "title_en": "Business Analytics",
            "description_ru": "Метрики, требования и принятие решений на основе данных.",
            "description_kz": "Метрикалар, талаптар және деректерге негізделген шешімдер.",
            "description_en": "Metrics, requirements, and data-driven decision making.",
            "owner": users["leader1"],
            "is_shared": True,
        },
        {
            "code": "DEMO-AI301",
            "title_ru": "Прикладной искусственный интеллект",
            "title_kz": "Қолданбалы жасанды интеллект",
            "title_en": "Applied Artificial Intelligence",
            "description_ru": "Практика применения ИИ в бизнесе и ИТ.",
            "description_kz": "ИИ-ді бизнес пен ІТ-де қолдану тәжірибесі.",
            "description_en": "Practical AI applications in business and IT.",
            "owner": users["teacher2"],
            "is_shared": False,
        },
    ]

    courses = []
    for item in courses_data:
        course, created = Course.objects.get_or_create(
            code=item["code"],
            defaults={
                "owner": item["owner"],
                "title_ru": item["title_ru"],
                "title_kz": item["title_kz"],
                "title_en": item["title_en"],
                "description_ru": item["description_ru"],
                "description_kz": item["description_kz"],
                "description_en": item["description_en"],
                "available_languages": "ru,kz,en",
                "is_shared": item["is_shared"],
            },
        )
        courses.append(course)
    return courses


def _ensure_topics(courses):
    topic_map = {
        "DEMO-IS101": [
            ("Введение в информационные системы", "Ақпараттық жүйелерге кіріспе", "Introduction to Information Systems"),
            ("Моделирование процессов (BPMN)", "Процестерді модельдеу (BPMN)", "Process Modeling (BPMN)"),
            ("Архитектура ИС", "АЖ архитектурасы", "IS Architecture"),
            ("Базы данных и ER-модели", "Деректер базасы және ER-модель", "Databases and ER Models"),
            ("Проектирование интерфейсов", "Интерфейс жобалау", "Interface Design"),
            ("Интеграция и API", "Интеграция және API", "Integration and API"),
            ("Безопасность ИС", "АЖ қауіпсіздігі", "IS Security"),
            ("Проект внедрения", "Енгізу жобасы", "Implementation Project"),
        ],
        "DEMO-DS201": [
            ("Введение в Data Science", "Data Science-ке кіріспе", "Introduction to Data Science"),
            ("Python для анализа данных", "Деректерді талдауға Python", "Python for Data Analysis"),
            ("Сбор и очистка данных", "Деректерді жинау және тазалау", "Data Collection and Cleaning"),
            ("Статистика и вероятности", "Статистика және ықтималдық", "Statistics and Probability"),
            ("Регрессия и прогноз", "Регрессия және болжау", "Regression and Forecasting"),
            ("Классификация", "Классификация", "Classification"),
            ("Оценка моделей", "Модельдерді бағалау", "Model Evaluation"),
            ("Визуализация данных", "Деректерді визуализациялау", "Data Visualization"),
        ],
        "DEMO-SE210": [
            ("Жизненный цикл ПО", "БҚ өмірлік циклі", "Software Lifecycle"),
            ("Сбор требований", "Талаптарды жинау", "Requirements Gathering"),
            ("Архитектура и паттерны", "Архитектура және паттерндер", "Architecture and Patterns"),
            ("Тестирование и QA", "Тестілеу және QA", "Testing and QA"),
            ("CI/CD и автоматизация", "CI/CD және автоматтандыру", "CI/CD and Automation"),
            ("Командная разработка", "Командалық әзірлеу", "Team Development"),
            ("Качество кода", "Код сапасы", "Code Quality"),
            ("Командный проект", "Командалық жоба", "Team Project"),
        ],
        "DEMO-BA220": [
            ("Основы бизнес-аналитики", "Бизнес-аналитика негіздері", "Business Analytics Foundations"),
            ("Метрики и KPI", "Метрикалар және KPI", "Metrics and KPIs"),
            ("Сбор требований", "Талаптарды жинау", "Requirements Collection"),
            ("SQL для аналитиков", "Аналитиктерге SQL", "SQL for Analysts"),
            ("BI-инструменты", "BI-құралдар", "BI Tools"),
            ("Моделирование процессов", "Процестерді модельдеу", "Process Modeling"),
            ("Презентация инсайтов", "Инсайттарды ұсыну", "Presenting Insights"),
            ("Бизнес-кейс", "Бизнес-кейс", "Business Case"),
        ],
        "DEMO-AI301": [
            ("Введение в ИИ", "ИИ-ге кіріспе", "Introduction to AI"),
            ("NLP и языковые модели", "NLP және тілдік модельдер", "NLP and Language Models"),
            ("Computer Vision", "Computer Vision", "Computer Vision"),
            ("Рекомендательные системы", "Ұсыну жүйелері", "Recommender Systems"),
            ("Prompting и LLM", "Prompting және LLM", "Prompting and LLMs"),
            ("MLOps и деплой", "MLOps және деплой", "MLOps and Deployment"),
            ("Этика и безопасность", "Этика және қауіпсіздік", "Ethics and Safety"),
            ("Прикладной проект", "Қолданбалы жоба", "Applied Project"),
        ],
    }

    for course in courses:
        if course.topics.exists():
            continue
        topics = topic_map.get(course.code, [])
        for idx, (title_ru, title_kz, title_en) in enumerate(topics, start=1):
            topic = Topic.objects.create(
                course=course,
                order_index=idx,
                title_ru=title_ru,
                title_kz=title_kz,
                title_en=title_en,
                description_ru=f"Краткое описание темы: {title_ru}.",
                description_kz=f"Тақырыптың қысқаша сипаттамасы: {title_kz}.",
                description_en=f"Topic overview: {title_en}.",
                default_hours=2,
                week_type=Topic.WeekType.LECTURE if idx % 3 else Topic.WeekType.PRACTICE,
                is_active=True,
            )

            TopicLiterature.objects.create(
                topic=topic,
                title=f"{course.title_en} Essentials",
                author="AlmaU Press",
                year="2024",
                lit_type=TopicLiterature.LitType.MAIN,
            )
            TopicLiterature.objects.create(
                topic=topic,
                title=f"Selected readings on {title_en}",
                author="Various",
                year="2023",
                lit_type=TopicLiterature.LitType.ADDITIONAL,
            )

            TopicQuestion.objects.create(
                topic=topic,
                question_ru=f"Какие ключевые идеи раскрывает тема «{title_ru}»?",
                question_kz=f"«{title_kz}» тақырыбының негізгі идеялары қандай?",
                question_en=f"What are the key ideas of \"{title_en}\"?",
            )
            TopicQuestion.objects.create(
                topic=topic,
                question_ru=f"Как применить тему «{title_ru}» на практике?",
                question_kz=f"«{title_kz}» тақырыбын практикада қалай қолданамыз?",
                question_en=f"How can \"{title_en}\" be applied in practice?",
            )


def _ensure_syllabi(courses, users):
    course_by_code = {course.code: course for course in courses}
    syllabus_seeds = [
        ("DEMO-IS101", "Fall 2025", "2025/2026", users["teacher1"], Syllabus.Status.DRAFT, False),
        ("DEMO-DS201", "Fall 2025", "2025/2026", users["teacher1"], Syllabus.Status.SUBMITTED_DEAN, False),
        ("DEMO-SE210", "Fall 2025", "2025/2026", users["teacher2"], Syllabus.Status.APPROVED_DEAN, False),
        ("DEMO-BA220", "Fall 2025", "2025/2026", users["leader1"], Syllabus.Status.SUBMITTED_UMU, True),
        ("DEMO-AI301", "Fall 2025", "2025/2026", users["teacher2"], Syllabus.Status.APPROVED_UMU, True),
        ("DEMO-IS101", "Spring 2026", "2025/2026", users["teacher1"], Syllabus.Status.REJECTED, False),
    ]

    syllabi = []
    for code, semester, year, creator, target_status, is_shared in syllabus_seeds:
        course = course_by_code.get(code)
        if not course:
            continue
        syllabus, created = Syllabus.objects.get_or_create(
            course=course,
            creator=creator,
            semester=semester,
            academic_year=year,
            defaults={
                "status": Syllabus.Status.DRAFT,
                "total_weeks": 8,
                "main_language": "ru",
                "is_shared": is_shared,
                "credits_ects": "5",
                "total_hours": 90,
                "contact_hours": 45,
                "self_study_hours": 45,
                "delivery_format": "Очный",
                "level": "Бакалавриат",
                "program_name": "Информационные технологии",
                "instructor_name": creator.get_full_name() or creator.username,
                "instructor_contacts": creator.email,
                "course_description": course.description_ru,
                "course_goal": "Сформировать практические навыки и понимание ключевых концепций.",
                "learning_outcomes": "Понимание ключевых концепций\nНавыки анализа кейсов\nПрактическая работа",
                "teaching_methods": "Лекции\nПрактические занятия\nКейс-стади",
                "assessment_policy": "Текущие задания 40%\nПроект 30%\nИтоговый экзамен 30%",
            },
        )
        if created:
            _attach_topics(syllabus)
            SyllabusRevision.objects.create(
                syllabus=syllabus,
                changed_by=creator,
                note="Первичная версия",
                version_number=1,
            )
            _advance_status(syllabus, target_status, users, creator)
        syllabi.append(syllabus)
    return syllabi


def _attach_topics(syllabus):
    topics = list(syllabus.course.topics.order_by("order_index"))
    for idx, topic in enumerate(topics, start=1):
        SyllabusTopic.objects.get_or_create(
            syllabus=syllabus,
            topic=topic,
            defaults={
                "week_number": idx,
                "week_label": str(idx),
                "tasks": "Домашнее задание и мини-кейс.",
                "learning_outcomes": "Применять знания на практике.",
                "literature_notes": "",
                "assessment": "Мини-отчет или презентация.",
            },
        )


def _advance_status(syllabus, target_status, users, creator):
    if target_status == Syllabus.Status.DRAFT:
        return

    dean = users["dean1"]
    umu = users["umu1"]

    if target_status == Syllabus.Status.SUBMITTED_DEAN:
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_DEAN)
        return

    if target_status == Syllabus.Status.APPROVED_DEAN:
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_DEAN)
        change_status(dean, syllabus, Syllabus.Status.APPROVED_DEAN)
        return

    if target_status == Syllabus.Status.SUBMITTED_UMU:
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_DEAN)
        change_status(dean, syllabus, Syllabus.Status.APPROVED_DEAN)
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_UMU)
        return

    if target_status == Syllabus.Status.APPROVED_UMU:
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_DEAN)
        change_status(dean, syllabus, Syllabus.Status.APPROVED_DEAN)
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_UMU)
        change_status(umu, syllabus, Syllabus.Status.APPROVED_UMU)
        return

    if target_status == Syllabus.Status.REJECTED:
        change_status(creator, syllabus, Syllabus.Status.SUBMITTED_DEAN)
        change_status(
            dean,
            syllabus,
            Syllabus.Status.REJECTED,
            comment="Нужны правки по нагрузке и структуре.",
        )


def _ensure_ai_checks(syllabi):
    for syllabus in syllabi[:2]:
        if syllabus.ai_checks.exists():
            continue
        AiCheckResult.objects.create(
            syllabus=syllabus,
            created_at=timezone.now(),
            model_name="rules-only",
            summary="Демо-проверка: структура заполнена, критических проблем нет.",
            raw_result={"demo": True},
        )


def _ensure_announcements(users):
    if Announcement.objects.exists():
        return
    announcements = [
        {
            "title": "График согласований на семестр",
            "body": "Деканат принимает заявки на согласование до 15 сентября. После проверки документ будет направлен в УМУ.",
            "created_by": users["dean1"],
        },
        {
            "title": "Обновление требований к силлабусам",
            "body": "Проверьте заполнение целей, результатов обучения и списка литературы. "
            "Используйте единый формат названий тем.",
            "created_by": users["umu1"],
        },
        {
            "title": "Напоминание по отчетности",
            "body": "Пожалуйста, обновите рабочие программы дисциплин до конца месяца.",
            "created_by": users["dean1"],
        },
    ]
    for item in announcements:
        Announcement.objects.create(**item)
