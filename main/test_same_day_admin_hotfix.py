from types import SimpleNamespace
from unittest.mock import patch

from django.contrib import admin
from django.test import TestCase

from .admin import FlowerAdmin, ProductAdminForm, SameDayFlowerAdmin
from .models import (
    PROPOSAL_COLLECTION_TAG_SLUG,
    Category,
    Product,
    SAME_DAY_TAG_SLUG,
    SameDayFlower,
    Tag,
)


class SameDayAdminTagHotfixTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.category = Category.objects.create(
            name="Same-day admin flowers",
            slug="same-day-admin-flowers",
            section=Category.Section.FLOWERS,
            is_active=True,
        )
        cls.same_day_tag, _ = Tag.objects.update_or_create(
            slug=SAME_DAY_TAG_SLUG,
            defaults={
                "name": "ارسال روز",
                "is_active": True,
                "is_occasion": False,
            },
        )
        cls.proposal_collection_tag = Tag.objects.create(
            name="کالکشن خواستگاری (سیستمی)",
            slug=PROPOSAL_COLLECTION_TAG_SLUG,
            is_active=False,
            is_occasion=False,
        )
        cls.visible_tag = Tag.objects.create(
            name="Visible admin tag",
            slug="visible-admin-tag",
            is_active=True,
            is_occasion=True,
        )

    def setUp(self):
        self.product = Product.objects.create(
            name="Same-day editable product",
            category=self.category,
        )
        self.model_admin = SameDayFlowerAdmin(SameDayFlower, admin.site)

    @patch.object(FlowerAdmin, "save_related")
    def test_change_respects_intentional_same_day_tag_removal(self, parent_save):
        self.product.tags.add(self.same_day_tag)
        self.product.tags.remove(self.same_day_tag)

        self.model_admin.save_related(
            request=None,
            form=SimpleNamespace(instance=self.product),
            formsets=[],
            change=True,
        )

        parent_save.assert_called_once()
        self.assertFalse(self.product.tags.filter(slug=SAME_DAY_TAG_SLUG).exists())

    @patch.object(FlowerAdmin, "save_related")
    def test_add_through_same_day_admin_still_enforces_same_day_tag(self, parent_save):
        self.model_admin.save_related(
            request=None,
            form=SimpleNamespace(instance=self.product),
            formsets=[],
            change=False,
        )

        parent_save.assert_called_once()
        self.assertTrue(self.product.tags.filter(slug=SAME_DAY_TAG_SLUG).exists())

    def test_regular_tag_save_preserves_hidden_proposal_collection_membership(self):
        class ConcreteProductAdminForm(ProductAdminForm):
            class Meta(ProductAdminForm.Meta):
                model = Product
                fields = "__all__"

        self.product.tags.add(
            self.same_day_tag,
            self.proposal_collection_tag,
            self.visible_tag,
        )
        form = ConcreteProductAdminForm(instance=self.product)
        form.cleaned_data = {"tags": Tag.objects.filter(pk=self.visible_tag.pk)}

        form._save_m2m()

        slugs = set(self.product.tags.values_list("slug", flat=True))
        self.assertEqual(
            slugs,
            {PROPOSAL_COLLECTION_TAG_SLUG, self.visible_tag.slug},
        )
