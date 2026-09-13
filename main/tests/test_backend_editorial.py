from datetime import timedelta

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from main.editorial import article_context, public_posts
from main.models import ArticleBlock, ArticleLink, NewsPost, PublishStatus, validate_editorial_url


class EditorialBackendTests(TestCase):
    def setUp(self):
        self.public = NewsPost.objects.create(title="راهنمای گل", slug="public-guide", body="متن قدیمی", status=PublishStatus.PUBLISHED)
        self.draft = NewsPost.objects.create(title="پیش‌نویس", slug="draft-guide")
        self.future = NewsPost.objects.create(title="آینده", slug="future-guide", status=PublishStatus.PUBLISHED, published_at=timezone.now() + timedelta(days=1))

    def test_publication_boundary_and_related_posts(self):
        self.public.related_articles.add(self.draft, self.future)
        self.assertEqual(list(public_posts()), [self.public])
        self.assertEqual(list(article_context(self.public)["related_posts"]), [])
        for post in (self.draft, self.future):
            self.assertEqual(self.client.get(post.get_absolute_url()).status_code, 404)
            self.assertEqual(self.client.get(post.get_absolute_url() + "?preview=1").status_code, 404)

    def test_preview_requires_staff_and_change_permission_and_is_private(self):
        user = get_user_model().objects.create_user(username="editor", password="local-test", is_staff=True)
        self.client.force_login(user)
        self.assertEqual(self.client.get(self.draft.get_absolute_url() + "?preview=1").status_code, 404)
        user.user_permissions.add(Permission.objects.get(codename="change_newspost"))
        response = self.client.get(self.draft.get_absolute_url() + "?preview=1")
        self.assertEqual(response.status_code, 200)
        self.assertIn("private", response["Cache-Control"])
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("noindex", response["X-Robots-Tag"])
        self.assertTrue(response.context["is_preview"])
        self.assertFalse(any(node.get("@type") == "Article" for node in response.context["structured_data_graph"]))
        user.is_staff = False
        user.save()
        self.assertEqual(self.client.get(self.draft.get_absolute_url() + "?preview=1").status_code, 404)

    def test_unsafe_links_rejected_and_not_rendered_even_after_direct_save(self):
        for url in ("javascript:alert(1)", "//evil.test", "/%2fexample.com", "%2f%2fevil.test", "/%252fexample.com", "/%0aevil", "https://[invalid", "/%5cevil", "https://good.test\nevil", "http://example.com", "https://user:pass@example.com"):
            with self.subTest(url=url), self.assertRaises(ValidationError):
                validate_editorial_url(url)
        for url in ("/flowers/box/", "https://example.com/guide#section"):
            validate_editorial_url(url)
        ArticleLink.objects.create(post=self.public, label="unsafe", url="javascript:alert(1)")
        self.assertEqual(article_context(self.public)["related_links"], [])

    def test_blocks_validate_content_and_preserve_escaped_text(self):
        for block in (ArticleBlock(kind="faq", title="?"), ArticleBlock(kind="cta"), ArticleBlock(kind="table", table_data=[["a"], ["b", "c"]]), ArticleBlock(kind="image")):
            with self.subTest(kind=block.kind), self.assertRaises(ValidationError):
                block.clean()
        block = ArticleBlock.objects.create(post=self.public, kind="heading", title="انتخاب")
        context = article_context(self.public)
        self.assertEqual(context["toc"], [{"id": f"section-{block.pk}", "title": "انتخاب"}])
        self.assertEqual(context["recommended_connections"], [])

    def test_topic_pagination_is_filtered_and_deterministic(self):
        for index in range(12):
            NewsPost.objects.create(title=f"Care {index}", slug=f"care-{index}", topic="care", status=PublishStatus.PUBLISHED)
        response = self.client.get("/blog/?topic=care&page=2")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context["paginator"].count, 12)
        self.assertEqual(len(response.context["posts"]), 3)
        self.assertTrue(all(post.topic == "care" for post in response.context["posts"]))
