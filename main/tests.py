import base64
from datetime import timedelta

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

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

    def test_home_carousel_hides_inactive_slide_content_from_keyboard_and_at(self):
        for order, title in ((1, "First"), (2, "Second")):
            HomeHeroSlide.objects.create(
                title=title,
                image=f"heroes/home/{order}.jpg",
                primary_button_text=f"Open {title}",
                primary_button_url=f"/slide-{order}/",
                sort_order=order,
            )

        response = self.client.get(reverse("index"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "data-home-hero-toggle", count=1)
        self.assertContains(response, 'aria-roledescription="carousel"', count=1)
        self.assertContains(response, 'aria-hidden="false"', count=1)
        self.assertContains(response, 'aria-hidden="true" inert', count=1)

    def test_legacy_section_redirects_to_new_category(self):
        response = self.client.get(reverse("index"), {"section": "bakery"})
        self.assertRedirects(response, reverse("bakery"), fetch_redirect_response=False)

    def test_flowers_landing_page_loads(self):
        response = self.client.get(reverse("flowers"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context["directory_only"])
        self.assertEqual(response.context["catalog_products"], [])
        self.assertContains(response, self.flowers_category.get_absolute_url())
        self.assertNotContains(response, self.flower.product_code)

    def test_collection_landing_paginates_products_and_partial_next_page(self):
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
        self.assertEqual(payload["page_count"], 3)
        self.assertEqual(payload["total_count"], 15)
        self.assertContains(partial, "Paged Bakery", status_code=200)

        second_page = self.client.get(reverse("bakery"), {"page": 2})
        first_ids = {product.pk for product in response.context["catalog_products"]}
        second_ids = {product.pk for product in second_page.context["catalog_products"]}
        self.assertTrue(first_ids.isdisjoint(second_ids))

    def test_collection_landing_filters_category_on_server(self):
        other_category = Category.objects.create(
            name="Cookie",
            slug="cookie",
            section=Category.Section.BAKERY,
        )
        other_product = Product.objects.create(
            name="Cookie Box",
            publish_status=Product.PublishStatus.PUBLISHED,
            category=other_category,
        )

        response = self.client.get(reverse("bakery"), {"category": "cookie"})

        self.assertEqual(response.status_code, 200)
        self.assertEqual(list(response.context["catalog_products"]), [other_product])

    def test_empty_catalog_filter_keeps_a_valid_controls_target(self):
        empty_category = Category.objects.create(
            name="Empty Bakery",
            slug="empty-bakery",
            section=Category.Section.BAKERY,
        )

        response = self.client.get(
            reverse("bakery"),
            {"category": empty_category.slug},
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'id="catalog-products"', count=1)
        self.assertContains(response, 'aria-controls="catalog-products"')

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
                self.assertContains(response, 'class="flowers-hero hero-configurable')
                self.assertContains(response, f'data-filter="{category.slug}"')
                self.assertContains(response, f'data-category="{category.slug}"')
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

    def test_occasion_detail_always_exposes_available_product_filters(self):
        response = self.client.get(reverse("occasion_detail", args=["birthday"]))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item["label"] for item in response.context["filter_links"]],
            ["All", "Daily Bakery", "Bouquet", "Gift Box"],
        )
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

    def test_wedding_uses_dedicated_catalog_and_not_an_occasion_page(self):
        wedding_category = Category.objects.get(
            slug="bridal-bouquet",
            section=Category.Section.FLOWERS,
        )
        wedding_tag, _ = Tag.objects.update_or_create(
            slug="wedding",
            defaults={
                "name": "عروسی",
                "is_occasion": False,
                "is_active": False,
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

        occasions_response = self.client.get(reverse("occasions"))
        wedding_response = self.client.get(reverse("weddings"))
        collection_response = self.client.get(
            reverse("wedding_collection", args=["bridal-bouquets"])
        )

        self.assertNotContains(
            occasions_response,
            f'href="{reverse("occasion_detail", args=["wedding"])}"',
        )
        self.assertNotIn(wedding_tag, Tag.objects.for_general_catalog())
        self.assertTemplateUsed(wedding_response, "weddings.html")
        self.assertEqual(wedding_response.context["active_nav"], "weddings")
        self.assertNotContains(wedding_response, wedding_product.name)
        self.assertContains(collection_response, wedding_product.name)

    def test_legacy_wedding_occasion_url_redirects_to_weddings(self):
        response = self.client.get(reverse("occasion_detail", args=["wedding"]))

        self.assertRedirects(
            response,
            reverse("weddings"),
            status_code=301,
            fetch_redirect_response=False,
        )

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

    def test_custom_page_heroes_share_the_accessible_carousel_contract(self):
        for target_page, route_name in (
            (SiteHero.TargetPage.ABOUT, "about"),
            (SiteHero.TargetPage.EVENTS, "events"),
        ):
            for order in (1, 2):
                SiteHero.objects.create(
                    title=f"{route_name} slide {order}",
                    image=f"heroes/pages/{route_name}-{order}.jpg",
                    target_page=target_page,
                    sort_order=order,
                )

            with self.subTest(route=route_name):
                response = self.client.get(reverse(route_name))
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, "data-page-hero-toggle", count=1)
                self.assertContains(response, 'aria-roledescription="carousel"', count=1)
                self.assertContains(response, 'aria-hidden="true" inert', count=1)
                self.assertContains(response, 'aria-current="true"', count=1)

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

    def test_invalid_lead_form_preserves_values_and_exposes_specific_errors(self):
        response = self.client.post(
            reverse("lead_request"),
            {
                "full_name": "کاربر آزمایشی",
                "mobile": "bad-number",
                "lead_type": LeadRequest.LeadType.FLOWER,
                "delivery_window": LeadRequest.DeliveryWindow.PICK_DATE,
                "next": reverse("contact"),
                "source_page": reverse("contact"),
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertEqual(LeadRequest.objects.count(), 0)
        self.assertContains(response, 'role="alert"', status_code=422)
        self.assertContains(response, 'data-form-error-summary', status_code=422)
        self.assertContains(response, 'value="کاربر آزمایشی"', status_code=422)
        self.assertContains(response, 'aria-invalid="true"', status_code=422)
        self.assertContains(response, 'id="id_mobile_error"', status_code=422)
        self.assertContains(response, 'id="id_preferred_date_error"', status_code=422)
        self.assertContains(response, 'content="noindex,follow"', status_code=422)

    def test_lead_inputs_expose_mobile_and_autofill_metadata(self):
        response = self.client.get(reverse("contact"))

        self.assertContains(response, 'autocomplete="name"')
        self.assertContains(response, 'type="tel"')
        self.assertContains(response, 'autocomplete="tel"')

    def test_irrelevant_conditional_value_error_remains_repairable(self):
        response = self.client.post(
            reverse("lead_request"),
            {
                "full_name": "Conditional Error",
                "mobile": "09121234567",
                "lead_type": LeadRequest.LeadType.FLOWER,
                "delivery_window": LeadRequest.DeliveryWindow.TODAY,
                "preferred_date": "not-a-date",
                "next": reverse("contact"),
                "source_page": reverse("contact"),
            },
        )

        self.assertEqual(response.status_code, 422)
        self.assertContains(response, 'data-lead-date-field', status_code=422)
        self.assertContains(response, 'id="id_preferred_date_error"', status_code=422)
        self.assertContains(response, 'aria-invalid="true"', status_code=422)

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
                "custom_font": "",
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
