from pathlib import Path

from django.contrib.auth import get_user_model
from django.conf import settings
from django.test import TestCase
from django.urls import reverse


User = get_user_model()
MOJIBAKE_MARKERS = ("РџР", "РЎР", "Р“Р", "СЃР", "С‚Р")


class DiagnosticsAccessTests(TestCase):
    def test_healthz_is_public(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual(response.status_code, 200)

    def test_diagnostics_requires_privileged_user(self):
        response = self.client.get(reverse("diagnostics"))
        self.assertEqual(response.status_code, 403)

    def test_admin_can_access_diagnostics(self):
        admin_user = User.objects.create_user(
            username="diag_admin",
            password="pass1234",
            role="admin",
        )
        self.client.force_login(admin_user)

        response = self.client.get(reverse("diagnostics"))
        self.assertNotEqual(response.status_code, 403)


class DashboardEncodingTests(TestCase):
    def test_dean_dashboard_contains_normal_russian_text(self):
        dean_user = User.objects.create_user(
            username="dean_utf8",
            password="pass1234",
            role="dean",
        )
        self.client.force_login(dean_user)

        response = self.client.get(reverse("dashboard"))
        content = response.content.decode("utf-8", errors="strict")

        self.assertEqual(response.status_code, 200)
        self.assertIn("Панель управления", content)
        self.assertIn("Просматривайте силлабусы на согласовании", content)
        for marker in MOJIBAKE_MARKERS:
            self.assertNotIn(marker, content)

    def test_html_templates_do_not_contain_mojibake_markers(self):
        templates_dir = Path(settings.BASE_DIR) / "templates"
        html_files = sorted(templates_dir.rglob("*.html"))
        self.assertGreater(len(html_files), 0, "No HTML templates found in templates/")

        for html_file in html_files:
            content = html_file.read_text(encoding="utf-8")
            for marker in MOJIBAKE_MARKERS:
                self.assertNotIn(marker, content, f"Found '{marker}' in {html_file}")
