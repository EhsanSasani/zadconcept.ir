"""Import drafts; optionally refresh drafts proven unchanged against a prior pack."""
import json
from pathlib import Path

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from main.models import ArticleBlock, ArticleLink, NewsPost, PublishStatus


class Command(BaseCommand):
    help = "ورود پیش‌نویس‌ها؛ به‌روزرسانی پیش‌نویس دست‌نخورده فقط با --update-from"

    def add_arguments(self, parser):
        parser.add_argument("--source", type=Path, default=Path(settings.BASE_DIR) / "main/content/editorial_launch.json")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--update-from", type=Path, help="Update only unchanged drafts matching this previous source file.")

    @transaction.atomic
    def handle(self, *args, **options):
        try:
            entries = json.loads(options["source"].read_text(encoding="utf-8"))
            previous = {}
            if options.get("update_from"):
                previous = {entry["slug"]: entry for entry in json.loads(options["update_from"].read_text(encoding="utf-8"))}
            if not isinstance(entries, list) or not entries:
                raise ValueError("Source must be a nonempty list.")
            slugs = [entry["slug"] for entry in entries]
            if len(set(slugs)) != len(slugs):
                raise ValueError("Duplicate article slug.")
            existing = set(NewsPost.objects.values_list("slug", flat=True))
            known = existing | set(slugs)
            created = {}
            updated = 0
            for entry in entries:
                post = None
                if entry["slug"] in existing:
                    candidate = NewsPost.objects.get(slug=entry["slug"])
                    baseline = previous.get(entry["slug"])
                    if not baseline or not self.matches_unchanged_draft(candidate, baseline):
                        self.stdout.write(f"SKIP {entry['slug']} (existing content preserved)")
                        continue
                    post = candidate
                fields = {key: entry.get(key, "") for key in (
                    "slug", "title", "seo_title", "meta_description", "excerpt",
                    "takeaway", "topic", "author_name",
                )}
                if post is None:
                    post = NewsPost(**fields, status=PublishStatus.DRAFT)
                else:
                    for key, value in fields.items():
                        setattr(post, key, value)
                    post.blocks.all().delete()
                    post.editorial_links.all().delete()
                    updated += 1
                post.full_clean()
                if not entry.get("blocks"):
                    raise ValueError(f"{post.slug}: no content blocks")
                if set(entry.get("related_slugs", [])) - known:
                    raise ValueError(f"{post.slug}: unknown related article")
                post.save()
                for order, block_data in enumerate(entry["blocks"]):
                    allowed = {"kind", "title", "body", "alt_text", "caption", "table_data", "link_label", "link_url"}
                    if set(block_data) - allowed:
                        raise ValueError(f"{post.slug}: unsupported block fields")
                    block = ArticleBlock(post=post, sort_order=order, **block_data)
                    block.full_clean()
                    block.save()
                for order, link_data in enumerate(entry.get("links", [])):
                    if set(link_data) - {"label", "url", "description"}:
                        raise ValueError(f"{post.slug}: unsupported link fields")
                    link = ArticleLink(post=post, sort_order=order, **link_data)
                    link.full_clean()
                    link.save()
                created[post.slug] = post
                self.stdout.write(f"DRAFT {post.slug}")
            for entry in entries:
                if entry["slug"] in created:
                    created[entry["slug"]].related_articles.set(
                        NewsPost.objects.filter(slug__in=entry.get("related_slugs", []))
                    )
            if options["dry_run"]:
                transaction.set_rollback(True)
            self.stdout.write(self.style.SUCCESS(
                f"{'DRY RUN: ' if options['dry_run'] else ''}{len(created) - updated} new drafts; {updated} unchanged drafts updated; {len(entries) - len(created)} preserved."
            ))
        except (OSError, ValueError, TypeError, KeyError, ValidationError) as exc:
            raise CommandError(f"Import rolled back: {exc}") from exc

    @staticmethod
    def matches_unchanged_draft(post, baseline):
        if post.status != PublishStatus.DRAFT or post.body.strip():
            return False
        fields = ("slug", "title", "seo_title", "meta_description", "excerpt", "takeaway", "topic", "author_name")
        if any(getattr(post, key) != baseline.get(key, "") for key in fields):
            return False
        blocks = list(post.blocks.all())
        if len(blocks) != len(baseline.get("blocks", [])):
            return False
        for block, source in zip(blocks, baseline["blocks"]):
            if block.image:
                return False
            for key in ("kind", "title", "body", "alt_text", "caption", "table_data", "link_label", "link_url"):
                if getattr(block, key) != source.get(key, [] if key == "table_data" else ""):
                    return False
        links = list(post.editorial_links.all())
        if len(links) != len(baseline.get("links", [])):
            return False
        for link, source in zip(links, baseline.get("links", [])):
            if any(getattr(link, key) != source.get(key, "") for key in ("label", "url", "description")):
                return False
        return set(post.related_articles.values_list("slug", flat=True)) == set(baseline.get("related_slugs", []))
