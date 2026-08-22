import json
from datetime import timedelta
from io import StringIO
from pathlib import Path
from urllib.parse import urlsplit

from django.conf import settings
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from ..management.commands.audit_seo import SeoHTMLParser
from ..models import (
    Category,
    Event,
    LeadRequest,
    NewsPost,
    Product,
    PublishStatus,
    Tag,
)


def parse_html(response):
    parser = SeoHTMLParser()
    parser.feed(response.content.decode(response.charset or "utf-8"))
    return parser


def graph_for(response):
    parser = parse_html(response)
    if len(parser.jsonld_documents) != 1:
        raise AssertionError(
            f"Expected one JSON-LD graph, found {len(parser.jsonld_documents)}"
        )
    return json.loads(parser.jsonld_documents[0])["@graph"]


class SeoContractTests(TestCase):
    def setUp(self):
        cache.clear()
        self.category = Category.objects.create(
            name="Bouquet",
            slug="bouquet",
            section=Category.Section.FLOWERS,
        )
        self.plants_category = Category.objects.create(
            name="Plants",
            slug="plants",
            section=Category.Section.FLOWERS,
        )
        self.wedding_category, _ = Category.objects.update_or_create(
            slug="wedding",
            section=Category.Section.FLOWERS,
            defaults={"name": "Wedding", "parent": None, "is_active": True},
        )
        self.inactive_category = Category.objects.create(
            name="Hidden",
            slug="hidden",
            section=Category.Section.FLOWERS,
            is_active=False,
        )
        self.same_day, _ = Tag.objects.update_or_create(
            slug="same-day",
            defaults={"name": "ارسال روز", "is_active": True, "is_occasion": False},
        )
        self.birthday, _ = Tag.objects.update_or_create(
            slug="birthday",
            defaults={"name": "تولد", "is_active": True, "is_occasion": True},
        )
        self.unnamed = Product.objects.create(
            name="",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
            pricing_type=Product.PricingType.INQUIRY,
        )
        self.unnamed.tags.add(self.same_day, self.birthday)
        self.fixed = Product.objects.create(
            name="رز قرمز",
            description="دسته گل رز قرمز برای هدیه.",
            category=self.category,
            publish_status=Product.PublishStatus.PUBLISHED,
            pricing_type=Product.PricingType.FIXED,
            price=450000,
        )
        self.draft = Product.objects.create(
            name="Draft",
            category=self.category,
            publish_status=Product.PublishStatus.DRAFT,
        )
        self.hidden = Product.objects.create(
            name="Hidden",
            category=self.inactive_category,
            publish_status=Product.PublishStatus.PUBLISHED,
            is_active=False,
        )
        now = timezone.now()
        self.future_event = Event.objects.create(
            title="ورکشاپ آینده",
            slug="future-workshop",
            description="ورکشاپ گل‌آرایی آینده زاد.",
            start_at=now + timedelta(days=2),
            end_at=now + timedelta(days=2, hours=2),
            location="مشهد",
            status=PublishStatus.PUBLISHED,
        )
        self.past_event = Event.objects.create(
            title="ورکشاپ گذشته",
            slug="past-workshop",
            description="آرشیو ورکشاپ گذشته زاد.",
            start_at=now - timedelta(days=2),
            end_at=now - timedelta(days=2, hours=-2),
            location="مشهد",
            status=PublishStatus.PUBLISHED,
        )

    def test_unnamed_product_has_unique_persian_seo_contract(self):
        response = self.client.get(self.unnamed.get_absolute_url())
        parser = parse_html(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.unnamed.product_code.translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")), self.unnamed.seo_name)
        self.assertIn(self.unnamed.seo_name, parser.title)
        self.assertNotEqual(parser.title.strip().lower(), "| zad")
        self.assertEqual(
            parser.canonical,
            f"https://www.zadconcept.ir{self.unnamed.get_absolute_url()}",
        )
        self.assertTrue(parser.description)

        graph = graph_for(response)
        self.assertFalse(any(node.get("@type") == "Product" for node in graph))
        self.assertFalse(any(node.get("@type") == "BreadcrumbList" for node in graph))
    def test_fixed_price_product_has_complete_offer(self):
        response = self.client.get(self.fixed.get_absolute_url())
        graph = graph_for(response)
        product = next(node for node in graph if node.get("@type") == "Product")

        self.assertEqual(product["offers"]["price"], "4500000")
        self.assertEqual(product["offers"]["priceCurrency"], "IRR")
        self.assertEqual(product["offers"]["availability"], "https://schema.org/InStock")
        self.assertEqual(
            product["offers"]["seller"]["@id"],
            "https://www.zadconcept.ir/#business",
        )
        self.assertNotIn("seller", product)
        self.assertContains(response, '<meta property="og:type" content="product">')

    def test_same_day_page_has_metadata_canonical_and_service(self):
        response = self.client.get(reverse("flowers_same_day"))
        parser = parse_html(response)
        graph = graph_for(response)

        self.assertEqual(response.status_code, 200)
        self.assertIn("ارسال گل امروز در مشهد", parser.title)
        self.assertEqual(
            parser.canonical,
            "https://www.zadconcept.ir/flowers/same-day/",
        )
        self.assertContains(response, self.unnamed.display_name)
        self.assertTrue(any(node.get("@type") == "Service" for node in graph))
        self.assertFalse(any(node.get("@type") == "BreadcrumbList" for node in graph))

    def test_query_policy_separates_filters_partials_and_pagination(self):
        bakery_category = Category.objects.create(
            name="SEO Bakery",
            slug="seo-bakery",
            section=Category.Section.BAKERY,
        )
        filtered = self.client.get(
            reverse("bakery"), {"category": bakery_category.slug}
        )
        filtered_parser = parse_html(filtered)
        self.assertEqual(filtered_parser.robots, "noindex,follow")
        self.assertEqual(filtered_parser.canonical, "https://www.zadconcept.ir/bakery/")

        partial = self.client.get(reverse("bakery"), {"partial": "products"})
        self.assertEqual(partial.status_code, 200)
        self.assertEqual(partial.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(partial.headers["Cache-Control"], "no-store")

        for index in range(13):
            Product.objects.create(
                name=f"Page product {index}",
                category=bakery_category,
                publish_status=Product.PublishStatus.PUBLISHED,
                sort_order=100 + index,
            )
        paginated = self.client.get(reverse("bakery"), {"page": "2"})
        paginated_parser = parse_html(paginated)
        self.assertEqual(paginated_parser.robots, "index,follow")
        self.assertEqual(
            paginated_parser.canonical,
            "https://www.zadconcept.ir/bakery/?page=2",
        )

        irrelevant_page = self.client.get(reverse("contact"), {"page": "2"})
        irrelevant_parser = parse_html(irrelevant_page)
        self.assertEqual(irrelevant_parser.robots, "noindex,follow")
        self.assertEqual(
            irrelevant_parser.canonical,
            "https://www.zadconcept.ir/contact/",
        )

    def test_sitemap_is_model_driven_canonical_and_direct(self):
        response = self.client.get(reverse("sitemap"))
        xml = response.content.decode()

        expected_paths = (
            reverse("about"),
            reverse("occasions"),
            reverse("flowers_same_day"),
            reverse("flowers_all"),
            reverse("bakery_all"),
            reverse("gifts_all"),
            reverse("privacy"),
            reverse("terms"),
            reverse("delivery_policy"),
            reverse("refund_policy"),
            reverse("payment_methods"),
            reverse("service_area"),
            reverse("international_orders"),
            reverse("international_orders_en"),
            self.future_event.get_absolute_url(),
            self.category.get_absolute_url(),
            self.plants_category.get_absolute_url(),
            self.unnamed.get_absolute_url(),
        )
        for path in expected_paths:
            self.assertIn(f"https://www.zadconcept.ir{path}", xml)

        self.assertNotIn("/flowers/plant/", xml)
        self.assertIn("https://www.zadconcept.ir/weddings/", xml)
        self.assertNotIn("https://www.zadconcept.ir/flowers/wedding/", xml)
        self.assertNotIn(self.draft.get_absolute_url(), xml)
        self.assertNotIn(self.hidden.get_absolute_url(), xml)
        self.assertNotIn(self.past_event.get_absolute_url(), xml)

        parser = SeoHTMLParser()
        # Extracting loc elements with a small deterministic split avoids an XML dependency.
        locations = [
            item.split("</loc>", 1)[0]
            for item in xml.split("<loc>")[1:]
        ]
        for location in locations:
            path = urlsplit(location).path
            with self.subTest(path=path):
                direct = self.client.get(path)
                self.assertEqual(direct.status_code, 200)
                if direct.headers.get("Location"):
                    self.fail(f"Sitemap URL redirected: {path}")

    def test_robots_separates_search_and_training_crawlers(self):
        response = self.client.get(reverse("robots_txt"))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn("User-agent: OAI-SearchBot\n", body)
        self.assertIn("User-agent: PerplexityBot\n", body)
        self.assertIn("User-agent: GPTBot\n", body)
        self.assertIn("User-agent: Google-Extended\n", body)
        self.assertIn("Sitemap: https://www.zadconcept.ir/sitemap.xml", body)
        self.assertIn("Disallow: /admin/", body)

    def test_faq_schema_uses_the_same_visible_persian_source(self):
        response = self.client.get(reverse("faq"))
        parser = parse_html(response)
        graph = graph_for(response)
        faq_nodes = [node for node in graph if node.get("@type") == "FAQPage"]
        business = next(
            node
            for node in graph
            if node.get("@id") == "https://www.zadconcept.ir/#business"
        )

        self.assertEqual(len(faq_nodes), 1)
        self.assertEqual(len(faq_nodes[0]["mainEntity"]), 12)
        for entity in faq_nodes[0]["mainEntity"]:
            self.assertIn(entity["name"].casefold(), parser.visible_text)
            self.assertIn(
                entity["acceptedAnswer"]["text"].casefold(),
                parser.visible_text,
            )
        self.assertIn("Florist", business["@type"])
        self.assertEqual(business["url"], "https://www.zadconcept.ir")
        self.assertEqual(business["logo"]["width"], 512)
        self.assertNotContains(response, "https://zad.ir")

    def test_hidden_faq_and_breadcrumb_schema_are_not_emitted(self):
        for route in ("index", "flowers", "contact", "mashhad_flower_order"):
            with self.subTest(route=route):
                graph = graph_for(self.client.get(reverse(route)))
                types = [node.get("@type") for node in graph]
                self.assertNotIn("FAQPage", types)
                self.assertNotIn("BreadcrumbList", types)

    def test_blog_and_wedding_collection_keep_view_owned_schema_contracts(self):
        post = NewsPost.objects.create(
            title="ZAD schema contract article",
            slug="zad-schema-contract-article",
            excerpt="A focused article schema contract.",
            body="Article body for the view-owned schema contract.",
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now().replace(microsecond=0),
        )

        blog_response = self.client.get(post.get_absolute_url())
        blog_canonical = f"{settings.ZAD_SITE_URL}{post.get_absolute_url()}"
        article_nodes = [
            node
            for node in blog_response.context["structured_data_graph"]
            if node.get("@type") == "Article"
        ]

        self.assertEqual(blog_response.status_code, 200)
        self.assertEqual(blog_response.context["canonical_url"], blog_canonical)
        self.assertEqual(blog_response.context["robots_content"], "index,follow")
        self.assertEqual(blog_response.context["og_type"], "article")
        self.assertEqual(len(article_nodes), 1)
        article = article_nodes[0]
        self.assertEqual(article["headline"], post.title)
        self.assertEqual(article["url"], blog_canonical)
        self.assertEqual(article["datePublished"], post.published_at.isoformat())
        self.assertEqual(
            article["mainEntityOfPage"],
            {"@id": f"{blog_canonical}#webpage"},
        )

        collection_url = reverse(
            "wedding_collection",
            args=["proposal-bouquets"],
        )
        collection_response = self.client.get(collection_url)
        collection_canonical = f"{settings.ZAD_SITE_URL}{collection_url}"
        page_nodes = [
            node
            for node in collection_response.context["structured_data_graph"]
            if node.get("@id") == f"{collection_canonical}#webpage"
        ]

        self.assertEqual(collection_response.status_code, 200)
        self.assertEqual(
            collection_response.context["canonical_url"],
            collection_canonical,
        )
        self.assertEqual(len(page_nodes), 1)
        self.assertEqual(page_nodes[0]["@type"], "CollectionPage")

    def test_international_pages_are_real_language_variants(self):
        fa_response = self.client.get(reverse("international_orders"))
        en_response = self.client.get(reverse("international_orders_en"))
        fa_parser = parse_html(fa_response)
        en_parser = parse_html(en_response)

        self.assertEqual(fa_parser.html_lang, "fa")
        self.assertEqual(en_parser.html_lang, "en")
        for parser in (fa_parser, en_parser):
            self.assertEqual(set(parser.alternate_links), {"fa", "en", "x-default"})
            self.assertEqual(parser.h1_count, 1)
        en_graph = graph_for(en_response)
        page = next(node for node in en_graph if str(node.get("@id", "")).endswith("#webpage"))
        self.assertEqual(page["inLanguage"], "en")
        self.assertTrue(any(node.get("@type") == "FAQPage" for node in en_graph))

    def test_trust_pages_have_unique_indexable_contracts(self):
        routes = (
            "privacy",
            "terms",
            "delivery_policy",
            "refund_policy",
            "payment_methods",
            "service_area",
        )
        titles = set()
        for route in routes:
            response = self.client.get(reverse(route))
            parser = parse_html(response)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(parser.robots, "index,follow")
            self.assertEqual(parser.h1_count, 1)
            self.assertTrue(parser.description)
            self.assertTrue(parser.og_image_width)
            self.assertTrue(parser.og_image_height)
            titles.add(parser.title)
        self.assertEqual(len(titles), len(routes))

    def test_past_event_is_archived_with_completed_schema_but_not_sitemap(self):
        response = self.client.get(self.past_event.get_absolute_url())
        graph = graph_for(response)
        event = next(node for node in graph if node.get("@type") == "Event")
        self.assertEqual(event["eventStatus"], "https://schema.org/EventCompleted")
        sitemap = self.client.get(reverse("sitemap")).content.decode()
        self.assertNotIn(self.past_event.get_absolute_url(), sitemap)
        self.assertIn(self.future_event.get_absolute_url(), sitemap)

    @override_settings(
        GOOGLE_TAG_ID="G-ABC123",
        GOOGLE_SITE_VERIFICATION="google-token",
        BING_SITE_VERIFICATION="bing-token",
    )
    def test_measurement_and_search_verification_can_be_activated(self):
        response = self.client.get(reverse("index"))
        self.assertContains(response, "googletagmanager.com/gtag/js?id=G-ABC123")
        self.assertContains(response, 'google-site-verification" content="google-token')
        self.assertContains(response, 'msvalidate.01" content="bing-token')

    @override_settings(GOOGLE_TAG_ID="</script><script>alert(1)</script>")
    def test_invalid_measurement_id_is_not_rendered(self):
        response = self.client.get(reverse("index"))
        self.assertNotContains(response, "googletagmanager.com/gtag/js")
        self.assertNotContains(response, "alert(1)")

    @override_settings(INDEXNOW_KEY="Abcd1234-key")
    def test_indexnow_key_file_is_exact_and_non_indexable(self):
        url = reverse("indexnow_key", args=["Abcd1234-key"])
        response = self.client.get(url)
        self.assertEqual(response.content.decode(), "Abcd1234-key")
        self.assertEqual(response.headers["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(
            self.client.get(reverse("indexnow_key", args=["wrong-key"])).status_code,
            404,
        )

    def test_indexnow_dry_run_uses_canonical_public_urls(self):
        output = StringIO()
        call_command("submit_indexnow", dry_run=True, stdout=output)
        self.assertIn(
            f"https://www.zadconcept.ir{self.unnamed.get_absolute_url()}",
            output.getvalue(),
        )

    def test_lead_honeypot_and_rate_limit(self):
        payload = {
            "full_name": "Bot",
            "mobile": "09121234567",
            "lead_type": LeadRequest.LeadType.FLOWER,
            "delivery_window": LeadRequest.DeliveryWindow.TODAY,
            "next": reverse("contact"),
            "source_page": reverse("contact"),
            "website": "https://spam.invalid",
        }
        self.client.post(reverse("lead_request"), payload)
        self.assertEqual(LeadRequest.objects.count(), 0)

        cache.clear()
        payload["website"] = ""
        with override_settings(LEAD_RATE_LIMIT_COUNT=1, LEAD_RATE_LIMIT_WINDOW=300):
            self.client.post(reverse("lead_request"), payload)
            payload["full_name"] = "Second attempt"
            self.client.post(reverse("lead_request"), payload)
        self.assertEqual(LeadRequest.objects.count(), 1)

    def test_csp_report_endpoint_accepts_json_without_csrf(self):
        response = self.client.post(
            reverse("csp_report"),
            data=json.dumps(
                {
                    "csp-report": {
                        "document-uri": "https://www.zadconcept.ir/",
                        "violated-directive": "script-src",
                        "blocked-uri": "inline",
                    }
                }
            ),
            content_type="application/csp-report",
        )
        self.assertEqual(response.status_code, 204)

    def test_semantic_main_and_modal_accessibility_do_not_change_layout(self):
        about = self.client.get(reverse("about"))
        catalog = self.client.get(reverse("bakery"))

        self.assertEqual(catalog.content.decode().count("<main"), 1)
        self.assertNotContains(about, "product-dialog.css")
        self.assertContains(catalog, "product-dialog.css")
        self.assertContains(catalog, 'aria-label="بستن پنجره محصول"')
        self.assertContains(catalog, 'aria-labelledby="zad-product-modal-title"')

    def test_rendered_public_pages_reserve_image_dimensions(self):
        for route in ("index", "flowers", "events", "about", "faq"):
            with self.subTest(route=route):
                parser = parse_html(self.client.get(reverse(route)))
                self.assertEqual(parser.images_missing_dimensions, [])
                self.assertEqual(parser.images_missing_alt, [])

    def test_full_seo_audit_is_a_ci_safe_gate(self):
        output = StringIO()
        call_command("audit_seo", fail_on_error=True, stdout=output)
        self.assertIn("SEO audit passed", output.getvalue())

    def test_product_tag_changes_touch_product_for_incremental_submission(self):
        previous_updated_at = self.fixed.updated_at
        self.fixed.tags.add(self.birthday)
        self.fixed.refresh_from_db()
        self.assertGreater(self.fixed.updated_at, previous_updated_at)


    def test_security_headers_and_edge_rate_limit_are_hardened(self):
        from django.conf import settings

        self.assertEqual(settings.X_FRAME_OPTIONS, "DENY")
        self.assertEqual(settings.SECURE_REFERRER_POLICY, "strict-origin-when-cross-origin")
        self.assertTrue(settings.SECURE_CONTENT_TYPE_NOSNIFF)
        nginx = (
            Path(settings.BASE_DIR) / "deploy" / "nginx" / "zadconcept.conf"
        ).read_text(encoding="utf-8")
        self.assertIn("limit_req_zone", nginx)
        self.assertIn("location = /lead-request/", nginx)
        self.assertIn("limit_req zone=zad_lead", nginx)

    def test_not_found_page_is_not_indexable(self):
        response = self.client.get("/not-a-real-public-page/")
        self.assertEqual(response.status_code, 404)
        self.assertEqual(parse_html(response).robots, "noindex,nofollow")
