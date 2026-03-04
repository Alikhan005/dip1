from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse

from catalog.models import Course, Topic
from syllabi.forms import SyllabusForm
from syllabi.models import Syllabus, SyllabusTopic

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

    def _create_topic(self, course: Course, title: str = "Topic 1", order_index: int = 1) -> Topic:
        return Topic.objects.create(
            course=course,
            order_index=order_index,
            title_ru=title,
            default_hours=2,
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

    def test_force_submit_button_visible_for_author_on_correction(self):
        teacher = self._create_user("teacher_force_button", "teacher")
        course = self._create_course(teacher, code="CS404")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.CORRECTION,
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("syllabus_detail", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Все равно отправить силлабус")

    def test_author_can_force_submit_from_correction(self):
        teacher = self._create_user("teacher_force_submit", "teacher")
        course = self._create_course(teacher, code="CS405")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.CORRECTION,
        )

        self.client.force_login(teacher)
        response = self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.REVIEW_DEAN]),
            {"comment": "Автор уверен в корректности и отправил без правок."},
        )

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.REVIEW_DEAN)

    def test_non_author_cannot_force_submit_from_correction(self):
        teacher = self._create_user("teacher_owner", "teacher")
        another_teacher = self._create_user("teacher_other", "teacher")
        course = self._create_course(teacher, code="CS406")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.CORRECTION,
        )

        self.client.force_login(another_teacher)
        response = self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.REVIEW_DEAN]),
            {"comment": "Пробую отправить чужой силлабус."},
        )

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.CORRECTION)

    def test_control_panel_hidden_for_author_on_correction(self):
        teacher = self._create_user("teacher_no_panel", "teacher")
        course = self._create_course(teacher, code="CS407")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.CORRECTION,
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("syllabus_detail", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Панель управления")

    def test_umu_reject_redirects_back_to_dashboard_when_next_is_set(self):
        teacher = self._create_user("teacher_redirect_back", "teacher")
        umu = self._create_user("umu_redirect_back", "umu")
        course = self._create_course(teacher, code="CS407A")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_UMU,
        )

        self.client.force_login(umu)
        response = self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.CORRECTION]),
            {"comment": "Нужно доработать раздел литературы.", "next": reverse("dashboard")},
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("dashboard"))
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.CORRECTION)

    def test_teacher_dashboard_shows_umu_correction_note(self):
        teacher = self._create_user("teacher_dash_note", "teacher")
        umu = self._create_user("umu_dash_note", "umu")
        course = self._create_course(teacher, code="CS407B")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_UMU,
        )

        self.client.force_login(umu)
        self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.CORRECTION]),
            {"comment": "Добавьте недостающие исходы обучения."},
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Возврат от УМУ")
        self.assertContains(response, "Добавьте недостающие исходы обучения.")

    def test_teacher_detail_shows_russian_umu_correction_block(self):
        teacher = self._create_user("teacher_detail_note", "teacher")
        umu = self._create_user("umu_detail_note", "umu")
        course = self._create_course(teacher, code="CS407C")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_UMU,
        )

        self.client.force_login(umu)
        self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.CORRECTION]),
            {"comment": "Причина понятная"},
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("syllabus_detail", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "возврат: УМУ")
        self.assertContains(response, "Причина понятная")
        self.assertNotContains(response, "returned for correction")

    def test_send_to_ai_check_requires_post(self):
        teacher = self._create_user("teacher_send_ai_get", "teacher")
        course = self._create_course(teacher, code="CS408")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)
        response = self.client.get(reverse("send_to_ai_check", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 405)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)

    def test_send_to_ai_check_post_updates_status(self):
        teacher = self._create_user("teacher_send_ai_post", "teacher")
        course = self._create_course(teacher, code="CS409")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
            main_literature="Core textbook",
        )
        topic = self._create_topic(course, title="Intro")
        SyllabusTopic.objects.create(syllabus=syllabus, topic=topic, week_number=1, is_included=True)

        self.client.force_login(teacher)
        response = self.client.post(reverse("send_to_ai_check", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.AI_CHECK)

    def test_send_to_ai_check_blocks_invalid_structure(self):
        teacher = self._create_user("teacher_send_ai_invalid", "teacher")
        course = self._create_course(teacher, code="CS409A")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)
        response = self.client.post(reverse("send_to_ai_check", args=[syllabus.pk]))

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)

    def test_syllabus_edit_topics_post_saves_syllabus_topic(self):
        teacher = self._create_user("teacher_edit_topics", "teacher")
        course = self._create_course(teacher, code="CS414")
        topic = self._create_topic(course, title="Algorithms")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)
        response = self.client.post(
            reverse("syllabus_edit_topics", args=[syllabus.pk]),
            {
                f"include_{topic.pk}": "on",
                f"week_{topic.pk}": "2",
                f"week_label_{topic.pk}": "2",
                f"hours_{topic.pk}": "3",
                f"title_{topic.pk}": "Algorithms Basics",
                f"tasks_{topic.pk}": "Read chapter 1",
                f"outcomes_{topic.pk}": "Understand complexity",
                f"literature_{topic.pk}": "CLRS",
                f"assessment_{topic.pk}": "Quiz",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("syllabus_edit_details", args=[syllabus.pk]))
        syllabus_topic = SyllabusTopic.objects.get(syllabus=syllabus, topic=topic)
        self.assertEqual(syllabus_topic.week_number, 2)
        self.assertEqual(syllabus_topic.custom_hours, 3)
        self.assertEqual(syllabus_topic.custom_title, "Algorithms Basics")
        self.assertEqual(syllabus_topic.tasks, "Read chapter 1")

    def test_syllabus_edit_details_post_updates_fields(self):
        teacher = self._create_user("teacher_edit_details", "teacher")
        course = self._create_course(teacher, code="CS415")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)
        response = self.client.post(
            reverse("syllabus_edit_details", args=[syllabus.pk]),
            {
                "credits_ects": "5",
                "total_hours": "150",
                "instructor_name": "Dr. Test",
                "course_description": "Updated description",
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("syllabus_detail", args=[syllabus.pk]))
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.credits_ects, "5")
        self.assertEqual(syllabus.total_hours, 150)
        self.assertEqual(syllabus.instructor_name, "Dr. Test")
        self.assertEqual(syllabus.course_description, "Updated description")

    def test_non_owner_cannot_reject_via_status_endpoint(self):
        teacher = self._create_user("teacher_reject_owner", "teacher")
        attacker = self._create_user("teacher_reject_attacker", "teacher")
        course = self._create_course(teacher, code="CS410")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_DEAN,
        )

        self.client.force_login(attacker)
        response = self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, Syllabus.Status.REJECTED]),
            {"comment": "bad"},
        )

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.REVIEW_DEAN)

    def test_invalid_status_endpoint_value_is_rejected(self):
        teacher = self._create_user("teacher_invalid_status", "teacher")
        course = self._create_course(teacher, code="CS411")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        self.client.force_login(teacher)
        response = self.client.post(
            reverse("syllabus_change_status", args=[syllabus.pk, "hacked"]),
            {"comment": "bad"},
        )

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)

    def test_syllabus_form_rejects_unsupported_file_extension(self):
        teacher = self._create_user("teacher_bad_extension_form", "teacher")
        course = self._create_course(teacher, code="CS412")
        uploaded = SimpleUploadedFile("notes.txt", b"not a syllabus")

        form = SyllabusForm(
            data={
                "course": course.pk,
                "semester": "Fall 2025",
                "academic_year": "2025-2026",
                "main_language": "ru",
            },
            files={"pdf_file": uploaded},
            user=teacher,
        )

        self.assertFalse(form.is_valid())
        self.assertIn("pdf_file", form.errors)

    def test_syllabus_upload_view_rejects_unsupported_file_extension(self):
        teacher = self._create_user("teacher_bad_extension_view", "teacher")
        course = self._create_course(teacher, code="CS413")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )
        bad_file = SimpleUploadedFile("malware.exe", b"fake")

        self.client.force_login(teacher)
        response = self.client.post(
            reverse("syllabus_upload_file", args=[syllabus.pk]),
            {"attachment": bad_file},
        )

        self.assertEqual(response.status_code, 302)
        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)
        self.assertEqual(syllabus.version_number, 1)
