from decimal import Decimal
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ..admin import ProductAdminForm
from ..models import (
    Category,
    Flower,
    Product,
    SameDayFlower,
    Tag,
    UNIQUE_TAG_SLUG,
)


class ConcreteProductAdminForm(ProductAdminForm):
    class Meta(ProductAdminForm.Meta):
        model = Product
        fields = "__all__"


class ProductUniqueAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="باکس ادمین",
            slug="admin-box",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.unique_tag = Tag.objects.create(
            name="یونیک",
            slug=UNIQUE_TAG_SLUG,
            is_occasion=True,
            is_active=True,
        )
        cls.birthday_tag = Tag.objects.create(
            name="تولد",
            slug="birthday-admin",
            is_occasion=True,
            is_active=True,
        )

    def setUp(self):
        self.product = Product.objects.create(
            name="باکس قابل مدیریت",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def test_new_product_is_not_unique_by_default(self):
        form = ConcreteProductAdminForm(instance=self.product)

        self.assertFalse(form.initial["is_unique"])

    def test_checkbox_creates_the_system_unique_tag_on_first_use(self):
        Tag.objects.filter(slug=UNIQUE_TAG_SLUG).delete()
        form = ConcreteProductAdminForm(
            data={
                "name": self.product.name,
                "slug": self.product.slug,
                "wedding_type": "",
                "wedding_sort_order": "0",
                "description": "",
                "pricing_type": Product.PricingType.INQUIRY,
                "price": "",
                "price_usd": "",
                "category": str(self.category.pk),
                "is_active": "on",
                "publish_status": Product.PublishStatus.PUBLISHED,
                "stock_status": Product.StockStatus.IN_STOCK,
                "sort_order": "0",
                "is_unique": "on",
            },
            instance=self.product,
        )

        self.assertTrue(form.is_valid(), form.errors)
        form.save()

        unique_tag = Tag.objects.get(slug=UNIQUE_TAG_SLUG)
        self.assertEqual(unique_tag.name, "یونیک")
        self.assertTrue(unique_tag.is_active)
        self.assertFalse(unique_tag.is_occasion)
        self.assertTrue(self.product.tags.filter(pk=unique_tag.pk).exists())

    def test_toman_price_input_groups_digits_and_accepts_slashes(self):
        form = ConcreteProductAdminForm(instance=self.product)
        price_input = form.fields["price"].widget

        self.assertEqual(price_input.format_value(Decimal("1250000")), "1/250/000")
        self.assertEqual(
            price_input.value_from_datadict({"price": "۱/۲۵۰/۰۰۰"}, {}, "price"),
            "1250000",
        )

        form = ConcreteProductAdminForm(
            data={
                "name": self.product.name,
                "slug": self.product.slug,
                "wedding_type": "",
                "wedding_sort_order": "0",
                "description": "",
                "pricing_type": Product.PricingType.FIXED,
                "price": "1/250/000",
                "price_usd": "",
                "category": str(self.category.pk),
                "is_active": "on",
                "publish_status": Product.PublishStatus.PUBLISHED,
                "stock_status": Product.StockStatus.IN_STOCK,
                "sort_order": "0",
            },
            instance=self.product,
        )

        self.assertTrue(form.is_valid(), form.errors)
        saved_product = form.save()
        self.assertEqual(saved_product.price, Decimal("1250000"))

    def test_dedicated_checkbox_owns_unique_membership(self):
        self.product.tags.add(self.unique_tag)
        form = ConcreteProductAdminForm(instance=self.product)

        self.assertTrue(form.initial["is_unique"])
        self.assertNotIn(self.unique_tag, form.fields["tags"].queryset)
        self.assertIn(self.birthday_tag, form.fields["tags"].queryset)
        self.assertIn("منتخب", form.fields["featured"].label)
        self.assertIn("فیلتر یونیک", form.fields["featured"].help_text)

        form.cleaned_data = {
            "tags": Tag.objects.filter(pk=self.birthday_tag.pk),
            "is_unique": False,
        }
        form._save_m2m()
        self.assertFalse(self.product.tags.filter(slug=UNIQUE_TAG_SLUG).exists())

        form = ConcreteProductAdminForm(instance=self.product)
        form.cleaned_data = {
            "tags": Tag.objects.filter(pk=self.birthday_tag.pk),
            "is_unique": True,
        }
        form._save_m2m()
        self.assertTrue(self.product.tags.filter(slug=UNIQUE_TAG_SLUG).exists())

    def test_bulk_unique_actions_add_and_remove_membership(self):
        model_admin = admin.site._registry[Flower]
        queryset = Product.objects.filter(pk=self.product.pk)

        Tag.objects.filter(slug=UNIQUE_TAG_SLUG).delete()

        with patch.object(model_admin, "message_user"):
            model_admin.add_to_unique(request=None, queryset=queryset)
        self.assertTrue(self.product.tags.filter(slug=UNIQUE_TAG_SLUG).exists())

        with patch.object(model_admin, "message_user"):
            model_admin.remove_from_unique(request=None, queryset=queryset)
        self.assertFalse(self.product.tags.filter(slug=UNIQUE_TAG_SLUG).exists())


class ProductBulkDeleteAdminTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="catalog-action-admin",
            email="catalog-action-admin@example.invalid",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            name="گل‌های حذف گروهی",
            slug="bulk-delete-flowers",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        self.product = Product.objects.create(
            name="گل قابل حذف",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

    def _request(self, path):
        request = RequestFactory().get(path)
        request.user = self.user
        return request

    def test_primary_product_list_exposes_confirmed_bulk_delete(self):
        url = reverse("admin:main_flower_changelist")
        model_admin = admin.site._registry[Flower]
        actions = model_admin.get_actions(self._request(url))

        self.assertIn("delete_selected", actions)
        self.assertEqual(
            actions["delete_selected"][2],
            "حذف کامل محصولات انتخاب‌شده",
        )

        confirmation = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.product.pk)],
                "index": "0",
            },
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        completed = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.product.pk)],
                "post": "yes",
            },
        )
        self.assertEqual(completed.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())

    def test_product_change_form_loads_the_price_grouping_control(self):
        response = self.client.get(
            reverse("admin:main_flower_change", args=[self.product.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-toman-price-input="true"')
        self.assertContains(response, "main/js/admin/product-price-input.js")

    def test_same_day_list_exposes_confirmed_full_delete(self):
        self.product.catalog_scope = Product.CatalogScope.SAME_DAY
        self.product.save(update_fields=["catalog_scope", "updated_at"])
        url = reverse("admin:main_samedayflower_changelist")
        model_admin = admin.site._registry[SameDayFlower]

        actions = model_admin.get_actions(self._request(url))

        self.assertIn("delete_selected", actions)
        self.assertNotIn("remove_from_same_day", actions)

        confirmation = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.product.pk)],
                "index": "0",
            },
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        completed = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": [str(self.product.pk)],
                "post": "yes",
            },
        )
        self.assertEqual(completed.status_code, 302)
        self.assertFalse(Product.objects.filter(pk=self.product.pk).exists())


class TagDeletionSafetyTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="tag-delete-admin",
            email="tag-delete-admin@example.invalid",
            password="test-password",
        )
        self.client.force_login(self.user)
        self.category = Category.objects.create(
            name="محصولات دارای برچسب",
            slug="tagged-products",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        self.product = Product.objects.create(
            name="محصول ماندگار",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
            catalog_scope=Product.CatalogScope.GENERAL,
        )
        self.tag = Tag.objects.create(
            name="برچسب قابل حذف",
            slug="deletable-tag",
            is_active=True,
            is_occasion=True,
        )
        self.product.tags.add(self.tag)

    def _request(self, path):
        request = RequestFactory().get(path)
        request.user = self.user
        return request

    def assert_product_unchanged(self):
        self.product.refresh_from_db()
        self.assertEqual(self.product.name, "محصول ماندگار")
        self.assertEqual(self.product.category, self.category)
        self.assertEqual(
            self.product.publish_status,
            Product.PublishStatus.PUBLISHED,
        )
        self.assertEqual(
            self.product.catalog_scope,
            Product.CatalogScope.GENERAL,
        )

    def test_single_tag_delete_only_removes_the_relationship(self):
        url = reverse("admin:main_tag_delete", args=[self.tag.pk])

        confirmation = self.client.get(url)
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "محصولی حذف یا جابه‌جا نمی‌شود")
        self.assertContains(confirmation, "از 1 محصول مرتبط")

        completed = self.client.post(url, {"post": "yes"})
        self.assertEqual(completed.status_code, 302)
        self.assertFalse(Tag.objects.filter(pk=self.tag.pk).exists())
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())
        self.assert_product_unchanged()
        self.assertFalse(self.product.tags.exists())

    def test_bulk_tag_delete_only_removes_relationships(self):
        second_tag = Tag.objects.create(
            name="برچسب دوم قابل حذف",
            slug="second-deletable-tag",
            is_active=True,
        )
        self.product.tags.add(second_tag)
        url = reverse("admin:main_tag_changelist")
        selected = [str(self.tag.pk), str(second_tag.pk)]

        confirmation = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": selected,
                "index": "0",
            },
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertContains(confirmation, "محصولی حذف یا جابه‌جا نمی‌شود")
        self.assertTrue(Product.objects.filter(pk=self.product.pk).exists())

        completed = self.client.post(
            url,
            {
                "action": "delete_selected",
                "_selected_action": selected,
                "post": "yes",
            },
        )
        self.assertEqual(completed.status_code, 302)
        self.assertFalse(Tag.objects.filter(pk__in=selected).exists())
        self.assert_product_unchanged()
        self.assertFalse(self.product.tags.exists())

    def test_unique_system_tag_cannot_be_deleted_from_admin(self):
        unique_tag = Tag.objects.create(
            name="یونیک محافظت‌شده",
            slug=UNIQUE_TAG_SLUG,
            is_active=True,
        )
        model_admin = admin.site._registry[Tag]
        url = reverse("admin:main_tag_delete", args=[unique_tag.pk])

        self.assertFalse(
            model_admin.has_delete_permission(self._request(url), unique_tag)
        )

        bulk_url = reverse("admin:main_tag_changelist")
        confirmation = self.client.post(
            bulk_url,
            {
                "action": "delete_selected",
                "_selected_action": [str(unique_tag.pk)],
                "index": "0",
            },
        )
        self.assertEqual(confirmation.status_code, 200)
        self.assertTrue(Tag.objects.filter(pk=unique_tag.pk).exists())
        self.assertContains(confirmation, "برچسب سیستمی یونیک")
