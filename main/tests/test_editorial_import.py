import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from main.models import ArticleProduct, Category, NewsPost, Product, PublishStatus
from main.editorial_links import guides_for_category, guides_for_product
from main.sitemaps import BlogSitemap
from django.utils import timezone
from datetime import timedelta


class EditorialImportTests(TestCase):
    def test_launch_pack_is_draft_idempotent_and_preserves_editor_changes(self):
        call_command("seed_editorial", stdout=StringIO())
        self.assertEqual(NewsPost.objects.count(), 8)
        self.assertFalse(NewsPost.objects.exclude(status=PublishStatus.DRAFT).exists())
        post = NewsPost.objects.get(slug="box-vs-bouquet")
        self.assertGreater(post.blocks.count(), 5)
        self.assertTrue(post.related_articles.exists())
        post.title = "ویرایش واقعی مدیر"
        post.save()
        call_command("seed_editorial", stdout=StringIO())
        post.refresh_from_db()
        self.assertEqual(post.title, "ویرایش واقعی مدیر")
        self.assertEqual(NewsPost.objects.count(), 8)

    def test_dry_run_writes_nothing(self):
        call_command("seed_editorial", dry_run=True, stdout=StringIO())
        self.assertFalse(NewsPost.objects.exists())

    def test_update_from_preserves_edits_and_published_articles(self):
        source = Path(__file__).resolve().parents[1] / "content/editorial_launch.json"
        entries = json.loads(source.read_text(encoding="utf-8"))
        call_command("seed_editorial", stdout=StringIO())
        edited = NewsPost.objects.get(slug=entries[1]["slug"])
        edited.title = "ویرایش مدیر"
        edited.save()
        published = NewsPost.objects.get(slug=entries[2]["slug"])
        published.status = PublishStatus.PUBLISHED
        published.save()
        for entry in entries:
            entry["title"] += " تازه"
        with TemporaryDirectory() as folder:
            revised = Path(folder) / "revised.json"
            revised.write_text(json.dumps(entries), encoding="utf-8")
            call_command("seed_editorial", source=revised, update_from=source, dry_run=True, stdout=StringIO())
            self.assertNotEqual(NewsPost.objects.get(slug=entries[0]["slug"]).title, entries[0]["title"])
            call_command("seed_editorial", source=revised, update_from=source, stdout=StringIO())
        self.assertEqual(NewsPost.objects.get(slug=entries[0]["slug"]).title, entries[0]["title"])
        edited.refresh_from_db()
        published.refresh_from_db()
        self.assertEqual(edited.title, "ویرایش مدیر")
        self.assertNotEqual(published.title, entries[2]["title"])

    def test_invalid_second_article_rolls_back_entire_import(self):
        good = dict(slug="good", title="عنوان", topic="selection", blocks=[dict(kind="text", body="متن")])
        bad = dict(slug="bad", title="عنوان دوم", topic="selection", blocks=[dict(kind="cta", link_label="خطر", link_url="javascript:alert(1)")])
        with TemporaryDirectory() as folder:
            source = Path(folder) / "invalid.json"
            source.write_text(json.dumps([good, bad]), encoding="utf-8")
            with self.assertRaises(CommandError):
                call_command("seed_editorial", source=source, stdout=StringIO())
        self.assertFalse(NewsPost.objects.exists())

    def test_future_articles_are_not_in_sitemap(self):
        NewsPost.objects.create(title="آینده", status=PublishStatus.PUBLISHED, published_at=timezone.now() + timedelta(days=1))
        visible = NewsPost.objects.create(title="قدیمی", status=PublishStatus.PUBLISHED)
        self.assertEqual(list(BlogSitemap().items()), [visible])

    def test_product_backlinks_are_curated_and_never_expose_drafts(self):
        category = Category.objects.create(name="گل", slug="editorial-test", section="flowers")
        product = Product.objects.create(name="مدل واقعی", category=category)
        visible = NewsPost.objects.create(title="راهنمای منتشرشده", status=PublishStatus.PUBLISHED, primary_category=category)
        draft = NewsPost.objects.create(title="متن محرمانه", primary_category=category)
        ArticleProduct.objects.create(post=visible, product=product, reason="انتخاب مرتبط")
        ArticleProduct.objects.create(post=draft, product=product, reason="پیش‌نویس")
        NewsPost.objects.create(title="مقاله نامرتبط", status=PublishStatus.PUBLISHED)
        self.assertEqual(list(guides_for_product(product)), [visible])
        self.assertEqual(list(guides_for_category(category)), [visible])
