"""The visual seed must be repeatable and must not remove ordinary records."""

from io import StringIO
from tempfile import TemporaryDirectory

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import Florist, StudioIngestionIssue, StudioProduct


class StudioDemoSeedTests(TestCase):
    def test_seed_is_repeatable_and_clear_is_scoped(self):
        with TemporaryDirectory() as media_dir, override_settings(DEBUG=True, MEDIA_ROOT=media_dir):
            real = Florist.objects.create(name="واقعی", code="real")
            call_command("seed_studio_demo", count=24, stdout=StringIO())
            self.assertEqual(StudioProduct.objects.count(), 24)
            self.assertEqual(StudioProduct.objects.filter(status="SOLD").count() > 0, True)
            self.assertTrue(all(record.photo_url for record in StudioProduct.objects.all()))
            call_command("seed_studio_demo", count=24, stdout=StringIO())
            self.assertEqual(StudioProduct.objects.count(), 24)
            call_command("seed_studio_demo", clear=True, stdout=StringIO())
            self.assertFalse(StudioProduct.objects.exists())
            self.assertFalse(StudioIngestionIssue.objects.exists())
            self.assertEqual(list(Florist.objects.values_list("code", flat=True)), [real.code])

    @override_settings(DEBUG=False)
    def test_rejects_production_mode(self):
        with self.assertRaises(CommandError):
            call_command("seed_studio_demo", count=12, stdout=StringIO())
        self.assertFalse(StudioProduct.objects.exists())

    def test_seeded_dashboard_pages_render(self):
        with TemporaryDirectory() as media_dir, override_settings(DEBUG=True, MEDIA_ROOT=media_dir):
            call_command("seed_studio_demo", count=24, stdout=StringIO())
            user = get_user_model().objects.create_superuser(username="demo-reviewer", password="pass")
            self.client.force_login(user)
            for route in ("studio_dashboard", "studio_products", "studio_florists",
                          "studio_analytics", "studio_settings", "studio_product_add"):
                with self.subTest(route=route):
                    self.assertEqual(self.client.get(reverse(route)).status_code, 200)
            florist = Florist.objects.get(code="demo-mz")
            self.assertEqual(self.client.get(reverse("studio_florist_profile", args=[florist.pk])).status_code, 200)
            self.assertGreater(self.client.get(reverse("studio_dashboard")).context["stats"]["produced"], 0)
