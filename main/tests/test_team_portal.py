from io import BytesIO, StringIO
from tempfile import TemporaryDirectory
from unittest.mock import patch
from uuid import uuid4

from PIL import Image
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from main.models import Category, Florist, StudioDelivery, StudioProduct


def photo():
    data = BytesIO()
    Image.new("RGB", (960, 1200), "#c09890").save(data, "JPEG")
    return SimpleUploadedFile("iphone.jpg", data.getvalue(), content_type="image/jpeg")


class TeamPortalTests(TestCase):
    password = "A long private test 4728!"

    def setUp(self):
        cache.clear()
        media = TemporaryDirectory()
        self.addCleanup(media.cleanup)
        self.category = Category.objects.create(name="روزانه", slug="team-daily", section=Category.Section.FLOWERS)
        config = override_settings(MEDIA_ROOT=media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(self.category.pk),
                                   TELEGRAM_SAME_DAY_GROUP_ID="-100899", TELEGRAM_BOT_TOKEN="",
                                   TELEGRAM_SAME_DAY_RELAY_URL="")
        config.enable()
        self.addCleanup(config.disable)
        User = get_user_model()
        self.owner = User.objects.create_user(username="portal-owner", password=self.password)
        self.peer_user = User.objects.create_user(username="portal-peer", password=self.password)
        self.florist = Florist.objects.create(name="لیلا", code="leila", user=self.owner)
        self.peer = Florist.objects.create(name="مینا", code="mina", user=self.peer_user, notes="PRIVATE-FLORIST-NOTE")
        self.manager = User.objects.create_user(username="portal-manager", password=self.password)
        self.manager.user_permissions.add(*Permission.objects.filter(content_type__app_label="main", codename__in=[
            "view_studioproduct", "manage_studio_accounts"]))

    def record(self, florist=None, **kwargs):
        florist = florist or self.florist
        data = {"factor_code": "F-" + uuid4().hex[:8], "florist": florist, "created_by": florist.user,
                "image": "studio/products/example.webp", "product_type": "box", "production_type": "CUSTOM",
                "price": 981234567, "source": "PORTAL", "submission_key": uuid4()}
        data.update(kwargs)
        return StudioProduct.objects.create(**data)

    def payload(self, **kwargs):
        data = {"image": photo(), "florist": self.florist.pk,
                "factor_code": "NEW-۱۲۳", "product_type": "box", "production_type": "DAILY",
                "price": "۱٬۲۵۰٬۰۰۰", "submission_key": str(uuid4()), "notes": "یادداشت خصوصی"}
        data.update(kwargs)
        return data

    def test_anonymous_and_expired_json_session_use_independent_login(self):
        response = self.client.get(reverse("team_home"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response.url.startswith(reverse("studio_login")))
        response = self.client.post(reverse("team_product_add"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["login_url"], reverse("studio_login"))
        self.assertIn("no-store", response["Cache-Control"])

    def test_login_rejects_external_redirect_and_uses_role_destination(self):
        response = self.client.post(reverse("studio_login"), {"username": self.owner.username,
            "password": self.password, "next": "https://hostile.example/login", "remember": "on"})
        self.assertRedirects(response, reverse("team_home"), fetch_redirect_response=False)
        self.assertEqual(self.client.session.get_expiry_age(), 30 * 24 * 60 * 60)
        self.assertIn("no-store", response["Cache-Control"])
        self.client.logout()
        response = self.client.post(reverse("studio_login"), {"username": self.manager.username, "password": self.password})
        self.assertRedirects(response, reverse("studio_dashboard"), fetch_redirect_response=False)
        self.assertFalse(self.manager.is_staff)
        self.assertEqual(self.client.get(reverse("studio_dashboard")).status_code, 200)

    def test_unlinked_and_inactive_florists_cannot_enter_portal(self):
        self.florist.is_active = False
        self.florist.save(update_fields=["is_active"])
        response = self.client.post(reverse("studio_login"), {"username": self.owner.username, "password": self.password})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("team_home")).status_code, 403)
        self.client.force_login(self.manager)
        self.assertEqual(self.client.get(reverse("team_home")).status_code, 403)

    def test_login_throttle_does_not_authenticate_after_limit(self):
        from main.team_views import _login_limit_key
        from django.test import RequestFactory
        request = RequestFactory().post("/studio/login/", {"username": self.owner.username}, REMOTE_ADDR="127.0.0.1")
        cache.set(_login_limit_key(request), 10, 900)
        with patch("django.contrib.auth.forms.authenticate") as authenticate:
            response = self.client.post(reverse("studio_login"), {"username": self.owner.username, "password": self.password})
        self.assertEqual(response.status_code, 200)
        authenticate.assert_not_called()
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_own_records_are_isolated_and_peer_gallery_is_whitelisted(self):
        own = self.record(factor_code="OWN-INVOICE")
        other = self.record(self.peer, factor_code="PRIVATE-PEER-INVOICE", notes="PRIVATE-PRODUCT-NOTE")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("team_products"))
        self.assertEqual(list(response.context["page_obj"]), [own])
        self.assertEqual(self.client.get(reverse("team_product_detail", args=[other.pk])).status_code, 404)
        self.assertEqual(self.client.post(reverse("studio_product_status", args=[other.pk]), {"status": "SOLD"}).status_code, 403)
        response = self.client.get(reverse("team_colleague_profile", args=[self.peer.pk]))
        self.assertEqual(set(response.context["colleague"]), {"pk", "name", "photo_url", "product_count"})
        self.assertEqual(set(response.context["work_gallery"][0]), {"image_url", "product_type", "production_type", "produced_at"})
        for private in ("PRIVATE-PEER-INVOICE", "PRIVATE-PRODUCT-NOTE", "PRIVATE-FLORIST-NOTE", "981234567", self.peer_user.username):
            self.assertNotContains(response, private)

    def test_daily_upload_uses_selected_florist_preserves_actor_and_is_idempotent(self):
        self.client.force_login(self.owner)
        payload = self.payload(florist=self.peer.pk, created_by=self.peer_user.pk, status="SOLD")
        key = payload["submission_key"]
        with patch("main.studio_transport.send_photo") as send:
            response = self.client.post(reverse("team_product_add"), payload, HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 201, response.content)
        result = response.json()
        record = StudioProduct.objects.get(pk=result["record_id"])
        self.assertEqual(record.florist, self.peer)
        self.assertEqual(record.created_by, self.owner)
        self.assertEqual(record.factor_code, "NEW-123")
        self.assertEqual(record.price, 1250000)
        self.assertEqual(record.status, "AVAILABLE")
        self.assertTrue(record.product.is_published)
        self.assertTrue(record.image.name.endswith(".webp"))
        self.assertEqual(record.deliveries.count(), 1)
        send.assert_not_called()
        replay = self.client.post(reverse("team_product_add"), {"submission_key": key}, HTTP_ACCEPT="application/json")
        self.assertEqual(replay.status_code, 200)
        self.assertEqual(replay.json()["record_id"], record.pk)
        self.assertEqual(StudioProduct.objects.count(), 1)
        self.assertEqual(StudioDelivery.objects.count(), 1)
        changed = self.client.post(reverse("team_product_add"), {
            "submission_key": key, "florist": self.florist.pk}, HTTP_ACCEPT="application/json")
        self.assertEqual(changed.status_code, 400)
        record.refresh_from_db()
        self.assertEqual(record.florist, self.peer)
        self.client.force_login(self.peer_user)
        collision = self.client.post(reverse("team_product_add"), {"submission_key": key}, HTTP_ACCEPT="application/json")
        self.assertEqual(collision.status_code, 400)
        self.assertNotIn("record_id", collision.json())

    def test_florist_picker_starts_empty_and_lists_only_active_florists(self):
        inactive = Florist.objects.create(name="غیرفعال", code="inactive", is_active=False)
        unlinked = Florist.objects.create(name="همکار بدون حساب", code="no-login")
        self.client.force_login(self.owner)
        response = self.client.get(reverse("team_product_add"))
        field = response.context["form"]["florist"]
        self.assertIsNone(field.value())
        self.assertTrue(field.field.required)
        self.assertEqual(field.field.empty_label, "فلوریست را انتخاب کنید")
        self.assertCountEqual(field.field.queryset, [self.florist, self.peer, unlinked])
        self.assertNotIn(inactive, field.field.queryset)
        self.assertContains(response, '<option value="" selected>فلوریست را انتخاب کنید</option>', html=True)

    def test_missing_inactive_or_unknown_florist_cannot_create_product(self):
        inactive = Florist.objects.create(name="غیرفعال", code="inactive", is_active=False)
        self.client.force_login(self.owner)
        for choice in (None, "", inactive.pk, "999999", "not-an-id"):
            with self.subTest(choice=choice):
                payload = self.payload(production_type="CUSTOM", florist=choice)
                if choice is None:
                    payload.pop("florist")
                response = self.client.post(reverse("team_product_add"), payload, HTTP_ACCEPT="application/json")
                self.assertEqual(response.status_code, 400)
                self.assertIn("florist", response.json()["errors"])
                self.assertFalse(StudioProduct.objects.exists())
                self.assertFalse(StudioDelivery.objects.exists())

    def test_registering_for_colleague_keeps_receipt_visible_and_stats_attributed(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("team_product_add"), self.payload(
            production_type="CUSTOM", florist=self.peer.pk), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 201)
        record = StudioProduct.objects.get()
        receipt = self.client.get(response.json()["redirect_url"])
        self.assertEqual(receipt.status_code, 200)
        self.assertContains(receipt, '<dt>فلوریست</dt><dd>مینا</dd>', html=True)
        self.assertEqual(list(self.client.get(reverse("team_products")).context["page_obj"]), [record])
        home = self.client.get(reverse("team_home"))
        self.assertEqual(home.context["summary"]["total_count"], 0)
        self.assertEqual(list(home.context["recent_products"]), [record])
        self.client.force_login(self.peer_user)
        self.assertEqual(self.client.get(reverse("team_product_detail", args=[record.pk])).status_code, 200)
        self.assertEqual(self.client.get(reverse("team_home")).context["summary"]["total_count"], 1)
        outsider = get_user_model().objects.create_user("other-reader")
        Florist.objects.create(name="نفر سوم", code="third", user=outsider)
        self.client.force_login(outsider)
        self.assertEqual(self.client.get(reverse("team_product_detail", args=[record.pk])).status_code, 404)
        self.assertFalse(self.client.get(reverse("team_products")).context["page_obj"])

    def test_custom_multipart_fallback_stays_private(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("team_product_add"), self.payload(production_type="CUSTOM"))
        self.assertEqual(response.status_code, 302)
        record = StudioProduct.objects.get()
        self.assertIsNone(record.product_id)
        self.assertFalse(record.deliveries.exists())
        self.assertTrue(response.url.startswith(reverse("team_product_detail", args=[record.pk])))

    def test_invalid_upload_and_csrf_are_rejected_without_writes(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("team_product_add"), self.payload(
            image=SimpleUploadedFile("fake.jpg", b"not image content"), price="-۵"), HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("image", response.json()["errors"])
        self.assertIn("price", response.json()["errors"])
        self.assertFalse(StudioProduct.objects.exists())
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(self.owner)
        self.assertEqual(strict.post(reverse("team_product_add"), self.payload()).status_code, 403)

    def test_profile_photo_and_password_changes_remain_personal(self):
        self.client.force_login(self.owner)
        response = self.client.post(reverse("team_profile"), {"name": "لیلا تازه", "photo": photo(), "code": "hijack", "user": self.peer_user.pk})
        self.assertEqual(response.status_code, 302)
        self.florist.refresh_from_db()
        self.assertEqual(self.florist.name, "لیلا تازه")
        self.assertEqual(self.florist.code, "leila")
        self.assertEqual(self.florist.user, self.owner)
        with Image.open(self.florist.photo.path) as image:
            self.assertLessEqual(max(image.size), 800)
        response = self.client.post(reverse("team_profile"), {"action": "password", "old_password": self.password,
            "new_password1": "A new private password 953!", "new_password2": "A new private password 953!"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.client.get(reverse("team_home")).status_code, 200)
        self.owner.refresh_from_db()
        self.assertTrue(self.owner.check_password("A new private password 953!"))

    def test_account_manager_creates_only_unprivileged_user(self):
        unlinked = Florist.objects.create(name="سارا", code="sara")
        self.client.force_login(self.owner)
        self.assertEqual(self.client.get(reverse("studio_accounts")).status_code, 403)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("studio_accounts"), {"action": "create", "florist": unlinked.pk,
            "username": "sara-team", "password1": self.password, "password2": self.password,
            "is_staff": "on", "is_superuser": "on"})
        self.assertRedirects(response, reverse("studio_accounts"), fetch_redirect_response=False)
        unlinked.refresh_from_db()
        self.assertFalse(unlinked.user.is_staff)
        self.assertFalse(unlinked.user.is_superuser)
        self.assertFalse(unlinked.user.get_all_permissions())

    def test_account_reset_cannot_take_over_inactive_privileged_user(self):
        self.peer_user.user_permissions.add(Permission.objects.get(content_type__app_label="main", codename="view_studioproduct"))
        self.peer_user.is_active = False
        self.peer_user.save(update_fields=["is_active"])
        self.client.force_login(self.manager)
        for action in ("password", "enable", "disable"):
            response = self.client.post(reverse("studio_accounts"), {"action": action, "florist_id": self.peer.pk,
                "new_password1": self.password, "new_password2": self.password})
            self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.post(reverse("studio_accounts"), {"action": "disable", "florist_id": "bad"}).status_code, 404)

    def test_account_disable_revokes_existing_portal_session_and_logout_is_post(self):
        florist_client = Client()
        florist_client.force_login(self.owner)
        self.client.force_login(self.manager)
        response = self.client.post(reverse("studio_accounts"), {"action": "disable", "florist_id": self.florist.pk})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(florist_client.get(reverse("team_home")).status_code, 302)
        self.assertEqual(self.client.get(reverse("studio_logout")).status_code, 405)
        self.assertEqual(self.client.post(reverse("studio_logout")).status_code, 302)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_account_command_prompts_password_and_preserves_admin_separation(self):
        stdout = StringIO()
        with patch("main.management.commands.studio_account.getpass", side_effect=[self.password, self.password]):
            call_command("studio_account", "new-manager", manager=True, stdout=stdout)
        user = get_user_model().objects.get(username="new-manager")
        self.assertFalse(user.is_staff)
        self.assertTrue(user.has_perm("main.manage_studio_accounts"))
        self.assertTrue(user.has_perm("main.change_studioingestionissue"))
        self.assertNotIn(self.password, stdout.getvalue())
        with self.assertRaises(CommandError):
            call_command("studio_account", self.owner.username, florist="mina", stdout=stdout)
