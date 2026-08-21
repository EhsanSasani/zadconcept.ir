import base64
from datetime import timedelta

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db.models import QuerySet
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from . import views
from .models import (
    BakeryItem,
    Category,
    Event,
    GiftItem,
    HomeHeroSlide,
    LeadRequest,
    PageContentBlock,
    Product,
    ProductImage,
    PublishStatus,
    SiteHero,
    Tag,
    WEDDING_ROOT_CATEGORY_SLUG,
    WorkshopPageContent,
)
from .admin import CategoryAdminForm, EventAdminForm, HeroAdminForm


VALID_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def uploaded_png(name="test.png"):
    return SimpleUploadedFile(name, VALID_PNG, content_type="image/png")


class MainViewsTests(TestCase):
    def setUp(self):
        self.flowers_category = Category.objects.create(
            name="Bouquet",
            slug="bouquet",
            section=Category.Section.FLOWERS,
        )
        self.bakery_category = Category.objects.create(
            name="Daily Bakery",
            slug="daily-bakery",
            section=Category.Section.BAKERY,
        )
        self.gifts_category = Category.objects.create(
            name="Gift Box",
            slug="gift-box",
            section=Category.Section.GIFTS,
        )

        self.flower = Product.objects.create(
            name="Red Rose",
            pricing_type=Product.PricingType.FIXED,
            price=450000,
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.flowers_category,
            description="Test flower product",
        )
        self.bakery = Product.objects.create(
            name="Chocolate Cake",
            pricing_type=Product.PricingType.FIXED,
            price=560000,
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.bakery_category,
            description="Test bakery product",
        )
        self.gift_product = Product.objects.create(
            name="Gift Box",
            pricing_type=Product.PricingType.FIXED,
            price=320000,
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.gifts_category,
            description="Test gift product",
        )

        self.birthday_tag = Tag.objects.create(
            name="تولد",
            slug="birthday",
            is_occasion=True,
        )
        self.condolence_tag = Tag.objects.create(
            name="ترحیم",
            slug="condolence",
            is_occasion=True,
        )
        self.flower.tags.add(self.birthday_tag, self.condolence_tag)
        self.bakery.tags.add(self.birthday_tag)
        self.gift_product.tags.add(self.birthday_tag)

        self.published_event = Event.objects.create(
            title="Published Event",
            description="Test event",
            start_at=timezone.now() + timedelta(days=2),
            end_at=timezone.now() + timedelta(days=2, hours=3),
            location="Mashhad",
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.draft_event = Event.objects.create(
            title="Draft Event",
            description="Draft",
            start_at=timezone.now() + timedelta(days=5),
            end_at=timezone.now() + timedelta(days=5, hours=2),
            location="Mashhad",
            status=PublishStatus.DRAFT,
        )

    def test_index_page_loads(self):
        response = self.client.get(reverse("index"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, reverse("flowers"))

    def test_general_catalog_section_selector_keeps_card_relations_eager_loaded(self):
        with self.assertNumQueries(2):
            products = list(
                views._published_products_for_section(Category.Section.BAKERY)
            )
            self.assertEqual(products, [self.bakery])
            product = products[0]
            self.assertEqual(product.category, self.bakery_category)
            self.assertEqual(list(product.tags.all()), [self.birthday_tag])
            self.assertIn("category", product._state.fields_cache)
            self.assertIn("tags", product._prefetched_objects_cache)

    def test_active_occasion_selector_preserves_membership_order_limit_and_list_contract(self):
        self.birthday_tag.name = "Beta Occasion"
        self.birthday_tag.sort_order = 10
        self.birthday_tag.save(update_fields=["name", "sort_order", "updated_at"])
        self.condolence_tag.name = "Alpha Occasion"
        self.condolence_tag.sort_order = 10
        self.condolence_tag.save(update_fields=["name", "sort_order", "updated_at"])
        later_occasion = Tag.objects.create(
            name="Later Occasion",
            slug="later-occasion",
            is_occasion=True,
            sort_order=20,
        )
        inactive_occasion = Tag.objects.create(
            name="Inactive Occasion",
            slug="inactive-occasion",
            is_occasion=True,
            is_active=False,
            sort_order=0,
        )
        expected = [self.condolence_tag, self.birthday_tag, later_occasion]

        occasions = views._active_occasion_tags()

        self.assertIsInstance(occasions, list)
        self.assertNotIn(inactive_occasion, occasions)
        self.assertEqual(occasions, expected)
        self.assertEqual(views._active_occasion_tags(limit=2), expected[:2])
        self.assertEqual(views._active_occasion_tags(limit=0), expected)

    def test_occasion_detail_hero_preserves_configured_and_unknown_fallbacks(self):
        expected_birthday = {
            "page_hero_kicker": "ZAD OCCASIONS · Birthday",
            "page_hero_title": "تولد",
            "page_hero_text": "برای لحظه‌ای که باید با گل، رنگ و یک یاد شیرین ماندگار شود.",
            "page_hero_image": "main/img/occasion-detail-hero-v1.webp",
            "page_hero_mobile_image": "main/img/occasion-detail-hero-mobile-v1.webp",
            "page_hero_style_class": "hero-style--occasion-detail",
            "page_hero_content_position": "center-right",
            "page_hero_mobile_content_position": "bottom-right",
        }
        unknown_tag = Tag(
            slug="team-thanks",
            name="Team Thanks",
            description="",
        )

        with self.assertNumQueries(0):
            birthday_hero = views._occasion_detail_hero(self.birthday_tag)
            explicit_title_hero = views._occasion_detail_hero(
                self.birthday_tag,
                title="Birthday Celebration",
            )
            unknown_hero = views._occasion_detail_hero(unknown_tag)

        self.assertEqual(birthday_hero, expected_birthday)
        self.assertEqual(
            explicit_title_hero,
            {
                **expected_birthday,
                "page_hero_title": "Birthday Celebration",
            },
        )
        self.assertEqual(
            unknown_hero,
            {
                "page_hero_kicker": "ZAD OCCASIONS · Team Thanks",
                "page_hero_title": "Team Thanks",
                "page_hero_text": "انتخاب‌هایی هماهنگ برای این لحظه.",
                "page_hero_image": "main/img/occasion-detail-hero-v1.webp",
                "page_hero_mobile_image": "main/img/occasion-detail-hero-mobile-v1.webp",
                "page_hero_style_class": "hero-style--occasion-detail",
                "page_hero_content_position": "center-right",
                "page_hero_mobile_content_position": "bottom-right",
            },
        )

    def test_category_content_preserves_configured_and_generic_fallbacks(self):
        described_category = Category(
            name="Custom Flowers",
            slug="custom-flowers",
            description="Custom category description",
        )
        blank_category = Category(
            name="Seasonal Flowers",
            slug="seasonal-flowers",
            description="",
        )

        with self.assertNumQueries(0):
            configured = views._category_content(self.flowers_category)
            described = views._category_content(described_category)
            blank = views._category_content(blank_category)

        self.assertEqual(
            configured,
            {
                "label": "بوکت",
                "meta_title": "بوکت گل خاص در مشهد | ZAD",
                "meta_description": "بوکت‌های طراحی‌شده زاد برای انتخاب‌های خاص‌تر و لوکس‌تر.",
                "intro": "چیدمانی طراحی‌شده‌تر برای وقتی که انتخاب باید خاص‌تر باشد.",
                "image": "main/img/sub-bouquet.webp",
                "hero_image": "main/img/hero-subcategory.webp",
            },
        )
        self.assertEqual(
            described,
            {
                "label": "Custom Flowers",
                "meta_title": "Custom Flowers در مشهد | زاد",
                "meta_description": "Custom category description",
                "intro": "Custom category description",
                "image": "main/img/sub-bouquet.webp",
                "hero_image": "main/img/hero-subcategory.webp",
            },
        )
        self.assertEqual(
            blank,
            {
                "label": "Seasonal Flowers",
                "meta_title": "Seasonal Flowers در مشهد | زاد",
                "meta_description": "مشاهده و سفارش محصولات Seasonal Flowers زاد با هماهنگی ارسال در مشهد.",
                "intro": "انتخابی از محصولات این دسته برای لحظه‌های شما.",
                "image": "main/img/sub-bouquet.webp",
                "hero_image": "main/img/hero-subcategory.webp",
            },
        )

    def test_active_category_selector_preserves_membership_order_and_lazy_queryset_contract(self):
        self.flowers_category.name = "Beta Category"
        self.flowers_category.sort_order = 10
        self.flowers_category.save(
            update_fields=["name", "sort_order", "updated_at"]
        )
        alpha_category = Category.objects.create(
            name="Alpha Category",
            slug="alpha-category",
            section=Category.Section.FLOWERS,
            sort_order=10,
        )
        later_category = Category.objects.create(
            name="Later Category",
            slug="later-category",
            section=Category.Section.FLOWERS,
            sort_order=20,
        )
        inactive_category = Category.objects.create(
            name="Inactive Category",
            slug="inactive-category",
            section=Category.Section.FLOWERS,
            is_active=False,
            sort_order=0,
        )
        child_category = Category.objects.create(
            name="Child Category",
            slug="child-category",
            section=Category.Section.FLOWERS,
            parent=self.flowers_category,
            sort_order=0,
        )
        protected_wedding_category, _ = Category.objects.update_or_create(
            slug=WEDDING_ROOT_CATEGORY_SLUG,
            section=Category.Section.FLOWERS,
            defaults={
                "name": "Protected Wedding Category",
                "parent": None,
                "is_active": True,
                "sort_order": 0,
            },
        )

        with self.assertNumQueries(0):
            queryset = views._active_categories_for_section(
                Category.Section.FLOWERS
            )

        self.assertIsInstance(queryset, QuerySet)
        self.assertEqual(queryset.query.order_by, ("sort_order", "name"))

        with self.assertNumQueries(1):
            results = list(queryset)

        self.assertEqual(
            results,
            [alpha_category, self.flowers_category, later_category],
        )

    def test_general_catalog_surfaces_preserve_exact_membership_and_order(self):
        featured = self.bakery
        featured.featured = True
        featured.sort_order = 100
        featured.save(update_fields=["featured", "sort_order", "updated_at"])

        older_tied = Product.objects.create(
            name="Older tied bakery product",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            sort_order=10,
        )
        newer_tied = Product.objects.create(
            name="Newer tied bakery product",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            sort_order=10,
        )
        later_sort = Product.objects.create(
            name="Later-sort bakery product",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            sort_order=20,
        )
        draft = Product.objects.create(
            name="Draft bakery control",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.DRAFT,
            sort_order=0,
        )
        inactive = Product.objects.create(
            name="Inactive bakery control",
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            is_active=False,
            sort_order=0,
        )

        reference_time = timezone.now()
        Product.objects.filter(pk=older_tied.pk).update(
            created_at=reference_time - timedelta(days=2)
        )
        Product.objects.filter(pk=newer_tied.pk).update(
            created_at=reference_time - timedelta(days=1)
        )

        expected_ids = [
            featured.pk,
            newer_tied.pk,
            older_tied.pk,
            later_sort.pk,
        ]
        surfaces = (
            (reverse("bakery"), "catalog_products"),
            (reverse("bakery_all"), "items"),
            (
                reverse(
                    "bakery_subcategory",
                    args=[self.bakery_category.slug],
                ),
                "items",
            ),
        )

        for url, context_key in surfaces:
            with self.subTest(url=url, context_key=context_key):
                response = self.client.get(url)
                actual_ids = [
                    product.pk for product in response.context[context_key]
                ]
                self.assertEqual(actual_ids, expected_ids)
                self.assertNotIn(draft.pk, actual_ids)
                self.assertNotIn(inactive.pk, actual_ids)

    def test_representative_pages_keep_shared_context_envelope(self):
        pages = (
            (
                reverse("index"),
                "index.html",
                "home",
                "home",
                True,
            ),
            (
                reverse("bakery"),
                "flowers_landing.html",
                "flowers_landing",
                "bakery",
                True,
            ),
            (
                self.flower.get_absolute_url(),
                "item_detail.html",
                "item",
                "flowers",
                True,
            ),
            (
                reverse("occasion_detail", args=[self.birthday_tag.slug]),
                "occasion_detail.html",
                "occasion-detail",
                "occasions",
                True,
            ),
            (
                reverse("contact"),
                "contact.html",
                "contact",
                "",
                False,
            ),
        )

        for url, template, page_type, active_nav, enable_product_modal in pages:
            with self.subTest(url=url):
                response = self.client.get(url)
                expected_canonical = f"{settings.ZAD_SITE_URL}{url}"
                page_graph_nodes = [
                    node
                    for node in response.context["structured_data_graph"]
                    if node.get("@id") == f"{expected_canonical}#webpage"
                ]

                self.assertEqual(response.status_code, 200)
                self.assertTemplateUsed(response, template)
                self.assertEqual(response.context["page_type"], page_type)
                self.assertEqual(response.context["active_nav"], active_nav)
                self.assertEqual(
                    response.context["enable_product_modal"],
                    enable_product_modal,
                )
                self.assertEqual(
                    response.context["canonical_url"],
                    expected_canonical,
                )
                self.assertEqual(response.context["robots_content"], "index,follow")
                self.assertEqual(len(page_graph_nodes), 1)

    def test_policy_views_preserve_routing_context_and_normalization(self):
        routes = (
            ("privacy", "privacy"),
            ("terms", "terms"),
            ("delivery_policy", "delivery"),
            ("refund_policy", "refund"),
            ("payment_methods", "payment"),
            ("service_area", "service-area"),
        )

        for route_name, policy_slug in routes:
            with self.subTest(route_name=route_name):
                expected = views.POLICY_PAGES[policy_slug]
                response = self.client.get(reverse(route_name))

                self.assertEqual(response.status_code, 200)
                self.assertIs(response.resolver_match.func, views.policy_page)
                self.assertTemplateUsed(response, "policy_page.html")
                self.assertEqual(response.context["page_type"], "policy")
                self.assertEqual(response.context["active_nav"], "")
                self.assertIs(response.context["suppress_default_hero"], True)
                self.assertEqual(
                    response.context["meta_title"],
                    expected["meta_title"],
                )
                self.assertEqual(
                    response.context["meta_description"],
                    expected["meta_description"],
                )
                self.assertEqual(
                    response.context["breadcrumbs"],
                    [
                        {"name": "Home", "url": reverse("index")},
                        {"name": expected["title"], "url": None},
                    ],
                )

                normalized = response.context["policy"]
                self.assertEqual(normalized["title"], expected["title"])

                for section in normalized.get("sections", []):
                    self.assertIsInstance(section["paragraphs"], list)
                    self.assertIsInstance(section["items"], list)

        normalized = views._normalized_policy(
            {
                "title": "Contract",
                "sections": [
                    {
                        "title": "String values",
                        "paragraphs": "One paragraph",
                        "items": "One item",
                    },
                    {
                        "title": "Missing values",
                    },
                    {
                        "title": "List values",
                        "paragraphs": ["A", "B"],
                        "items": ["X", "Y"],
                    },
                ],
            }
        )

        self.assertEqual(
            normalized["sections"],
            [
                {
                    "title": "String values",
                    "paragraphs": ["One paragraph"],
                    "items": ["One item"],
                },
                {
                    "title": "Missing values",
                    "paragraphs": [],
                    "items": [],
                },
                {
                    "title": "List values",
                    "paragraphs": ["A", "B"],
                    "items": ["X", "Y"],
                },
            ],
        )

    def test_international_order_views_preserve_routing_templates_and_context(self):
        managed_content = PageContentBlock.objects.create(
            page="international-orders",
            section_key="international-contract",
            title="Managed international content",
        )
        expected_page_content = {
            managed_content.section_key: {
                "kicker": managed_content.kicker,
                "title": managed_content.title,
                "body": managed_content.body,
                "cta_text": managed_content.cta_text,
                "cta_url": managed_content.cta_url,
            }
        }
        fa_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders')}"
        en_url = f"{settings.ZAD_SITE_URL}{reverse('international_orders_en')}"
        alternate_links = [
            {"language": "fa", "url": fa_url},
            {"language": "en", "url": en_url},
            {"language": "x-default", "url": fa_url},
        ]
        pages = (
            {
                "language": "Persian",
                "route": "international_orders",
                "view": views.international_orders,
                "template": "international_orders.html",
                "meta_title": "سفارش گل از خارج ایران برای مشهد | زاد",
                "meta_description": "ثبت سفارش گل و هدیه از خارج ایران با پرداخت ارزی و تحویل محلی برای گیرنده در مشهد.",
                "canonical_url": fa_url,
                "html_lang": "fa",
                "html_dir": "rtl",
                "og_locale": "fa_IR",
                "hide_global_chrome": False,
                "faq_items": views.INTERNATIONAL_FAQ_FA,
            },
            {
                "language": "English",
                "route": "international_orders_en",
                "view": views.international_orders_en,
                "template": "international_orders_en.html",
                "meta_title": "Send Flowers to Mashhad, Iran | ZAD",
                "meta_description": "Order flowers, gifts, and bakery items from abroad for local delivery to your recipient in Mashhad, Iran.",
                "canonical_url": en_url,
                "html_lang": "en",
                "html_dir": "ltr",
                "og_locale": "en_US",
                "hide_global_chrome": True,
                "faq_items": views.INTERNATIONAL_FAQ_EN,
            },
        )

        for page in pages:
            with self.subTest(language=page["language"]):
                response = self.client.get(reverse(page["route"]))

                self.assertEqual(response.status_code, 200)
                self.assertIs(response.resolver_match.func, page["view"])
                self.assertEqual(response.templates[0].name, page["template"])
                self.assertEqual(response.context["page_type"], "policy")
                self.assertEqual(response.context["active_nav"], "")
                self.assertEqual(response.context["meta_title"], page["meta_title"])
                self.assertEqual(
                    response.context["meta_description"],
                    page["meta_description"],
                )
                self.assertEqual(
                    response.context["canonical_url"],
                    page["canonical_url"],
                )
                self.assertEqual(response.context["html_lang"], page["html_lang"])
                self.assertEqual(response.context["html_dir"], page["html_dir"])
                self.assertEqual(response.context["og_locale"], page["og_locale"])
                self.assertEqual(
                    response.context["hide_global_chrome"],
                    page["hide_global_chrome"],
                )
                self.assertIs(response.context["suppress_default_hero"], True)
                self.assertIs(response.context["has_managed_site_hero"], False)
                self.assertEqual(response.context["faq_items"], page["faq_items"])
                self.assertEqual(
                    response.context["alternate_links"],
                    alternate_links,
                )
                self.assertEqual(
                    response.context["page_content"],
                    expected_page_content,
                )

    def test_default_page_presentation_fallbacks_remain_exact(self):
        bakery_response = self.client.get(reverse("bakery"))
        self.assertEqual(
            bakery_response.context["meta_title"],
            "سفارش سوئیت‌بار و شیرینی در مشهد | زاد",
        )
        self.assertEqual(
            bakery_response.context["meta_description"],
            "سفارش محصولات سوئیت‌بار زاد برای هدیه، پذیرایی و مناسبت‌ها در مشهد.",
        )
        self.assertEqual(bakery_response.context["active_nav"], "bakery")
        self.assertEqual(bakery_response.context["lead_default_type"], "bakery")

        contact_response = self.client.get(reverse("contact"))
        self.assertEqual(contact_response.context["page_hero_kicker"], "Contact zad")
        self.assertEqual(
            contact_response.context["page_hero_title"],
            "Let’s Arrange It",
        )
        self.assertEqual(
            contact_response.context["page_hero_text"],
            "For availability, timing and order details.",
        )
        self.assertEqual(
            contact_response.context["page_hero_image"],
            "main/img/hero-contact.webp",
        )

        privacy_response = self.client.get(reverse("privacy"))
        self.assertEqual(
            privacy_response.context["page_hero_title"],
            privacy_response.context["meta_title"],
        )
        self.assertEqual(
            privacy_response.context["page_hero_text"],
            privacy_response.context["meta_description"],
        )
        self.assertEqual(
            privacy_response.context["page_hero_image"],
            "main/img/hero-2.webp",
        )
        self.assertEqual(privacy_response.context["page_hero_style_class"], "")
        self.assertEqual(
            privacy_response.context["page_hero_content_position"],
            "center-left",
        )
        self.assertEqual(
            privacy_response.context["page_hero_mobile_content_position"],
            "bottom-center",
        )

    def test_managed_site_hero_preserves_active_scoped_and_fallback_selection(self):
        target_page = SiteHero.TargetPage.SUBCATEGORY
        generic_hero = SiteHero.objects.create(
            title="Generic managed Hero",
            image="heroes/pages/generic.jpg",
            target_page=target_page,
            target_slug="",
        )
        scoped_hero = SiteHero.objects.create(
            title="Scoped managed Hero",
            image="heroes/pages/scoped.jpg",
            target_page=target_page,
            target_slug="managed-scope",
        )
        inactive_scoped_hero = SiteHero.objects.create(
            title="Inactive scoped Hero",
            image="heroes/pages/inactive.jpg",
            target_page=target_page,
            target_slug="inactive-scope",
            is_active=False,
        )

        with self.assertNumQueries(1):
            scoped_result = views._get_site_hero(
                target_page,
                scoped_hero.target_slug,
            )
        with self.assertNumQueries(1):
            generic_result = views._get_site_hero(target_page)
        with self.assertNumQueries(2):
            inactive_result = views._get_site_hero(
                target_page,
                inactive_scoped_hero.target_slug,
            )
        with self.assertNumQueries(2):
            fallback_result = views._get_site_hero(target_page, "missing-scope")
        with self.assertNumQueries(1):
            no_fallback_result = views._get_site_hero(
                target_page,
                "missing-scope",
                allow_fallback=False,
            )

        self.assertEqual(
            [slide["title"] for slide in scoped_result["page_hero_slides"]],
            [scoped_hero.title],
        )
        self.assertEqual(generic_result["page_hero_title"], generic_hero.title)
        self.assertEqual(inactive_result["page_hero_title"], generic_hero.title)
        self.assertEqual(fallback_result["page_hero_title"], generic_hero.title)
        self.assertIsNone(no_fallback_result)

    def test_home_hero_uses_all_admin_managed_fields(self):
        HomeHeroSlide.objects.create(
            title="Admin Home Hero",
            kicker="ADMIN KICKER",
            description="Admin home description",
            image="heroes/home/desktop.jpg",
            mobile_image="heroes/home/mobile/mobile.jpg",
            primary_button_text="Primary action",
            primary_button_url="/flowers/",
            secondary_button_text="Secondary action",
            secondary_button_url="/contact/",
        )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "/media/heroes/home/desktop.jpg")
        self.assertContains(response, "/media/heroes/home/mobile/mobile.jpg")
        self.assertContains(response, "Admin Home Hero")
        self.assertContains(response, "Admin home description")
        self.assertContains(response, 'href="/flowers/"')
        self.assertContains(response, 'href="/contact/"')

    def test_legacy_section_redirects_to_new_category(self):
        response = self.client.get(reverse("index"), {"section": "bakery"})
        self.assertRedirects(response, reverse("bakery"), fetch_redirect_response=False)

    def test_flowers_landing_page_loads(self):
        response = self.client.get(reverse("flowers"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["directory_only"])
        self.assertContains(response, self.flowers_category.name)
        self.assertContains(response, self.flowers_category.get_absolute_url())
    def test_flowers_legacy_page_query_redirects_to_clean_landing(self):
        response = self.client.get(reverse("flowers"), {"page": 2})

        self.assertRedirects(
            response,
            reverse("flowers"),
            status_code=301,
            fetch_redirect_response=False,
        )
    def test_collection_landing_paginates_initial_products_and_partial_next_page(self):
        for index in range(14):
            Product.objects.create(
                name=f"Paged Bakery {index:02d}",
                publish_status=Product.PublishStatus.PUBLISHED,
                category=self.bakery_category,
                sort_order=index + 10,
            )

        response = self.client.get(reverse("bakery"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["catalog_products"]), 12)
        self.assertTrue(response.context["catalog_page_obj"].has_next())

        partial = self.client.get(
            reverse("bakery"),
            {"partial": "products", "page": 2},
        )

        self.assertEqual(partial.status_code, 200)
        payload = partial.json()
        self.assertIn("html", payload)
        self.assertFalse(payload["has_next"])
        self.assertContains(partial, "Paged Bakery", status_code=200)

        second_page = self.client.get(reverse("bakery"), {"page": 2})
        first_ids = {product.pk for product in response.context["catalog_products"]}
        second_ids = {product.pk for product in second_page.context["catalog_products"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_collection_landing_filters_category_on_server(self):
        other_category = Category.objects.create(
            name="Box",
            slug="box",
            section=Category.Section.BAKERY,
        )
        other_product = Product.objects.create(
            name="Box Flower",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=other_category,
        )

        response = self.client.get(reverse("bakery"), {"category": "box"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["catalog_products"]), [other_product])

    def test_new_published_flower_appears_and_draft_or_inactive_do_not(self):
        visible = Product.objects.create(
            name="Fresh Visible Flower",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.flowers_category,
        )
        Product.objects.create(
            name="Draft Hidden Flower",
            publish_status=Product.PublishStatus.DRAFT,
            category=self.flowers_category,
        )
        Product.objects.create(
            name="Inactive Hidden Flower",
            is_active=False,
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.flowers_category,
        )

        response = self.client.get(
            reverse("flower_subcategory", args=[self.flowers_category.slug])
        )

        self.assertContains(response, visible.display_name)
        self.assertNotContains(response, "Draft Hidden Flower")
        self.assertNotContains(response, "Inactive Hidden Flower")

    def test_product_pricing_contact_text_uses_pricing_type(self):
        inquiry_product = Product.objects.create(
            name="Inquiry Flower",
            pricing_type=Product.PricingType.INQUIRY,
            price=999,
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.flowers_category,
        )

        self.assertTrue(self.flower.has_price)
        self.assertIn("ثبت سفارش", self.flower.order_contact_text)
        self.assertFalse(inquiry_product.has_price)
        self.assertIsNone(inquiry_product.price)
        self.assertIn("استعلام قیمت", inquiry_product.order_contact_text)

    def test_collection_landing_uses_page_hero_from_admin(self):
        SiteHero.objects.create(
            title="Admin Flowers Hero",
            kicker="ADMIN FLOWERS",
            description="Admin flowers description",
            image="heroes/pages/flowers.jpg",
            mobile_image="heroes/pages/mobile/flowers.jpg",
            target_page=SiteHero.TargetPage.FLOWERS,
        )

        response = self.client.get(reverse("flowers"))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["landing_hero_title"], "Admin Flowers Hero")
        self.assertEqual(response.context["landing_hero_eyebrow"], "ADMIN FLOWERS")
        self.assertEqual(
            response.context["landing_hero_mobile_image"],
            "/media/heroes/pages/mobile/flowers.jpg",
        )
        self.assertContains(response, "Admin flowers description")
        self.assertContains(response, "/media/heroes/pages/flowers.jpg")
        self.assertContains(response, "/media/heroes/pages/mobile/flowers.jpg")

    def test_category_page_contains_filter_fallback_link(self):
        response = self.client.get(reverse("bakery"))
        self.assertEqual(response.status_code, 200)
        expected_url = reverse(
            "bakery_subcategory",
            args=[self.bakery_category.slug],
        )
        self.assertContains(response, f'href="{expected_url}"')

    def test_bakery_and_gifts_use_the_shared_collection_landing(self):
        for route_name, product, category in (
            ("bakery", self.bakery, self.bakery_category),
            ("gifts", self.gift_product, self.gifts_category),
        ):
            with self.subTest(route_name=route_name):
                response = self.client.get(reverse(route_name))
                self.assertTemplateUsed(response, "flowers_landing.html")
                self.assertTemplateUsed(response, "partials/catalog_filter.html")
                self.assertContains(response, 'class="flowers-hero ')
                self.assertContains(response, 'data-filter-count="2"')
                self.assertContains(response, '>همه<')
                self.assertContains(response, f'data-filter="{category.slug}"')
                self.assertContains(response, f'data-category="{category.slug}"')
                self.assertNotContains(response, "flowers-filter__chip")
                self.assertContains(response, product.product_code)

    def test_subcategory_page_loads(self):
        response = self.client.get(reverse("flower_subcategory", args=["bouquet"]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.flower.display_name)

    def test_occasion_tags_share_art_direction_but_keep_distinct_copy(self):
        birthday = self.client.get(reverse("occasion_detail", args=["birthday"]))
        condolence = self.client.get(reverse("occasion_detail", args=["condolence"]))
        flower_birthday = self.client.get(reverse("flower_occasion", args=["birthday"]))

        for response in (birthday, condolence, flower_birthday):
            with self.subTest(path=response.request["PATH_INFO"]):
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    response.context["page_hero_image"],
                    "main/img/occasion-detail-hero-v1.webp",
                )
                self.assertEqual(
                    response.context["page_hero_mobile_image"],
                    "main/img/occasion-detail-hero-mobile-v1.webp",
                )
                self.assertContains(response, 'class="page-hero__content container"')
                self.assertContains(response, 'media="(max-width: 760px)"')

        self.assertContains(birthday, "برای لحظه‌ای که باید با گل، رنگ و یک یاد شیرین ماندگار شود.")
        self.assertContains(condolence, "برای ابراز همدلی؛ باوقار، آرام و محترمانه.")
        self.assertNotEqual(
            birthday.context["page_hero_text"],
            condolence.context["page_hero_text"],
        )

    def test_occasion_all_products_follow_category_sort_order(self):
        self.flowers_category.sort_order = 30
        self.flowers_category.save(update_fields=["sort_order"])
        self.bakery_category.sort_order = 10
        self.bakery_category.save(update_fields=["sort_order"])
        self.gifts_category.sort_order = 20
        self.gifts_category.save(update_fields=["sort_order"])

        response = self.client.get(reverse("occasion_detail", args=["birthday"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [product.pk for product in response.context["products"]],
            [
                self.bakery.pk,
                self.gift_product.pk,
                self.flower.pk,
            ],
        )

    def test_occasion_detail_always_exposes_available_product_filters(self):
        response = self.client.get(reverse("occasion_detail", args=["birthday"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["label"] for item in response.context["filter_links"]],
            ["همه", "Daily Bakery", "Bouquet", "Gift Box"],
        )
        self.assertTemplateUsed(response, "partials/catalog_filter.html")
        self.assertContains(response, 'data-filter-count="4"')
        self.assertContains(response, 'aria-label="فیلتر نوع محصول"')
        self.assertNotContains(response, "catalog-filter-chip")
        self.assertContains(response, "?category=bouquet&amp;section=flowers")

        filtered = self.client.get(
            reverse("occasion_detail", args=["birthday"]),
            {"category": "bouquet", "section": "flowers"},
        )

        self.assertEqual(filtered.status_code, 200)
        self.assertEqual(filtered.context["products"], [self.flower])
        self.assertTrue(
            next(
                item
                for item in filtered.context["filter_links"]
                if item["label"] == "Bouquet"
            )["is_active"]
        )

    def test_catalog_filter_keeps_five_managed_names_immediately_available(self):
        fifth_category = Category.objects.create(
            name="دسته گل ویژه",
            slug="special-bouquet",
            section=Category.Section.FLOWERS,
        )
        fifth_product = Product.objects.create(
            name="Special Birthday Bouquet",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=fifth_category,
        )
        fifth_product.tags.add(self.birthday_tag)

        response = self.client.get(reverse("occasion_detail", args=["birthday"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.context["filter_links"]), 5)
        self.assertContains(response, 'data-filter-count="5"')
        self.assertContains(response, 'class="catalog-filter__item"', count=5)
        self.assertContains(response, "دسته گل ویژه")
        self.assertEqual(response.context["filter_links"][0]["label"], "همه")

    def test_wedding_uses_the_dedicated_landing_and_not_an_occasion_page(self):
        wedding_root, _ = Category.objects.update_or_create(
            slug="wedding",
            section=Category.Section.FLOWERS,
            defaults={"name": "Wedding", "parent": None, "is_active": True},
        )
        wedding_category, _ = Category.objects.update_or_create(
            slug="bridal-bouquet",
            section=Category.Section.FLOWERS,
            defaults={
                "name": "Bridal Bouquet",
                "parent": wedding_root,
                "is_active": True,
            },
        )
        wedding_tag, _ = Tag.objects.update_or_create(
            slug="wedding",
            defaults={
                "name": "عروسی",
                "is_occasion": True,
                "is_active": True,
                "sort_order": 85,
            },
        )
        wedding_product = Product.objects.create(
            name="Wedding Arrangement",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=wedding_category,
            catalog_scope=Product.CatalogScope.WEDDING,
            wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
        )

        wedding_response = self.client.get(reverse("weddings"))
        legacy_response = self.client.get(reverse("occasion_detail", args=["wedding"]))

        self.assertFalse(wedding_tag in Tag.objects.for_general_catalog())
        self.assertTemplateUsed(wedding_response, "weddings.html")
        self.assertEqual(wedding_response.context["active_nav"], "weddings")
        self.assertNotContains(wedding_response, wedding_product.name)
        self.assertRedirects(
            legacy_response,
            reverse("weddings"),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_legacy_wedding_flower_url_redirects_to_the_occasion(self):
        response = self.client.get(reverse("flower_subcategory", args=["wedding"]))

        self.assertRedirects(
            response,
            reverse("weddings"),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_event_views_preserve_routing_templates_context_and_errors(self):
        list_response = self.client.get(reverse("events"))

        self.assertEqual(list_response.status_code, 200)
        self.assertIs(list_response.resolver_match.func, views.events)
        self.assertTemplateUsed(list_response, "events.html")
        self.assertEqual(list_response.context["page_type"], "workshops")
        self.assertEqual(list_response.context["active_nav"], "events")
        self.assertEqual(
            list_response.context["breadcrumbs"],
            [
                {"name": "Home", "url": reverse("index")},
                {"name": "ورکشاپ‌ها", "url": None},
            ],
        )
        self.assertEqual(list_response.context["lead_default_type"], "event")
        self.assertTrue(list_response.context["lead_form"].include_event_fields)
        self.assertEqual(
            list_response.context["lead_form"].fields["lead_type"].initial,
            "event",
        )
        self.assertIn(self.published_event, list(list_response.context["events"]))
        self.assertNotIn(self.draft_event, list(list_response.context["events"]))
        self.assertIsInstance(
            list_response.context["workshop_copy"],
            WorkshopPageContent,
        )
        self.assertEqual(
            list_response.context["workshops_hero_kicker"],
            "ZAD WORKSHOPS",
        )
        self.assertEqual(
            list_response.context["workshops_hero_title"],
            "ورکشاپ‌های زاد",
        )
        self.assertEqual(
            list_response.context["workshops_hero_image"],
            "main/img/workshops-hero.webp",
        )
        self.assertEqual(
            list_response.context["workshops_hero_mobile_image"],
            "",
        )

        detail_url = reverse(
            "event_detail",
            args=[self.published_event.slug],
        )
        detail_response = self.client.get(detail_url)

        self.assertEqual(detail_response.status_code, 200)
        self.assertIs(detail_response.resolver_match.func, views.event_detail)
        self.assertTemplateUsed(detail_response, "event_detail.html")
        self.assertEqual(detail_response.context["event"], self.published_event)
        self.assertEqual(detail_response.context["page_type"], "category")
        self.assertEqual(detail_response.context["active_nav"], "events")
        self.assertEqual(detail_response.context["og_type"], "article")
        self.assertEqual(
            detail_response.context["breadcrumbs"],
            [
                {"name": "Home", "url": reverse("index")},
                {"name": "Events", "url": reverse("events")},
                {"name": self.published_event.title, "url": None},
            ],
        )
        self.assertEqual(detail_response.context["lead_default_type"], "event")
        self.assertTrue(detail_response.context["lead_form"].include_event_fields)
        self.assertEqual(
            detail_response.context["lead_form"].fields["lead_type"].initial,
            "event",
        )

        event_nodes = [
            node
            for node in detail_response.context["structured_data_graph"]
            if node.get("@type") == "Event"
        ]
        self.assertEqual(len(event_nodes), 1)
        self.assertEqual(event_nodes[0]["name"], self.published_event.title)
        self.assertEqual(
            event_nodes[0]["@id"],
            f"{settings.ZAD_SITE_URL.rstrip('/')}{detail_url}#event",
        )

        draft_response = self.client.get(
            reverse("event_detail", args=[self.draft_event.slug])
        )
        missing_response = self.client.get(
            reverse("event_detail", args=["missing-event"])
        )

        self.assertEqual(draft_response.status_code, 404)
        self.assertEqual(missing_response.status_code, 404)

    def test_events_page_shows_only_published(self):
        response = self.client.get(reverse("events"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.published_event.title)
        self.assertNotContains(response, self.draft_event.title)

    def test_events_page_shows_only_future_published_events(self):
        past_event = Event.objects.create(
            title="Past Event",
            description="Past",
            start_at=timezone.now() - timedelta(days=3),
            end_at=timezone.now() - timedelta(days=3, hours=-2),
            location="Mashhad",
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        response = self.client.get(reverse("events"))

        self.assertContains(response, self.published_event.title)
        self.assertNotContains(response, past_event.title)

    def test_events_page_also_shows_an_ongoing_published_event(self):
        ongoing_event = Event.objects.create(
            title="Ongoing Workshop",
            description="Already started and still open",
            start_at=timezone.now() - timedelta(hours=1),
            end_at=timezone.now() + timedelta(hours=2),
            location="Mashhad",
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now(),
        )

        self.assertContains(self.client.get(reverse("events")), ongoing_event.title)

    def test_workshops_use_concrete_experience_copy(self):
        workshops = self.client.get(reverse("events"))
        home = self.client.get(reverse("index"))

        self.assertContains(workshops, "فضایی برای کار با دست‌ها")
        self.assertContains(workshops, "در ورکشاپ‌های زاد چه تجربه‌ای دارید؟")
        self.assertContains(home, "کار عملی با متریال")
        self.assertContains(home, "انتخاب و ساختن با سلیقه شخصی")
        self.assertNotContains(workshops, "فعلاً با گل‌ها")
        self.assertNotContains(workshops, "گل، مرز ورکشاپ‌های زاد نیست")
        self.assertNotContains(home, "به گل محدود نمی‌مانند")

    def test_workshops_page_uses_managed_section_copy(self):
        WorkshopPageContent.objects.create(
            story_kicker="Managed story kicker",
            story_title="Managed story title",
            story_text="Managed story text",
            types_kicker="Managed types kicker",
            types_title="Managed types title",
            public_title="Managed public title",
            public_text="Managed public text",
            private_title="Managed private title",
            private_text="Managed private text",
            corporate_title="Managed corporate title",
            corporate_text="Managed corporate text",
            upcoming_kicker="Managed upcoming kicker",
            upcoming_title="Managed upcoming title",
            upcoming_empty_title="Managed empty title",
            upcoming_empty_text="Managed empty text",
            cta_title="Managed CTA title",
            cta_text="Managed CTA text",
        )

        response = self.client.get(reverse("events"))

        for managed_copy in (
            "Managed story kicker",
            "Managed story title",
            "Managed story text",
            "Managed types kicker",
            "Managed types title",
            "Managed public title",
            "Managed public text",
            "Managed private title",
            "Managed private text",
            "Managed corporate title",
            "Managed corporate text",
            "Managed upcoming kicker",
            "Managed upcoming title",
            "Managed CTA title",
            "Managed CTA text",
        ):
            with self.subTest(managed_copy=managed_copy):
                self.assertContains(response, managed_copy)

        self.published_event.delete()
        empty_response = self.client.get(reverse("events"))
        self.assertContains(empty_response, "Managed empty title")
        self.assertContains(empty_response, "Managed empty text")

    def test_events_page_uses_page_hero_from_admin(self):
        SiteHero.objects.create(
            title="Admin Events Hero",
            kicker="ADMIN EVENTS",
            description="Admin events description",
            image="heroes/pages/events.jpg",
            mobile_image="heroes/pages/mobile/events.jpg",
            target_page=SiteHero.TargetPage.EVENTS,
        )

        response = self.client.get(reverse("events"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Admin Events Hero")
        self.assertContains(response, "ADMIN EVENTS")
        self.assertContains(response, "Admin events description")
        self.assertContains(response, "/media/heroes/pages/events.jpg")
        self.assertContains(response, "/media/heroes/pages/mobile/events.jpg")

    def test_page_hero_supports_multiple_ordered_slides(self):
        for order, title in ((2, "Second page slide"), (1, "First page slide")):
            SiteHero.objects.create(
                title=title,
                image=f"heroes/pages/{order}.jpg",
                target_page=SiteHero.TargetPage.CONTACT,
                sort_order=order,
            )

        response = self.client.get(reverse("contact"))

        self.assertEqual(
            [slide["title"] for slide in response.context["page_hero_slides"]],
            ["First page slide", "Second page slide"],
        )
        self.assertContains(response, "data-page-hero-slider")
        self.assertContains(response, "data-page-hero-next")

    def test_visit_urls_redirect_to_contact(self):
        contact_url = reverse("contact")

        for visit_url in ("/visit/", "/Visit"):
            with self.subTest(visit_url=visit_url):
                response = self.client.get(visit_url)
                self.assertRedirects(
                    response,
                    contact_url,
                    status_code=301,
                    fetch_redirect_response=False,
                )

    def test_static_content_views_preserve_routing_templates_and_context(self):
        cases = (
            (
                "contact",
                "contact.html",
                "contact",
                "",
                "Contact",
                "main/img/hero-contact.webp",
            ),
            (
                "faq",
                "faq.html",
                "category",
                "",
                "FAQ",
                "main/img/hero-faq.webp",
            ),
            (
                "about",
                "about.html",
                "about",
                "about",
                "About",
                "main/img/hero-about.webp",
            ),
        )

        responses = {}

        for (
            route_name,
            template_name,
            page_type,
            active_nav,
            breadcrumb_name,
            hero_image,
        ) in cases:
            with self.subTest(route_name=route_name):
                url = reverse(route_name)
                response = self.client.get(url)
                responses[route_name] = response

                self.assertEqual(response.status_code, 200)
                self.assertIs(
                    response.resolver_match.func,
                    getattr(views, route_name),
                )
                self.assertTemplateUsed(response, template_name)
                self.assertEqual(response.context["page_type"], page_type)
                self.assertEqual(response.context["active_nav"], active_nav)
                self.assertEqual(
                    response.context["breadcrumbs"],
                    [
                        {"name": "Home", "url": reverse("index")},
                        {"name": breadcrumb_name, "url": None},
                    ],
                )
                self.assertEqual(
                    response.context["page_hero_image"],
                    hero_image,
                )

        contact_response = responses["contact"]
        self.assertEqual(
            contact_response.context["lead_default_type"],
            "flower",
        )
        self.assertEqual(
            contact_response.context["lead_form"].fields["lead_type"].initial,
            "flower",
        )

        faq_response = responses["faq"]
        self.assertTrue(faq_response.context["faq_items"])
        self.assertTrue(faq_response.context["faq_page_groups"])
        faq_nodes = [
            node
            for node in faq_response.context["structured_data_graph"]
            if node.get("@type") == "FAQPage"
        ]
        self.assertEqual(len(faq_nodes), 1)

        about_response = responses["about"]
        self.assertEqual(
            about_response.context["about_hero_image"],
            "main/img/about/zad-floral-wall-v1.webp",
        )
        self.assertEqual(
            about_response.context["about_hero_mobile_image"],
            "",
        )

    def test_contact_and_faq_pages_load(self):
        self.assertEqual(self.client.get(reverse("contact")).status_code, 200)
        self.assertEqual(self.client.get(reverse("faq")).status_code, 200)

    def test_about_page_uses_the_scoped_editorial_redesign(self):
        response = self.client.get(reverse("about"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'class="about-page"')
        self.assertContains(response, "main/css/about.css")
        self.assertNotContains(response, '<section class="page-hero">')

        for image_name in (
            "zad-store-v1.webp",
            "zad-store-flowers-v1.webp",
            "zad-floral-wall-v1.webp",
            "zad-sweetbar-v1.webp",
            "zad-workshop-making-v1.webp",
            "zad-workshop-talk-v1.webp",
            "zad-workshop-space-v1.webp",
        ):
            with self.subTest(image_name=image_name):
                self.assertContains(response, image_name)

    def test_standard_page_hero_uses_admin_mobile_image(self):
        SiteHero.objects.create(
            title="Admin Contact Hero",
            image="heroes/pages/contact.jpg",
            mobile_image="heroes/pages/mobile/contact.jpg",
            target_page=SiteHero.TargetPage.CONTACT,
        )

        response = self.client.get(reverse("contact"))

        self.assertEqual(
            response.context["page_hero_mobile_image"],
            "/media/heroes/pages/mobile/contact.jpg",
        )
        self.assertContains(response, "/media/heroes/pages/mobile/contact.jpg")

    def test_about_page_is_available_as_a_site_hero_target(self):
        self.assertIn(
            (SiteHero.TargetPage.ABOUT, "درباره زاد"),
            SiteHero.TargetPage.choices,
        )

        SiteHero.objects.create(
            title="Admin About Hero",
            image="heroes/pages/about.jpg",
            target_page=SiteHero.TargetPage.ABOUT,
        )

        response = self.client.get(reverse("about"))

        self.assertEqual(response.context["page_hero_title"], "Admin About Hero")
        self.assertEqual(response.context["about_hero_title"], "Admin About Hero")
        self.assertContains(response, "/media/heroes/pages/about.jpg")

    def test_detail_redirects_when_slug_is_wrong(self):
        response = self.client.get(reverse("flower_detail", args=[self.flower.pk, "wrong-slug"]))
        self.assertRedirects(
            response,
            self.flower.get_absolute_url(),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_products_use_section_and_category_in_their_canonical_urls(self):
        expected = {
            self.flower: reverse(
                "flower_product_detail",
                args=[self.flowers_category.slug, self.flower.slug],
            ),
            self.bakery: reverse(
                "bakery_product_detail",
                args=[self.bakery_category.slug, self.bakery.slug],
            ),
            self.gift_product: reverse(
                "gift_product_detail",
                args=[self.gifts_category.slug, self.gift_product.slug],
            ),
        }

        for product, url in expected.items():
            with self.subTest(product=product):
                self.assertEqual(product.get_absolute_url(), url)
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_legacy_events_urls_redirect_to_workshops(self):
        self.assertRedirects(
            self.client.get("/events/"),
            reverse("events"),
            status_code=301,
            fetch_redirect_response=False,
        )
        self.assertRedirects(
            self.client.get(f"/events/{self.published_event.slug}/"),
            self.published_event.get_absolute_url(),
            status_code=301,
            fetch_redirect_response=False,
        )

    def test_admin_page_content_overrides_contact_copy(self):
        PageContentBlock.objects.create(
            page=PageContentBlock.Page.CONTACT,
            section_key="intro",
            title="Editable contact heading",
            body="Editable contact body",
        )

        response = self.client.get(reverse("contact"))
        self.assertContains(response, "Editable contact heading")
        self.assertContains(response, "Editable contact body")

    def test_lead_form_submit_creates_row(self):
        response = self.client.post(
            reverse("lead_request"),
            {
                "full_name": "Test User",
                "mobile": "09121234567",
                "lead_type": LeadRequest.LeadType.FLOWER,
                "delivery_window": LeadRequest.DeliveryWindow.TODAY,
                "note": "Test",
                "next": reverse("contact"),
                "source_page": "/contact/",
            },
        )
        self.assertRedirects(response, reverse("contact"), fetch_redirect_response=False)
        self.assertEqual(LeadRequest.objects.count(), 1)

    def test_seo_utility_views_preserve_routing_content_and_indexnow_contract(self):
        robots_response = self.client.get(reverse("robots_txt"))

        self.assertEqual(robots_response.status_code, 200)
        self.assertIs(robots_response.resolver_match.func, views.robots_txt)
        self.assertEqual(
            robots_response["Content-Type"],
            "text/plain; charset=utf-8",
        )
        self.assertEqual(
            robots_response["Cache-Control"],
            "public, max-age=3600",
        )

        expected_robots = [
            "# Search and answer-engine crawlers",
            "User-agent: Googlebot",
            "User-agent: Bingbot",
            "User-agent: OAI-SearchBot",
            "User-agent: ChatGPT-User",
            "User-agent: PerplexityBot",
            "User-agent: Claude-SearchBot",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /accounts/",
            "Disallow: /auth/",
            "Disallow: /search/",
            "Disallow: /lead-request/",
            "Disallow: /csp-report/",
            "",
            "# Model-training crawlers are handled separately from search crawlers",
            "User-agent: GPTBot",
            "User-agent: ClaudeBot",
            "User-agent: Google-Extended",
            "User-agent: CCBot",
            "Disallow: /",
            "",
            "User-agent: *",
            "Allow: /",
            "Disallow: /admin/",
            "Disallow: /accounts/",
            "Disallow: /auth/",
            "Disallow: /search/",
            "Disallow: /lead-request/",
            "Disallow: /csp-report/",
            f"Sitemap: {settings.ZAD_SITE_URL}{reverse('sitemap')}",
        ]
        self.assertEqual(
            robots_response.content.decode("utf-8").splitlines(),
            expected_robots,
        )

        self.assertEqual(
            views.INDEXNOW_KEY_PATTERN.pattern,
            r"^[A-Za-z0-9-]{8,128}$",
        )

        key = "zad-indexnow-12345678"

        with self.settings(INDEXNOW_KEY=key):
            url = reverse("indexnow_key", args=[key])
            valid_response = self.client.get(url)

            self.assertEqual(valid_response.status_code, 200)
            self.assertIs(
                valid_response.resolver_match.func,
                views.indexnow_key,
            )
            self.assertEqual(
                valid_response["Content-Type"],
                "text/plain; charset=utf-8",
            )
            self.assertEqual(
                valid_response["Cache-Control"],
                "public, max-age=86400",
            )
            self.assertEqual(
                valid_response["X-Robots-Tag"],
                "noindex, nofollow",
            )
            self.assertEqual(valid_response.content.decode("utf-8"), key)

            head_response = self.client.head(url)
            self.assertEqual(head_response.status_code, 200)
            self.assertEqual(
                head_response["X-Robots-Tag"],
                "noindex, nofollow",
            )

            wrong_response = self.client.get(
                reverse("indexnow_key", args=["wrong-key-12345678"])
            )
            self.assertEqual(wrong_response.status_code, 404)

            post_response = self.client.post(url)
            self.assertEqual(post_response.status_code, 404)

    def test_robots_and_sitemap_routes(self):
        self.assertEqual(self.client.get(reverse("robots_txt")).status_code, 200)
        self.assertEqual(self.client.get(reverse("sitemap")).status_code, 200)

    def test_proxy_products_save_with_correct_section(self):
        bakery = BakeryItem.objects.create(
            name="Proxy Bakery",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.bakery_category,
        )
        gift = GiftItem.objects.create(
            name="Proxy Gift",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=self.gifts_category,
        )

        self.assertTrue(bakery.product_code)
        self.assertTrue(gift.product_code)
        self.assertContains(self.client.get(reverse("bakery")), bakery.display_name)
        self.assertContains(self.client.get(reverse("gifts")), gift.display_name)

    def test_gallery_ordering_is_stable(self):
        first = ProductImage.objects.create(
            product=self.flower,
            image="products/gallery/first.jpg",
            ordering=2,
        )
        second = ProductImage.objects.create(
            product=self.flower,
            image="products/gallery/second.jpg",
            ordering=1,
        )

        self.assertEqual(list(self.flower.gallery_images.all()), [second, first])

    def test_catalog_invalid_page_is_safe_and_out_of_range_is_404(self):
        invalid = self.client.get(reverse("flowers"), {"page": "not-a-number"})
        missing = self.client.get(
            reverse("flowers"),
            {"partial": "products", "page": 9999},
        )

        self.assertEqual(invalid.status_code, 200)
        self.assertEqual(missing.status_code, 404)

    def test_products_in_inactive_categories_are_not_public(self):
        inactive_category = Category.objects.create(
            name="Inactive Flowers",
            slug="inactive-flowers",
            section=Category.Section.FLOWERS,
            is_active=False,
        )
        hidden_product = Product.objects.create(
            name="Hidden by category",
            category=inactive_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            is_active=False,
        )
        # Simulate pre-validation legacy data and verify the public query still
        # fails closed when the category itself is inactive.
        Product.objects.filter(pk=hidden_product.pk).update(is_active=True)
        hidden_product.refresh_from_db()

        response = self.client.get(reverse("flowers"))
        self.assertNotContains(response, hidden_product.display_name)

    def test_proxy_slug_generation_checks_the_concrete_product_table(self):
        same_name = self.flower.name
        bakery = BakeryItem.objects.create(
            name=same_name,
            category=self.bakery_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )
        gift = GiftItem.objects.create(
            name=same_name,
            category=self.gifts_category,
            publish_status=Product.PublishStatus.PUBLISHED,
        )

        self.assertEqual(len({self.flower.slug, bakery.slug, gift.slug}), 3)

    def test_new_tags_are_internal_until_marked_as_occasions(self):
        tag = Tag.objects.create(name="Internal Tag", slug="internal-tag")
        self.assertFalse(tag.is_occasion)
        self.assertNotContains(self.client.get(reverse("occasions")), tag.name)

        tag.is_occasion = True
        tag.save(update_fields=["is_occasion", "updated_at"])
        self.assertContains(self.client.get(reverse("occasions")), tag.name)

    def test_multiple_home_slides_remain_visible_in_admin_order(self):
        HomeHeroSlide.objects.create(
            title="First managed slide",
            image="heroes/home/first.jpg",
            sort_order=1,
        )
        HomeHeroSlide.objects.create(
            title="Second managed slide",
            image="heroes/home/second.jpg",
            sort_order=2,
        )

        response = self.client.get(reverse("index"))
        self.assertContains(response, "First managed slide")
        self.assertContains(response, "Second managed slide")
        self.assertEqual(len(response.context["home_hero_slides"]), 2)

    def test_workshop_copy_keeps_only_the_latest_active_record(self):
        first = WorkshopPageContent.objects.create(story_title="First", is_active=True)
        second = WorkshopPageContent.objects.create(story_title="Second", is_active=True)
        first.refresh_from_db()

        self.assertFalse(first.is_active)
        self.assertEqual(WorkshopPageContent.current(), second)

    def test_event_model_rejects_an_end_before_its_start(self):
        start = timezone.now() + timedelta(days=1)
        invalid_event = Event(
            title="Invalid Event",
            description="Invalid",
            start_at=start,
            end_at=start - timedelta(hours=1),
            location="Mashhad",
        )

        with self.assertRaises(ValidationError):
            invalid_event.full_clean()

    def test_admin_image_forms_accept_valid_images_and_reject_large_files(self):
        category_form = CategoryAdminForm(
            data={
                "name": "Image Category",
                "slug": "image-category",
                "section": Category.Section.FLOWERS,
                "description": "",
                "is_active": True,
                "sort_order": 0,
            },
            files={"cover_image": uploaded_png("category.png")},
        )
        self.assertTrue(category_form.is_valid(), category_form.errors)

        event_form = EventAdminForm(
            data={
                "title": "Image Event",
                "slug": "image-event",
                "description": "Event description",
                "start_at": timezone.now() + timedelta(days=1),
                "end_at": timezone.now() + timedelta(days=1, hours=2),
                "location": "Mashhad",
                "status": PublishStatus.DRAFT,
                "published_at": "",
            },
            files={"cover_image": uploaded_png("event.png")},
        )
        self.assertTrue(event_form.is_valid(), event_form.errors)

        oversized = SimpleUploadedFile(
            "too-large.jpg",
            b"x" * (10 * 1024 * 1024 + 1),
            content_type="image/jpeg",
        )
        class HomeHeroTestForm(HeroAdminForm):
            class Meta:
                model = HomeHeroSlide
                fields = "__all__"

        hero_form = HomeHeroTestForm(
            data={
                "title": "Hero",
                "kicker": "",
                "description": "",
                "is_active": True,
                "sort_order": 0,
            },
            files={"image": oversized},
        )
        self.assertFalse(hero_form.is_valid())


class AdminSmokeTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin-smoke-test",
            email="admin-smoke@example.invalid",
            password="test-password",
        )
        self.client.force_login(self.user)

    def test_every_registered_admin_list_and_add_page_loads(self):
        for model in admin.site._registry:
            model_meta = model._meta
            route_prefix = f"admin:{model_meta.app_label}_{model_meta.model_name}"

            for route_suffix in ("changelist", "add"):
                with self.subTest(model=model_meta.label, page=route_suffix):
                    response = self.client.get(
                        reverse(f"{route_prefix}_{route_suffix}")
                    )
                    self.assertEqual(response.status_code, 200)

    def test_site_hero_can_be_edited_through_admin(self):
        hero = SiteHero.objects.create(
            title="Before edit",
            image="heroes/pages/edit-test.jpg",
            target_page=SiteHero.TargetPage.CONTACT,
        )
        change_url = reverse("admin:main_sitehero_change", args=[hero.pk])

        self.assertEqual(self.client.get(change_url).status_code, 200)

        response = self.client.post(
            change_url,
            {
                "title": "After edit",
                "kicker": "",
                "description": "",
                "target_page": SiteHero.TargetPage.CONTACT,
                "target_slug": "",
                "content_position": "center-left",
                "mobile_content_position": "bottom-center",
                "text_color": "#FFFFFF",
                "builtin_font": "estedad",
                "title_font_size": "68",
                "body_font_size": "18",
                "mobile_title_font_size": "40",
                "mobile_body_font_size": "14",
                "is_active": "on",
                "sort_order": "0",
                "_save": "Save",
            },
        )

        self.assertEqual(response.status_code, 302)
        hero.refresh_from_db()
        self.assertEqual(hero.title, "After edit")
