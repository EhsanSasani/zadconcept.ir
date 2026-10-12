from django.test import TestCase

from main.models import Category, Product, Tag
from main.product_recommendations import complementary_groups


class ComplementaryProductsTests(TestCase):
    def setUp(self):
        self.categories = {section: Category.objects.create(name=section, slug=f"pair-{section}", section=section)
                           for section in ("flowers", "bakery", "gifts")}
        self.flower = self.product("flowers", "flower")
        self.cake = self.product("bakery", "cake")
        self.gift = self.product("gifts", "gift")

    def product(self, section, name, **kwargs):
        return Product.objects.create(category=self.categories[section], name=name,
                                      publish_status="published", **kwargs)

    def test_cross_section_suggestions_work_in_both_directions(self):
        for source in (self.flower, self.cake, self.gift):
            groups = complementary_groups(source)
            self.assertEqual({group["section"] for group in groups}, set(self.categories) - {source.category.section})
            self.assertNotIn(source.pk, [item.pk for group in groups for item in group["products"]])

    def test_ready_stock_then_shared_active_occasion_then_featured(self):
        occasion = Tag.objects.create(name="Birthday", slug="pair-birthday", is_active=True, is_occasion=True)
        self.flower.tags.add(occasion)
        match = self.product("bakery", "matched")
        match.tags.add(occasion)
        featured = self.product("bakery", "featured", featured=True)
        preorder = self.product("bakery", "preorder", stock_status="preorder", featured=True)
        preorder.tags.add(occasion)
        products = complementary_groups(self.flower)[0]["products"]
        self.assertEqual([item.pk for item in products], [match.pk, featured.pk, self.cake.pk, preorder.pk])

    def test_unavailable_private_and_inactive_products_are_excluded(self):
        self.product("bakery", "unavailable", stock_status="out_of_stock")
        draft = self.product("bakery", "draft")
        Product.objects.filter(pk=draft.pk).update(publish_status="draft")
        self.product("bakery", "inactive", is_active=False)
        groups = complementary_groups(self.flower)
        self.assertEqual([item.pk for item in groups[0]["products"]], [self.cake.pk])
        self.categories["bakery"].is_active = False
        self.categories["bakery"].save()
        self.assertEqual([group["section"] for group in complementary_groups(self.flower)], ["gifts"])

    def test_empty_sections_are_omitted_and_limit_is_per_section(self):
        self.gift.delete()
        for index in range(6):
            self.product("bakery", f"cake-{index}")
        groups = complementary_groups(self.flower)
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]["products"]), 4)

    def test_same_day_sold_or_withdrawn_items_never_become_complements(self):
        ready = self.product("flowers", "ready", catalog_scope="same_day")
        self.product("flowers", "sold", catalog_scope="same_day", status="SOLD")
        self.product("flowers", "withdrawn", catalog_scope="same_day", status="WITHDRAWN")
        flowers = complementary_groups(self.cake)[0]["products"]
        self.assertEqual({item.pk for item in flowers}, {self.flower.pk, ready.pk})

    def test_inactive_or_non_occasion_tags_do_not_affect_ranking(self):
        featured = self.product("bakery", "editorial", featured=True)
        for slug, active, occasion in (("inactive", False, True), ("style", True, False)):
            tag = Tag.objects.create(name=slug, slug=slug, is_active=active, is_occasion=occasion)
            self.flower.tags.add(tag)
            self.cake.tags.add(tag)
        self.assertEqual(complementary_groups(self.flower)[0]["products"][0].pk, featured.pk)

    def test_detail_renders_complements_and_catalog_uses_direct_links(self):
        response = self.client.get(self.flower.get_absolute_url())
        self.assertContains(response, 'id="related-products-title"')
        self.assertContains(response, self.cake.get_absolute_url())
        self.assertNotContains(response, "THE PERFECT PAIR")
        self.assertNotContains(response, "item-detail__tags")
        self.assertNotContains(response, self.flower.get_absolute_url() + '" class="flowers-product-card__main"')
        self.assertEqual([item.pk for item in response.context["complementary_items"]], [self.cake.pk, self.gift.pk])
        self.assertNotContains(response, "product-dialog.js")
        self.assertNotContains(response, "data-zad-modal-card")
