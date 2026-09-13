"""Read-only editorial readiness audit; never changes publication state."""
from urllib.parse import urlsplit

from django.core.management.base import BaseCommand, CommandError
from django.urls import Resolver404, resolve

from main.models import NewsPost, validate_editorial_url
from django.core.exceptions import ValidationError


class Command(BaseCommand):
    help = "گزارش آمادگی مقاله‌ها، تصاویر و پیوندهای داخلی، بدون تغییر داده"

    def add_arguments(self, parser):
        parser.add_argument("--slug")
        parser.add_argument("--strict", action="store_true")

    def handle(self, *args, **options):
        posts = NewsPost.objects.prefetch_related("blocks", "editorial_links", "product_connections")
        if options["slug"]:
            posts = posts.filter(slug=options["slug"])
        issues = 0
        for post in posts:
            findings = []
            for attr, label in [("seo_title", "عنوان سئو"), ("meta_description", "توضیح سئو"), ("takeaway", "پاسخ کوتاه"), ("cover_image", "تصویر واقعی جلد")]:
                if not getattr(post, attr):
                    findings.append(f"ناقص: {label}")
            if not post.blocks.all() and not post.body.strip():
                findings.append("متن مقاله خالی است")
            if not post.primary_category_id and not post.product_connections.all():
                findings.append("دسته یا محصول مرتبط هنوز انتخاب نشده")
            links = [link.url for link in post.editorial_links.all()]
            links += [block.link_url for block in post.blocks.all() if block.link_url]
            for url in links:
                try:
                    validate_editorial_url(url)
                    if url.startswith("/"):
                        match = resolve(urlsplit(url).path)
                        if match.url_name == "blog_detail" and not NewsPost.objects.filter(slug=match.kwargs["slug"]).exists():
                            findings.append(f"مقاله مقصد وجود ندارد: {url}")
                except (ValidationError, Resolver404, ValueError):
                    findings.append(f"مقصد نامعتبر: {url}")
            issues += len(findings)
            self.stdout.write(f"{post.slug} [{post.status}]")
            for finding in findings:
                self.stdout.write(f"  - {finding}")
        self.stdout.write(f"{issues} مورد برای بررسی؛ قیمت، موجودی و دسترسی واقعی مقصد باید جداگانه تأیید شود.")
        if issues and options["strict"]:
            raise CommandError("Editorial readiness checks need attention.")
