"""Integration boundaries between independent manager UI and the portal outbox."""
import tempfile
import uuid
from io import BytesIO

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import Category, Florist, Product, StudioDelivery, StudioProduct, TelegramSameDayPost
from main.studio_publishing import create_portal_record
from main.studio_delivery import reconcile_delivery


@override_settings(TELEGRAM_SAME_DAY_GROUP_ID="-100700")
class StudioTeamManagementTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        category = Category.objects.create(name="گل", slug="team-management", section="flowers")
        config = override_settings(MEDIA_ROOT=media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(category.pk))
        config.enable()
        self.addCleanup(config.disable)
        self.manager = get_user_model().objects.create_user(username="independent-manager")
        self.manager.user_permissions.add(*Permission.objects.filter(
            content_type__app_label="main", codename__in=("view_studioproduct", "change_studioproduct")))
        self.user = get_user_model().objects.create_user(username="independent-florist")
        florist = Florist.objects.create(name="همکار", code="mg", user=self.user)
        content = BytesIO()
        Image.new("RGB", (60, 80), "#60846b").save(content, "JPEG")
        self.record, _ = create_portal_record(user=self.user, florist=florist,
            image=SimpleUploadedFile("flower.jpg", content.getvalue(), content_type="image/jpeg"),
            factor_code="MG-01", product_type="box", production_type="DAILY", price=2500000,
            submission_key=uuid.uuid4())
        self.delivery = self.record.deliveries.get(action="PUBLISH")

    def test_independent_manager_login_and_readonly_boundaries(self):
        response = self.client.get(reverse("studio_dashboard"))
        self.assertTrue(response.url.startswith(reverse("studio_login")))
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse("studio_deliveries")).status_code, 403)
        self.client.force_login(self.manager)
        self.assertFalse(self.manager.is_staff)
        for route in ("studio_dashboard", "studio_settings", "studio_deliveries"):
            response = self.client.get(reverse(route))
            self.assertEqual(response.status_code, 200)
            self.assertIn("no-store", response.headers["Cache-Control"])
        viewer = get_user_model().objects.create_user(username="readonly-manager")
        viewer.user_permissions.add(Permission.objects.get(codename="view_studioproduct"))
        self.client.force_login(viewer)
        response = self.client.post(reverse("studio_deliveries"), {
            "delivery_id": self.delivery.pk, "action": "retry"})
        self.assertEqual(response.status_code, 403)

    def test_uncertain_send_requires_verified_message_and_never_blind_retry(self):
        self.delivery.status = "UNCERTAIN"
        self.delivery.save()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("studio_deliveries"), {
            "delivery_id": self.delivery.pk, "action": "retry"})
        self.assertEqual(response.status_code, 302)
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "UNCERTAIN")
        self.client.post(reverse("studio_deliveries"), {
            "delivery_id": self.delivery.pk, "action": "reconcile", "message_id": "901"})
        self.assertFalse(TelegramSameDayPost.objects.exists())
        self.client.post(reverse("studio_deliveries"), {
            "delivery_id": self.delivery.pk, "action": "reconcile", "message_id": "901", "verified": "yes"})
        self.delivery.refresh_from_db()
        self.assertEqual(self.delivery.status, "SENT")
        self.assertEqual(TelegramSameDayPost.objects.get().product_id, self.record.product_id)

    def _mark_sent(self):
        self.delivery.status = "UNCERTAIN"
        self.delivery.save()
        reconcile_delivery(self.delivery.pk, 901)
        self.record.refresh_from_db()

    def test_manager_terminal_status_updates_public_catalog_and_queues_retirement(self):
        self._mark_sent()
        self.client.force_login(self.manager)
        response = self.client.post(reverse("studio_product_status", args=[self.record.pk]), {"status": "SOLD"})
        self.assertEqual(response.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "SOLD")
        self.assertFalse(Product.objects.published().for_same_day().filter(pk=self.record.product_id).exists())
        self.assertTrue(self.record.deliveries.filter(action="RETIRE").exists())

    def test_admin_terminal_change_and_deletion_retain_ledger_and_queue(self):
        self._mark_sent()
        product = self.record.product
        product.status = Product.Status.WITHDRAWN
        product.save()
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, "WITHDRAWN")
        self.assertTrue(self.record.deliveries.filter(action="RETIRE").exists())
        image_name = self.record.image.name
        product.delete()
        self.record.refresh_from_db()
        self.assertIsNone(self.record.product_id)
        self.assertEqual(self.record.image.name, image_name)
        self.assertEqual(StudioProduct.objects.count(), 1)
