from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from catalog.models import Course, Topic, TopicLiterature, TopicQuestion


User = get_user_model()


class CatalogViewTests(TestCase):
    def _create_user(self, username: str, role: str = "teacher"):
        return User.objects.create_user(username=username, password="pass1234", role=role)

    def _course_payload(self, **overrides):
        payload = {
            "code": "CS101",
            "languages": ["ru", "en"],
            "title_ru": "Тестовый курс",
            "title_en": "Test course",
            "description_ru": "Описание курса",
            "description_en": "Course description",
            "is_shared": "on",
        }
        payload.update(overrides)
        return payload

    def _topic_payload(self, **overrides):
        payload = {
            "order_index": "1",
            "title_ru": "Тема 1",
            "title_en": "Topic 1",
            "default_hours": "2",
            "week_type": "lecture",
            "is_active": "on",
            "lit-TOTAL_FORMS": "1",
            "lit-INITIAL_FORMS": "0",
            "lit-MIN_NUM_FORMS": "0",
            "lit-MAX_NUM_FORMS": "1000",
            "lit-0-title": "Основной учебник",
            "lit-0-author": "Автор",
            "lit-0-year": "2024",
            "lit-0-lit_type": "main",
            "q-TOTAL_FORMS": "1",
            "q-INITIAL_FORMS": "0",
            "q-MIN_NUM_FORMS": "0",
            "q-MAX_NUM_FORMS": "1000",
            "q-0-question_ru": "Что нужно изучить?",
            "q-0-question_en": "What should be studied?",
        }
        payload.update(overrides)
        return payload

    def test_course_create_saves_selected_languages(self):
        teacher = self._create_user("catalog_teacher_create")
        self.client.force_login(teacher)

        response = self.client.post(reverse("course_create"), self._course_payload())

        course = Course.objects.get(code="CS101")
        self.assertRedirects(response, reverse("course_detail", args=[course.pk]))
        self.assertEqual(course.owner, teacher)
        self.assertEqual(course.get_available_languages_list(), ["ru", "en"])
        self.assertTrue(course.is_shared)

    def test_private_course_detail_denies_other_teacher(self):
        owner = self._create_user("catalog_teacher_owner")
        viewer = self._create_user("catalog_teacher_viewer")
        course = Course.objects.create(
            owner=owner,
            code="CS102",
            title_ru="Закрытый курс",
            available_languages="ru",
            is_shared=False,
        )

        self.client.force_login(viewer)
        response = self.client.get(reverse("course_detail", args=[course.pk]))

        self.assertEqual(response.status_code, 403)

    def test_topic_create_saves_formsets(self):
        teacher = self._create_user("catalog_teacher_topic")
        course = Course.objects.create(
            owner=teacher,
            code="CS103",
            title_ru="Курс с темами",
            available_languages="ru,en",
        )
        self.client.force_login(teacher)

        response = self.client.post(reverse("topic_create", args=[course.pk]), self._topic_payload())

        topic = Topic.objects.get(course=course, order_index=1)
        self.assertRedirects(response, reverse("course_detail", args=[course.pk]))
        self.assertEqual(topic.title_ru, "Тема 1")
        self.assertEqual(TopicLiterature.objects.filter(topic=topic).count(), 1)
        self.assertEqual(TopicQuestion.objects.filter(topic=topic).count(), 1)

    def test_shared_course_can_be_forked_with_nested_content(self):
        owner = self._create_user("catalog_teacher_source")
        fork_user = self._create_user("catalog_teacher_fork")
        source = Course.objects.create(
            owner=owner,
            code="CS104",
            title_ru="Общий курс",
            available_languages="ru,en",
            is_shared=True,
        )
        topic = Topic.objects.create(
            course=source,
            order_index=1,
            title_ru="Тема для копирования",
            default_hours=2,
        )
        TopicLiterature.objects.create(
            topic=topic,
            title="Книга для копирования",
            author="Автор",
            year="2024",
            lit_type="main",
        )
        TopicQuestion.objects.create(
            topic=topic,
            question_ru="Контрольный вопрос",
            question_en="Control question",
        )

        self.client.force_login(fork_user)
        response = self.client.post(reverse("course_fork", args=[source.pk]))

        forked = Course.objects.get(owner=fork_user, code="CS104_copy")
        self.assertRedirects(response, reverse("course_detail", args=[forked.pk]))
        self.assertFalse(forked.is_shared)
        self.assertEqual(forked.topics.count(), 1)
        self.assertEqual(forked.topics.first().literature.count(), 1)
        self.assertEqual(forked.topics.first().questions.count(), 1)
