import json
import logging
import re
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from main.models import (
    Category,
    Event,
    NewsPost,
    Product,
    PublishStatus,
    Tag,
    WeddingPageContent,
)
from main.sitemaps import sitemaps


logger = logging.getLogger("main.indexnow")
INDEXNOW_KEY_PATTERN = re.compile(r"^[A-Za-z0-9-]{8,128}$")


def all_public_urls():
    urls = set()
    for sitemap_class in sitemaps.values():
        sitemap = sitemap_class()
        for page_number in range(1, sitemap.paginator.num_pages + 1):
            urls.update(
                item["location"]
                for item in sitemap.get_urls(page=page_number)
            )
    return urls


def changed_public_urls(since):
    urls = set()
    wedding_catalog_changed = Product.objects.for_weddings().filter(
        updated_at__gte=since,
    ).exists()

    products = Product.objects.publicly_indexable().filter(
        updated_at__gte=since,
    ).select_related("category")
    urls.update(f"{settings.ZAD_SITE_URL}{item.get_absolute_url()}" for item in products)

    categories = (
        Category.objects.for_general_catalog().filter(
            is_active=True,
            section__in=(
                Category.Section.FLOWERS,
                Category.Section.BAKERY,
                Category.Section.GIFTS,
            ),
            updated_at__gte=since,
        )
    )
    urls.update(f"{settings.ZAD_SITE_URL}{item.get_absolute_url()}" for item in categories)

    occasions = Tag.objects.for_general_catalog().filter(
        is_active=True,
        is_occasion=True,
        updated_at__gte=since,
    )
    urls.update(f"{settings.ZAD_SITE_URL}{item.get_absolute_url()}" for item in occasions)

    events = Event.objects.filter(
        status=PublishStatus.PUBLISHED,
        updated_at__gte=since,
    )
    urls.update(f"{settings.ZAD_SITE_URL}{item.get_absolute_url()}" for item in events)

    posts = NewsPost.objects.filter(
        status=PublishStatus.PUBLISHED,
        updated_at__gte=since,
    )
    urls.update(f"{settings.ZAD_SITE_URL}{item.get_absolute_url()}" for item in posts)

    wedding_content = WeddingPageContent.current()
    if wedding_catalog_changed or (
        wedding_content and wedding_content.updated_at >= since
    ):
        urls.add(f"{settings.ZAD_SITE_URL}{reverse('weddings')}")

    return urls


class Command(BaseCommand):
    help = "Submit added, changed, and removed public URLs to IndexNow."

    def add_arguments(self, parser):
        parser.add_argument("--all", action="store_true", help="Submit every public URL.")
        parser.add_argument("--since", help="ISO-8601 timestamp overriding saved state.")
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=1000)

    def handle(self, *args, **options):
        key = settings.INDEXNOW_KEY
        dry_run = options["dry_run"]
        if not dry_run and not INDEXNOW_KEY_PATTERN.fullmatch(key or ""):
            raise CommandError("INDEXNOW_KEY must contain 8-128 letters, numbers, or dashes.")

        endpoint = urlsplit(settings.INDEXNOW_ENDPOINT)
        if endpoint.scheme != "https" or not endpoint.netloc:
            raise CommandError("INDEXNOW_ENDPOINT must be an HTTPS URL.")

        batch_size = options["batch_size"]
        if batch_size < 1 or batch_size > 10000:
            raise CommandError("--batch-size must be between 1 and 10000.")

        state_path = Path(settings.INDEXNOW_STATE_FILE)
        state = self.read_state(state_path)
        current_urls = all_public_urls()
        previous_urls = set(state.get("known_urls", []))
        removed_urls = previous_urls - current_urls

        since = self.resolve_since(options.get("since"), state)
        if options["all"] or since is None:
            candidates = set(current_urls)
        else:
            candidates = changed_public_urls(since)
        candidates.update(removed_urls)
        canonical_origin = urlsplit(settings.ZAD_SITE_URL)
        candidates = sorted(
            url
            for url in candidates
            if urlsplit(url).scheme == canonical_origin.scheme
            and urlsplit(url).netloc == canonical_origin.netloc
        )

        if not candidates:
            self.stdout.write(self.style.SUCCESS("IndexNow: no changed URLs."))
            return

        self.stdout.write(f"IndexNow candidates: {len(candidates)}")
        if dry_run:
            for url in candidates:
                self.stdout.write(url)
            return

        submitted_at = timezone.now()
        for start in range(0, len(candidates), batch_size):
            batch = candidates[start : start + batch_size]
            self.submit_batch(batch, key)

        self.write_state(
            state_path,
            {
                "last_success_at": submitted_at.isoformat(),
                "known_urls": sorted(current_urls),
            },
        )
        self.stdout.write(
            self.style.SUCCESS(f"IndexNow accepted {len(candidates)} URL(s).")
        )

    def resolve_since(self, option, state):
        raw = option or state.get("last_success_at")
        if not raw:
            return None
        parsed = parse_datetime(raw)
        if parsed is None:
            raise CommandError("--since/state timestamp must be valid ISO-8601.")
        if timezone.is_naive(parsed):
            parsed = timezone.make_aware(parsed, timezone.get_current_timezone())
        return parsed

    def submit_batch(self, urls, key):
        host = urlsplit(settings.ZAD_SITE_URL).netloc
        key_location = f"{settings.ZAD_SITE_URL}/{key}.txt"
        payload = json.dumps(
            {
                "host": host,
                "key": key,
                "keyLocation": key_location,
                "urlList": urls,
            }
        ).encode("utf-8")
        request = Request(
            settings.INDEXNOW_ENDPOINT,
            data=payload,
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "User-Agent": "ZAD-IndexNow/1.1.2",
            },
            method="POST",
        )

        try:
            with urlopen(request, timeout=15) as response:
                status = response.status
        except HTTPError as exc:
            logger.error("IndexNow HTTP error: %s", exc.code)
            raise CommandError(f"IndexNow returned HTTP {exc.code}.") from exc
        except (URLError, TimeoutError) as exc:
            logger.error("IndexNow network error: %s", exc)
            raise CommandError("IndexNow request failed.") from exc

        if status not in {200, 202}:
            raise CommandError(f"IndexNow returned unexpected HTTP {status}.")

    @staticmethod
    def read_state(path):
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise CommandError(f"Cannot read IndexNow state: {path}") from exc
        return payload if isinstance(payload, dict) else {}

    @staticmethod
    def write_state(path, state):
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = path.with_suffix(f"{path.suffix}.tmp")
        temporary_path.write_text(
            json.dumps(state, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(path)
