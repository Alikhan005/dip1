from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.test import TestCase

from catalog.models import Course
from syllabi.models import Syllabus
from workflow.models import SyllabusAuditLog, SyllabusStatusLog
from workflow.services import change_status, change_status_system

User = get_user_model()


class WorkflowRoleTests(TestCase):
    def _create_user(self, username: str, role: str) -> User:
        return User.objects.create_user(username=username, password="pass1234", role=role)

    def _create_course(self, owner: User, code: str = "CS101") -> Course:
        return Course.objects.create(
            owner=owner,
            code=code,
            available_languages="ru",
        )

    def test_umu_can_approve_submitted_umu(self):
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

        change_status(umu, syllabus, Syllabus.Status.APPROVED_UMU, "ok")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.APPROVED_UMU)
        self.assertTrue(
            SyllabusStatusLog.objects.filter(
                syllabus=syllabus,
                to_status=Syllabus.Status.APPROVED_UMU,
                changed_by=umu,
            ).exists()
        )

    def test_umu_cannot_approve_own_syllabus(self):
        umu = self._create_user("umu_author", "umu")
        course = self._create_course(umu)
        syllabus = Syllabus.objects.create(
            course=course,
            creator=umu,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.SUBMITTED_UMU,
        )

        with self.assertRaises(PermissionDenied):
            change_status(umu, syllabus, Syllabus.Status.APPROVED_UMU, "ok")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.SUBMITTED_UMU)

    def test_dean_cannot_approve_own_syllabus(self):
        dean = self._create_user("dean_author", "dean")
        course = self._create_course(dean, code="CS202")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=dean,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.SUBMITTED_DEAN,
        )

        with self.assertRaises(PermissionDenied):
            change_status(dean, syllabus, Syllabus.Status.APPROVED_DEAN, "ok")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.SUBMITTED_DEAN)

    def test_wrong_status_rejected(self):
        teacher = self._create_user("teacher_author", "teacher")
        dean = self._create_user("dean_user", "dean")
        course = self._create_course(teacher, code="CS303")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        with self.assertRaises(PermissionDenied):
            change_status(dean, syllabus, Syllabus.Status.APPROVED_DEAN, "ok")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)

    def test_non_reviewer_cannot_reject_syllabus(self):
        teacher = self._create_user("teacher_owner", "teacher")
        attacker = self._create_user("teacher_attacker", "teacher")
        course = self._create_course(teacher, code="CS304")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_DEAN,
        )

        with self.assertRaises(PermissionDenied):
            change_status(attacker, syllabus, Syllabus.Status.REJECTED, "bad")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.REVIEW_DEAN)

    def test_invalid_status_value_rejected(self):
        teacher = self._create_user("teacher_invalid_status", "teacher")
        course = self._create_course(teacher, code="CS305")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.DRAFT,
        )

        with self.assertRaises(ValueError):
            change_status(teacher, syllabus, "hacked_status", "bad")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.DRAFT)

    def test_system_transition_creates_logs_and_status(self):
        teacher = self._create_user("teacher_system", "teacher")
        course = self._create_course(teacher, code="CS404")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.AI_CHECK,
        )

        change_status_system(
            syllabus,
            Syllabus.Status.REVIEW_DEAN,
            comment="AI check approved.",
            ai_feedback="<p>OK</p>",
        )

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.REVIEW_DEAN)
        self.assertEqual(syllabus.ai_feedback, "<p>OK</p>")

        status_log = SyllabusStatusLog.objects.filter(syllabus=syllabus).latest("changed_at")
        self.assertEqual(status_log.from_status, Syllabus.Status.AI_CHECK)
        self.assertEqual(status_log.to_status, Syllabus.Status.REVIEW_DEAN)
        self.assertIsNone(status_log.changed_by)

        audit = SyllabusAuditLog.objects.filter(
            syllabus=syllabus, action=SyllabusAuditLog.Action.STATUS_CHANGED
        ).latest("created_at")
        self.assertIsNone(audit.actor)
        self.assertEqual(audit.metadata.get("source"), "system")

    def test_system_transition_can_move_to_correction(self):
        teacher = self._create_user("teacher_system_correction", "teacher")
        course = self._create_course(teacher, code="CS405")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.AI_CHECK,
        )

        change_status_system(
            syllabus,
            Syllabus.Status.CORRECTION,
            comment="AI check found issues.",
            ai_feedback="<p>Need improvements</p>",
        )

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.CORRECTION)
        self.assertEqual(syllabus.ai_feedback, "<p>Need improvements</p>")

    def test_manual_correction_keeps_existing_ai_feedback(self):
        teacher = self._create_user("teacher_manual_feedback", "teacher")
        umu = self._create_user("umu_manual_feedback", "umu")
        course = self._create_course(teacher, code="CS406")
        syllabus = Syllabus.objects.create(
            course=course,
            creator=teacher,
            semester="Fall 2025",
            academic_year="2025-2026",
            status=Syllabus.Status.REVIEW_UMU,
            ai_feedback="<p>AI baseline feedback</p>",
        )

        change_status(umu, syllabus, Syllabus.Status.CORRECTION, "Исправьте литературу.")

        syllabus.refresh_from_db()
        self.assertEqual(syllabus.status, Syllabus.Status.CORRECTION)
        self.assertEqual(syllabus.ai_feedback, "<p>AI baseline feedback</p>")
