from types import SimpleNamespace

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse

from ..admin import ProductAdminForm
from ..models import (
    LEGACY_SAME_DAY_TAG_SLUG,
    PROPOSAL_COLLECTION_TAG_SLUG,
    Category,
    Flower,
    Product,
    SameDayFlower,
    Tag,
)


class SameDayAdminScopeTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Same-day admin flowers",
            slug="same-day-admin-flowers",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.user = get_user_model().objects.create_superuser(
            username="same-day-admin",
            email="same-day-admin@example.invalid",
            password="test-password",
        )
        cls.visible_tag = Tag.objects.create(
            name="Visible admin tag",
            slug="visible-admin-tag",
            is_active=True,
            is_occasion=True,
        )
        cls.legacy_same_day_tag, _ = Tag.objects.update_or_create(
            slug=LEGACY_SAME_DAY_TAG_SLUG,
            defaults={
                "name": "ارسال روز",
                "is_active": False,
                "is_occasion": False,
            },
        )

    def setUp(self):
        self.general_product = Product.objects.create(
            name="General flower",
            category=self.category,
        )
        self.same_day_product = Product.objects.create(
            name="Same-day isolated product",
            category=self.category,
            catalog_scope=Product.CatalogScope.SAME_DAY,
        )
        self.request = RequestFactory().get(
            reverse("admin:main_samedayflower_changelist")
        )
        self.request.user = self.user

    def test_proxy_managers_and_admin_lists_are_strictly_isolated(self):
        flower_ids = set(Flower.objects.values_list("pk", flat=True))
        same_day_ids = set(SameDayFlower.objects.values_list("pk", flat=True))

        self.assertIn(self.general_product.pk, flower_ids)
        self.assertNotIn(self.same_day_product.pk, flower_ids)
        self.assertEqual(same_day_ids, {self.same_day_product.pk})

        flower_admin = admin.site._registry[Flower]
        same_day_admin = admin.site._registry[SameDayFlower]
        self.assertEqual(
            set(flower_admin.get_queryset(self.request).values_list("pk", flat=True)),
            {self.general_product.pk},
        )
        self.assertEqual(
            set(
                same_day_admin.get_queryset(self.request).values_list(
                    "pk", flat=True
                )
            ),
            {self.same_day_product.pk},
        )

    def test_saving_from_same_day_admin_forces_same_day_scope(self):
        model_admin = admin.site._registry[SameDayFlower]

        model_admin.save_model(
            self.request,
            self.general_product,
            form=SimpleNamespace(),
            change=True,
        )

        self.general_product.refresh_from_db()
        self.assertEqual(
            self.general_product.catalog_scope,
            Product.CatalogScope.SAME_DAY,
        )

    def test_same_day_admin_has_full_delete_and_no_remove_membership_action(self):
        model_admin = admin.site._registry[SameDayFlower]
        actions = model_admin.get_actions(self.request)

        self.assertIn("delete_selected", actions)
        self.assertEqual(
            actions["delete_selected"][2],
            "حذف کامل محصولات انتخاب‌شده",
        )
        self.assertNotIn("remove_from_same_day", actions)

    def test_legacy_same_day_marker_is_not_available_as_a_tag(self):
        class ConcreteProductAdminForm(ProductAdminForm):
            class Meta(ProductAdminForm.Meta):
                model = Product
                fields = "__all__"

        form = ConcreteProductAdminForm(instance=self.same_day_product)

        self.assertNotIn(
            self.legacy_same_day_tag,
            form.fields["tags"].queryset,
        )
        self.assertIn(self.visible_tag, form.fields["tags"].queryset)


class ProductAdminHiddenTagTests(TestCase):
    def test_regular_tag_save_preserves_hidden_proposal_collection_membership(self):
        category = Category.objects.create(
            name="Hidden tag flowers",
            slug="hidden-tag-flowers",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        product = Product.objects.create(name="Tagged product", category=category)
        proposal_collection_tag = Tag.objects.create(
            name="کالکشن خواستگاری (سیستمی)",
            slug=PROPOSAL_COLLECTION_TAG_SLUG,
            is_active=False,
            is_occasion=False,
        )
        visible_tag = Tag.objects.create(
            name="Visible form tag",
            slug="visible-form-tag",
            is_active=True,
            is_occasion=True,
        )
        product.tags.add(proposal_collection_tag, visible_tag)

        class ConcreteProductAdminForm(ProductAdminForm):
            class Meta(ProductAdminForm.Meta):
                model = Product
                fields = "__all__"

        form = ConcreteProductAdminForm(instance=product)
        form.cleaned_data = {"tags": Tag.objects.filter(pk=visible_tag.pk)}
        form._save_m2m()

        self.assertEqual(
            set(product.tags.values_list("slug", flat=True)),
            {PROPOSAL_COLLECTION_TAG_SLUG, visible_tag.slug},
        )
