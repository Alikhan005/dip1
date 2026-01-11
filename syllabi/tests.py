from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Course
from syllabi.models import Syllabus

User = get_user_model()


class SyllabusRoleViewTests(TestCase):
    def _create_user(self, username: str, role: str) -> User:
        return User.objects.create_user(username=username, password="pass1234", role=role)

    def _create_course(self, owner: User, code: str = "CS101") -> Course:
        return Course.objects.create(
            owner=owner,
            code=code,
            available_languages="ru",
        )

    def test_teacher_can_create_syllabus(self):
        teacher = self._create_user("teacher_user", "teacher")
        course = self._create_course(teacher)
        self.client.force_login(teacher)

        response = self.client.post(
            reverse("syllabus_create"),
            {
                "course": course.pk,
                "semester": "Fall 2025",
                "academic_year": "2025-2026",
                "total_weeks": 15,
                "main_language": "ru",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertTrue(Syllabus.objects.filter(creator=teacher, course=course).exists())

    def test_dean_cannot_create_syllabus(self):
        dean = self._create_user("dean_user", "dean")
        course = self._create_course(dean)
        self.client.force_login(dean)

        response = self.client.post(
            reverse("syllabus_create"),
            {
                "course": course.pk,
                "semester": "Fall 2025",
                "academic_year": "2025-2026",
                "total_weeks": 15,
                "main_language": "ru",
            },
        )

        self.assertEqual(response.status_code, 403)

    def test_umu_buttons_visible_for_submitted_umu(self):
        teacher = self._create_user("teacher_user", "teacher")
        umu = self._create_user("umu_user", "umu")
        course = self._create_course(teacher)
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.SUBMITTED_UMU,
        )

        self.client.force_login(umu)
        response = self.client.get(reverse("syllabus_detail", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["can_approve_umu"])
        self.assertTrue(response.context["can_reject_umu"])

    def test_umu_buttons_hidden_for_author(self):
        umu = self._create_user("umu_author", "umu")
        course = self._create_course(umu, code="CS202")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=umu,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.SUBMITTED_UMU,
        )

        self.client.force_login(umu)
        response = self.client.get(reverse("syllabus_detail", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.context["can_approve_umu"])
