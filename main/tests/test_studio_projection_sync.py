"""Catalog/ledger changes stay consistent without republishing group messages."""
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models.query import QuerySet
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import (
    Category, Florist, Product, SameDayFlower, StudioAdminNotification,
    StudioDelivery, StudioProduct,
)
from main.studio_delivery import soft_delete_product
from main.studio_publishing import save_dashboard_record, update_dashboard_record
from .test_telegram_same_day import image_file


GROUP = -5595039112


@override_settings(STUDIO_ADMIN_NOTIFICATIONS_ENABLED=True, TELEGRAM_SAME_DAY_GROUP_ID=str(GROUP), TELEGRAM_STUDIO_ADMIN_CHAT_ID="212832276")
class StudioProjectionSyncTests(TestCase):
    def setUp(self):
        self.media = tempfile.TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        category = Category.objects.create(name="گل", slug="projection-flowers", section="flowers")
        config = override_settings(MEDIA_ROOT=self.media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(category.pk))
        config.enable()
        self.addCleanup(config.disable)
        self.manager = get_user_model().objects.create_superuser("projection-manager", password="test-pass")
        self.florist = Florist.objects.create(name="سازنده", code="projection")
        self.record = StudioProduct(
            florist=self.florist, created_by=self.manager, factor_code="PROJ-100",
            product_type=StudioProduct.ProductType.BOX, production_type=StudioProduct.ProductionType.DAILY,
            price=2500000, image=image_file(), source=StudioProduct.Source.DASHBOARD,
        )
        # Mock every outbound operation, even though these paths only queue DB
        # jobs. Image variants use isolated test media and a mocked callback.
        for target in ("main.studio_transport.send_photo", "main.studio_transport.delete_message",
                       "main.studio_transport.edit_caption", "main.studio_publishing.create_responsive_image_variants"):
            mock = patch(target).start()
            self.addCleanup(patch.stopall)
            if target.endswith("send_photo"):
                self.send = mock
        save_dashboard_record(self.record)
        StudioAdminNotification.objects.all().delete()

    def notifications(self):
        return StudioAdminNotification.objects.filter(record=self.record)

    def edit_values(self, **overrides):
        values = {
            "florist": self.florist.pk, "factor_code": self.record.factor_code,
            "product_type": "box", "production_type": "DAILY", "price": "2500000", "notes": "",
        }
        values.update(overrides)
        return values

    def post_edit(self, **overrides):
        self.client.force_login(self.manager)
        self.client.get(reverse("studio_product_edit", args=[self.record.pk]))
        return self.client.post(reverse("studio_product_edit", args=[self.record.pk]),
                                self.edit_values(**overrides),
                                HTTP_X_CSRFTOKEN=self.client.cookies["csrftoken"].value)

    def mark_existing_group_identity(self):
        self.record.telegram_chat_id, self.record.telegram_message_id = GROUP, 812
        self.record.save(update_fields=["telegram_chat_id", "telegram_message_id"])
        self.record.deliveries.update(status=StudioDelivery.Status.SENT, message_id=812,
                                      telegram_created_at=timezone.now())

    def test_manager_price_and_photo_edit_updates_existing_public_row_without_publish(self):
        product_id = self.record.product_id
        old_image = self.record.image.name
        response = self.post_edit(price="3100000", image=image_file())
        self.assertEqual(response.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 3100000)
        self.assertEqual(self.record.product_id, product_id)
        self.assertEqual(self.record.product.price, self.record.price)
        self.assertEqual(self.record.product.cover_image.name, self.record.image.name)
        self.assertNotEqual(self.record.image.name, old_image)
        self.assertEqual(self.record.deliveries.filter(action=StudioDelivery.Action.PUBLISH).count(), 1)
        self.assertEqual(self.notifications().count(), 1)
        self.assertEqual(self.notifications().get().event, StudioAdminNotification.Event.PRICE)
        self.assertIn("3,100,000", self.notifications().get().caption)
        self.send.assert_not_called()

    def test_price_projection_and_outbox_roll_back_if_public_update_fails(self):
        self.record.price = 3100000
        original = QuerySet.update

        def fail_public_update(queryset, **kwargs):
            if queryset.model is Product:
                raise RuntimeError("simulated projection write failure")
            return original(queryset, **kwargs)

        with patch.object(QuerySet, "update", fail_public_update), self.assertRaises(RuntimeError):
            update_dashboard_record(self.record, changed_fields={"price"})
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 2500000)
        self.assertEqual(self.record.product.price, 2500000)
        self.assertFalse(self.notifications().exists())

    def test_edit_reloads_locked_status_and_cannot_overwrite_later_deletion(self):
        stale = StudioProduct.objects.get(pk=self.record.pk)
        soft_delete_product(self.record, actor=self.manager, reason="ثبت اشتباه")
        stale.price, stale.notes = 3100000, "ویرایش قدیمی"
        with self.assertRaises(PermissionDenied):
            update_dashboard_record(stale, changed_fields={"price", "notes"})
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, StudioProduct.Status.DELETED)
        self.assertEqual(self.record.price, 2500000)
        self.assertEqual(self.record.deletion_reason, "ثبت اشتباه")
        self.assertEqual(self.record.deleted_by, self.manager)

    def test_edit_copies_only_changed_fields_and_preserves_source(self):
        stale = StudioProduct.objects.get(pk=self.record.pk)
        self.record.price = 2900000
        update_dashboard_record(self.record, changed_fields={"price"})
        stale.notes = "اصلاح یادداشت"
        result = update_dashboard_record(stale, changed_fields={"notes"})
        self.assertEqual(result.price, 2900000)
        self.assertEqual(result.product.price, 2900000)
        self.assertEqual(result.source, StudioProduct.Source.DASHBOARD)
        self.assertEqual(result.notes, "اصلاح یادداشت")
        self.assertEqual(self.notifications().count(), 1)

    def test_published_factor_and_production_type_changes_are_form_errors(self):
        for values, field in (({"factor_code": "CHANGED-1"}, "factor_code"),
                              ({"production_type": "CUSTOM"}, "production_type")):
            with self.subTest(field=field):
                response = self.post_edit(**values)
                self.assertEqual(response.status_code, 200)
                self.assertIn(field, response.context["form"].errors)
        self.record.refresh_from_db()
        self.assertEqual(self.record.factor_code, "PROJ-100")
        self.assertEqual(self.record.production_type, StudioProduct.ProductionType.DAILY)
        self.assertEqual(self.record.deliveries.count(), 1)

    def test_existing_inactive_florist_does_not_block_price_edit(self):
        self.florist.is_active = False
        self.florist.save(update_fields=["is_active"])
        self.assertEqual(self.post_edit(price="3100000").status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.florist_id, self.florist.pk)
        self.assertEqual(self.record.product.price, 3100000)

    def test_clear_image_cannot_remove_the_stored_photos(self):
        original = self.record.image.name
        # The edit widget does not offer clearing the required product photo;
        # a forged checkbox is ignored, and the service rejects an empty edit.
        response = self.post_edit(**{"image-clear": "on"})
        self.assertEqual(response.status_code, 302)
        self.record.refresh_from_db()
        self.assertEqual(self.record.image.name, original)
        self.assertEqual(self.record.product.cover_image.name, original)
        self.record.image = ""
        with self.assertRaises(ValidationError):
            update_dashboard_record(self.record, changed_fields={"image"})
        self.record.refresh_from_db()
        self.assertEqual(self.record.image.name, original)
        self.assertEqual(self.record.product.cover_image.name, original)

    def test_existing_record_cannot_be_passed_to_creation_service(self):
        with self.assertRaises(ValidationError):
            save_dashboard_record(self.record)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(self.record.deliveries.count(), 1)

    def test_concrete_price_edit_syncs_ledger_and_emits_one_price_snapshot(self):
        public = Product.objects.get(pk=self.record.product_id)
        public.price = 3100000
        public.save(update_fields=["price"])
        public.save(update_fields=["price"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 3100000)
        self.assertEqual(self.notifications().count(), 1)
        self.assertEqual(self.notifications().get().event, StudioAdminNotification.Event.PRICE)
        self.assertEqual(self.record.source, StudioProduct.Source.DASHBOARD)

    def test_same_day_proxy_price_and_photo_edit_syncs_without_republication(self):
        public = SameDayFlower.objects.get(pk=self.record.product_id)
        public.price, public.cover_image = 3100000, image_file()
        public.save(update_fields=["price", "cover_image"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 3100000)
        self.assertEqual(self.record.image.name, public.cover_image.name)
        self.assertEqual(self.record.deliveries.count(), 1)
        self.assertEqual(self.notifications().count(), 1)
        self.send.assert_not_called()

    def test_proxy_status_and_price_change_queues_one_status_snapshot_and_existing_retirement(self):
        self.mark_existing_group_identity()
        public = SameDayFlower.objects.get(pk=self.record.product_id)
        public.status, public.price = Product.Status.SOLD, 3100000
        public.stock_status = Product.StockStatus.OUT_OF_STOCK
        with transaction.atomic():
            public.save(update_fields=["status", "price", "stock_status"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.status, StudioProduct.Status.SOLD)
        self.assertIsNotNone(self.record.sold_at)
        self.assertEqual(self.record.price, 3100000)
        notification = self.notifications().get()
        self.assertEqual(notification.event, StudioAdminNotification.Event.STATUS)
        self.assertIn("3,100,000", notification.caption)
        self.assertIn(self.record.get_status_display(), notification.caption)
        self.assertEqual(self.record.deliveries.filter(action=StudioDelivery.Action.PUBLISH).count(), 1)
        self.assertEqual(self.record.deliveries.filter(action=StudioDelivery.Action.RETIRE).count(), 1)

    def test_product_partial_save_ignores_dirty_unsaved_price_and_status(self):
        public = SameDayFlower.objects.get(pk=self.record.product_id)
        public.price, public.status, public.description = 3100000, Product.Status.SOLD, "توضیح"
        public.save(update_fields=["description"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 2500000)
        self.assertEqual(self.record.status, StudioProduct.Status.AVAILABLE)
        self.assertFalse(self.notifications().exists())
        self.assertEqual(self.record.deliveries.count(), 1)

    def test_ledger_partial_save_does_not_notify_unsaved_price_or_status(self):
        self.record.price, self.record.status, self.record.notes = 3100000, StudioProduct.Status.SOLD, "یادداشت"
        self.record.save(update_fields=["notes"])
        self.record.refresh_from_db()
        self.assertEqual(self.record.price, 2500000)
        self.assertEqual(self.record.status, StudioProduct.Status.AVAILABLE)
        self.assertFalse(self.notifications().exists())

    def test_catalog_edit_cannot_reopen_or_rewrite_deleted_ledger_audit(self):
        soft_delete_product(self.record, actor=self.manager, reason="حذف اشتباه ثبت")
        self.record.refresh_from_db()
        audit = (self.record.image.name, self.record.price, self.record.deleted_at,
                 self.record.deleted_by_id, self.record.deletion_reason)
        StudioAdminNotification.objects.all().delete()
        public = SameDayFlower.objects.get(pk=self.record.product_id)
        public.price, public.cover_image = 3100000, image_file()
        public.status = Product.Status.AVAILABLE
        public.publish_status = Product.PublishStatus.PUBLISHED
        public.stock_status = Product.StockStatus.IN_STOCK
        public.save()
        self.record.refresh_from_db()
        public.refresh_from_db()
        self.assertEqual(self.record.status, StudioProduct.Status.DELETED)
        self.assertEqual((self.record.image.name, self.record.price, self.record.deleted_at,
                          self.record.deleted_by_id, self.record.deletion_reason), audit)
        self.assertEqual(public.publish_status, Product.PublishStatus.DRAFT)
        self.assertEqual(public.status, Product.Status.WITHDRAWN)
        self.assertEqual(public.stock_status, Product.StockStatus.OUT_OF_STOCK)
        self.assertFalse(self.notifications().exists())
