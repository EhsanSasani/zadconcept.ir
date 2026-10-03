"""Deleted entries remain in the audit ledger, outside florist workspaces."""
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Florist, StudioProduct


@override_settings(TELEGRAM_STUDIO_ADMIN_CHAT_ID="")
class StudioPortalDeletionSafetyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.owner = User.objects.create_user(username="safety-owner")
        cls.peer_user = User.objects.create_user(username="safety-peer")
        cls.manager = User.objects.create_superuser(username="safety-manager", password="test-password")
        cls.florist = Florist.objects.create(name="فلوریست من", code="safety-owner", user=cls.owner)
        cls.peer = Florist.objects.create(name="همکار", code="safety-peer", user=cls.peer_user)
        cls.empty_peer = Florist.objects.create(name="همکار تازه", code="safety-empty")

    def setUp(self):
        self.client.force_login(self.owner)

    def record(self, florist=None, **kwargs):
        florist = florist or self.florist
        data = {
            "florist": florist, "created_by": florist.user,
            "factor_code": "SAFETY-" + uuid4().hex[:8], "image": "studio/safety.webp",
            "product_type": StudioProduct.ProductType.BOX,
            "production_type": StudioProduct.ProductionType.CUSTOM,
            "price": 1250000, "source": StudioProduct.Source.PORTAL,
            "submission_key": uuid4(),
        }
        data.update(kwargs)
        if data.get("status") == StudioProduct.Status.SOLD:
            data["sold_at"] = timezone.now()
        elif data.get("status") == StudioProduct.Status.WITHDRAWN:
            data["withdrawn_at"] = timezone.now()
        elif data.get("status") == StudioProduct.Status.DELETED:
            data.update(deleted_at=timezone.now(), deleted_by=self.manager,
                        deletion_reason="ثبت اشتباه محصول")
        return StudioProduct.objects.create(**data)

    def test_deleted_entries_are_removed_from_all_home_counts_and_recent_items(self):
        live = [self.record(status=status) for status in (
            StudioProduct.Status.AVAILABLE, StudioProduct.Status.SOLD,
            StudioProduct.Status.WITHDRAWN, StudioProduct.Status.CANCELLED)]
        delegated = self.record(self.peer, created_by=self.owner)
        deleted = self.record(status=StudioProduct.Status.DELETED)
        deleted_peer = self.record(self.peer, created_by=self.owner, status=StudioProduct.Status.DELETED)
        response = self.client.get(reverse("team_home"))
        self.assertEqual(response.context["summary"], {
            "total_count": 4, "today_count": 4, "available_count": 1, "sold_count": 1})
        self.assertCountEqual(response.context["recent_products"], [*live, delegated])
        self.assertNotContains(response, deleted.factor_code)
        self.assertNotContains(response, deleted_peer.factor_code)

    def test_products_filters_and_detail_cannot_expose_deleted_entries(self):
        live = self.record(factor_code="VISIBLE-FACTOR")
        deleted = self.record(factor_code="DELETED-FACTOR", status=StudioProduct.Status.DELETED)
        delegated_deleted = self.record(self.peer, created_by=self.owner, status=StudioProduct.Status.DELETED)
        for params in ({}, {"status": "DELETED"}):
            with self.subTest(params=params):
                response = self.client.get(reverse("team_products"), params)
                self.assertEqual(list(response.context["page_obj"]), [live])
                self.assertNotIn("DELETED", dict(response.context["status_choices"]))
                self.assertNotContains(response, deleted.factor_code)
        response = self.client.get(reverse("team_products"), {"q": "DELETED-FACTOR"})
        self.assertEqual(response.context["page_obj"].paginator.count, 0)
        for record in (deleted, delegated_deleted):
            with self.subTest(record=record.pk):
                self.assertEqual(self.client.get(reverse("team_product_detail", args=[record.pk])).status_code, 404)
        self.assertEqual(self.client.get(reverse("team_product_detail", args=[live.pk])).status_code, 200)

    def test_pagination_counts_only_visible_records(self):
        visible = [self.record() for _ in range(19)]
        for _ in range(20):
            self.record(status=StudioProduct.Status.DELETED)
        first = self.client.get(reverse("team_products"))
        second = self.client.get(reverse("team_products"), {"page": 2})
        self.assertEqual(first.context["page_obj"].paginator.count, 19)
        self.assertEqual(first.context["page_obj"].paginator.num_pages, 2)
        self.assertCountEqual([*first.context["page_obj"], *second.context["page_obj"]], visible)

    def test_colleague_card_and_gallery_exclude_deleted_work(self):
        live = self.record(self.peer, image="studio/visible-peer.webp")
        self.record(self.peer, status=StudioProduct.Status.DELETED, image="studio/deleted-peer.webp")
        cards = self.client.get(reverse("team_colleagues")).context["colleagues"]
        counts = {card["pk"]: card["product_count"] for card in cards}
        self.assertEqual(counts[self.peer.pk], 1)
        self.assertEqual(counts[self.empty_peer.pk], 0)
        response = self.client.get(reverse("team_colleague_profile", args=[self.peer.pk]))
        self.assertEqual(response.context["colleague"]["product_count"], 1)
        self.assertEqual(len(response.context["work_gallery"]), 1)
        self.assertEqual(response.context["work_gallery"][0]["image_url"], live.photo_url)
        self.assertNotContains(response, "deleted-peer.webp")
        self.assertNotContains(response, live.factor_code)

    def test_deleted_original_upload_retry_does_not_resurrect_or_claim_success(self):
        record = self.record(status=StudioProduct.Status.DELETED)
        payload = {"submission_key": str(record.submission_key), "florist": record.florist_id}
        response = self.client.post(reverse("team_product_add"), payload, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 409)
        self.assertFalse(response.json()["ok"])
        self.assertIn("submission_key", response.json()["errors"])
        self.assertNotIn("redirect_url", response.json())
        fallback = self.client.post(reverse("team_product_add"), payload)
        self.assertRedirects(fallback, reverse("team_products"))
        record.refresh_from_db()
        self.assertEqual(record.status, StudioProduct.Status.DELETED)
        self.assertEqual(StudioProduct.objects.count(), 1)

    def test_deleted_upload_retry_still_rejects_another_actor(self):
        record = self.record(status=StudioProduct.Status.DELETED)
        self.client.force_login(self.peer_user)
        response = self.client.post(reverse("team_product_add"), {
            "submission_key": str(record.submission_key)}, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertNotIn("record_id", response.json())

    def test_manager_history_and_forms_keep_distinct_csp_safe_actions(self):
        live = self.record()
        deleted = self.record(status=StudioProduct.Status.DELETED)
        self.client.force_login(self.manager)
        response = self.client.get(reverse("studio_products"))
        self.assertCountEqual(response.context["page"], [live, deleted])
        self.assertContains(response, deleted.deletion_reason)
        self.assertContains(response, 'action="%s" class="status-form"' % reverse("studio_product_status", args=[live.pk]))
        self.assertContains(response, 'action="%s" class="product-delete-form"' % reverse("studio_product_delete", args=[live.pk]))
        self.assertNotContains(response, "onsubmit=")
