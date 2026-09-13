from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from django.apps import apps
from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction
from django.db.models import F, Max

from main.models import NewsPost


@dataclass(frozen=True)
class EditorialImageSpec:
    slug: str
    cover: str
    after_heading: str
    inline: str
    alt_text: str


SPECS = (
    EditorialImageSpec(
        "box-vs-bouquet",
        "box-vs-bouquet-cover.webp",
        "اگر گل باید همان‌جا بماند",
        "box-vs-bouquet-inline-home-table.webp",
        "باکس گل در یک فضای واقعی خانه روی میز قرار گرفته است.",
    ),
    EditorialImageSpec(
        "birthday-flower-guide",
        "birthday-flower-guide-cover.webp",
        "سه موقعیت، سه انتخاب قابل بررسی",
        "birthday-flower-guide-inline-workplace.webp",
        "گل تولد با رنگ‌های روشن روی میز کار در نور روز.",
    ),
    EditorialImageSpec(
        "flower-price-factors",
        "flower-price-factors-cover.webp",
        "۲. ظرف و بسته‌بندی را از تزئینات اضافی حساب نکنید",
        "flower-price-factors-inline-materials.webp",
        "گل‌های شاخه‌ای، ظرف، کاغذ و روبان در کنار گل‌آرایی آماده.",
    ),
    EditorialImageSpec(
        "ready-or-custom-flowers",
        "ready-or-custom-flowers-cover.webp",
        "اگر گزینه اول نشد، انتخاب را از صفر شروع نکنید",
        "ready-or-custom-flowers-inline-two-paths.webp",
        "یک دسته‌گل آماده کنار چیدمانی که در کارگاه در حال آماده‌شدن است.",
    ),
    EditorialImageSpec(
        "flower-color-guide",
        "flower-color-guide-cover.webp",
        "ظرف و محیط را هم وارد انتخاب کنید",
        "flower-color-guide-inline-room-and-vessel.webp",
        "گل‌آرایی با رنگ‌های ملایم در کنار ظرف و فضای داخلی هماهنگ.",
    ),
    EditorialImageSpec(
        "order-flowers-for-mashhad",
        "order-flowers-for-mashhad-cover.webp",
        "پیام را این‌طور جمع کنید",
        "order-flowers-for-mashhad-inline-clear-message.webp",
        "دسته‌گل آماده، کارت خالی و تلفن با صفحه خاموش برای هماهنگی سفارش.",
    ),
    EditorialImageSpec(
        "reading-a-flower-arrangement",
        "reading-a-flower-arrangement-cover.webp",
        "بار سوم، نقطه‌ای را پیدا کنید که نگاهتان آنجا می‌ایستد",
        "reading-a-flower-arrangement-inline-focal-point.webp",
        "جزئیات نقطه کانونی و خطوط آزاد یک گل‌آرایی نامتقارن.",
    ),
    EditorialImageSpec(
        "cut-flower-care",
        "cut-flower-care-cover.webp",
        "آب را به یک کار کوچکِ تکرارشونده تبدیل کنید",
        "cut-flower-care-inline-refresh-water.webp",
        "تعویض آب و قرار دادن گل‌های شاخه‌بریده در گلدان شیشه‌ای تمیز.",
    ),
)

PREFERRED_IMAGE_FIELDS = ("image", "image_file", "photo", "media")
PREFERRED_ALT_FIELDS = ("alt_text", "image_alt", "alt", "image_alt_text")
PREFERRED_TYPE_FIELDS = ("block_type", "type", "kind", "content_type")
PREFERRED_ORDER_FIELDS = ("sort_order", "order", "ordering", "position")
PREFERRED_ANCHOR_FIELDS = (
    "after_heading",
    "anchor_text",
    "anchor",
    "placement_after",
    "insert_after",
)
TEXT_FIELD_HINTS = (
    "title",
    "heading",
    "text",
    "body",
    "content",
    "paragraph",
    "value",
)


def _norm(value: object) -> str:
    return " ".join(str(value or "").replace("\u200c", " ").split()).casefold()


def _pick(fields: Iterable[models.Field], preferred: tuple[str, ...]):
    by_name = {field.name: field for field in fields}
    for name in preferred:
        if name in by_name:
            return by_name[name]
    return None


@dataclass
class BlockSchema:
    model: type[models.Model]
    post_fk: models.ForeignKey
    image_field: models.ImageField
    alt_field: models.Field | None
    type_field: models.Field | None
    image_type_value: object | None
    order_field: models.Field | None
    anchor_field: models.Field | None
    searchable_fields: tuple[models.Field, ...]


class Command(BaseCommand):
    help = (
        "Install the ZAD editorial image pack for the eight curated NewsPost slugs. "
        "Safe to run repeatedly."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Validate posts, assets and block placement without writing files or DB rows.",
        )
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Fail instead of skipping when a post or inline-image block schema is unavailable.",
        )

    def handle(self, *args, **options):
        self.dry_run = bool(options["dry_run"])
        self.strict = bool(options["strict"])
        asset_root = Path(__file__).resolve().parents[2] / "editorial_assets" / "news"

        missing_assets = [
            filename
            for spec in SPECS
            for filename in (spec.cover, spec.inline)
            if not (asset_root / filename).is_file()
        ]
        if missing_assets:
            raise CommandError(
                "Editorial asset(s) missing: " + ", ".join(sorted(set(missing_assets)))
            )

        posts = {post.slug: post for post in NewsPost.objects.filter(slug__in=[s.slug for s in SPECS])}
        missing_posts = [spec.slug for spec in SPECS if spec.slug not in posts]
        if missing_posts and self.strict:
            raise CommandError("NewsPost slug(s) missing: " + ", ".join(missing_posts))

        block_schema = self._discover_block_schema()
        if block_schema:
            self.stdout.write(
                self.style.SUCCESS(
                    "Inline block model: "
                    f"{block_schema.model._meta.label} "
                    f"(image={block_schema.image_field.name}, fk={block_schema.post_fk.name})"
                )
            )
        else:
            message = (
                "No image-capable child block model for NewsPost was detected. "
                "Cover images can be installed, but inline images cannot be attached automatically."
            )
            if self.strict:
                raise CommandError(message)
            self.stdout.write(self.style.WARNING(message))

        if missing_posts:
            self.stdout.write(
                self.style.WARNING("Missing posts (skipped): " + ", ".join(missing_posts))
            )

        if self.dry_run:
            for spec in SPECS:
                post = posts.get(spec.slug)
                if not post:
                    continue
                placement = self._preview_inline_placement(post, spec, block_schema)
                if self.strict and placement.startswith("append"):
                    raise CommandError(
                        f"{spec.slug}: exact inline placement could not be resolved for "
                        f"heading «{spec.after_heading}» ({placement})."
                    )
                self.stdout.write(f"[DRY] {spec.slug}: cover=ok; inline={placement}")
            self.stdout.write(self.style.SUCCESS("Dry run completed; nothing was written."))
            return

        with transaction.atomic():
            updated = 0
            inline_updated = 0
            for spec in SPECS:
                post = posts.get(spec.slug)
                if not post:
                    continue

                self._install_cover(post, asset_root / spec.cover)
                updated += 1

                if block_schema:
                    self._install_inline(post, spec, asset_root / spec.inline, block_schema)
                    inline_updated += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Editorial images installed: {updated} cover(s), {inline_updated} inline image(s)."
            )
        )

    def _discover_block_schema(self) -> BlockSchema | None:
        candidates = []
        for model in apps.get_app_config("main").get_models():
            if model is NewsPost:
                continue
            fields = [field for field in model._meta.get_fields() if isinstance(field, models.Field)]
            post_fks = [
                field
                for field in fields
                if isinstance(field, models.ForeignKey)
                and field.remote_field.model is NewsPost
            ]
            image_fields = [field for field in fields if isinstance(field, models.ImageField)]
            if not post_fks or not image_fields:
                continue

            post_fk = _pick(post_fks, ("post", "news_post", "article")) or post_fks[0]
            image_field = _pick(image_fields, PREFERRED_IMAGE_FIELDS) or image_fields[0]
            alt_field = _pick(fields, PREFERRED_ALT_FIELDS)
            type_field = _pick(fields, PREFERRED_TYPE_FIELDS)
            order_field = _pick(fields, PREFERRED_ORDER_FIELDS)
            anchor_field = _pick(fields, PREFERRED_ANCHOR_FIELDS)

            image_type_value = None
            if type_field is not None:
                for choice in getattr(type_field, "choices", ()) or ():
                    value, label = choice[:2]
                    if "image" in _norm(value) or "تصویر" in _norm(label) or "عکس" in _norm(label):
                        image_type_value = value
                        break
                if image_type_value is None and isinstance(type_field, (models.CharField, models.TextField)):
                    image_type_value = "image"

            searchable_fields = tuple(
                field
                for field in fields
                if isinstance(field, (models.CharField, models.TextField))
                and field not in {alt_field, type_field, anchor_field}
                and any(hint in field.name for hint in TEXT_FIELD_HINTS)
            )

            score = 0
            score += 5 if post_fk.name in {"post", "news_post", "article"} else 0
            score += 5 if image_field.name in PREFERRED_IMAGE_FIELDS else 0
            score += 3 if alt_field else 0
            score += 3 if order_field else 0
            score += 3 if anchor_field else 0
            score += 2 if type_field and image_type_value is not None else 0
            score += 2 if searchable_fields else 0
            if "block" in model.__name__.casefold():
                score += 5

            candidates.append(
                (
                    score,
                    BlockSchema(
                        model=model,
                        post_fk=post_fk,
                        image_field=image_field,
                        alt_field=alt_field,
                        type_field=type_field,
                        image_type_value=image_type_value,
                        order_field=order_field,
                        anchor_field=anchor_field,
                        searchable_fields=searchable_fields,
                    ),
                )
            )

        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _preview_inline_placement(
        self,
        post: NewsPost,
        spec: EditorialImageSpec,
        schema: BlockSchema | None,
    ) -> str:
        if schema is None:
            return "unavailable"
        queryset = schema.model._default_manager.filter(**{schema.post_fk.name: post})
        if schema.anchor_field:
            return f"anchor-field:{schema.anchor_field.name}"
        anchor = self._find_anchor_block(queryset, spec.after_heading, schema)
        if anchor is not None:
            return f"after-block:{anchor.pk}"
        if _norm(spec.after_heading) in _norm(getattr(post, "body", "")):
            return "heading-found-in-post-body; append-to-block-list"
        return "append; heading-not-found-in-blocks"

    def _install_cover(self, post: NewsPost, source: Path) -> None:
        expected_suffix = f"news-{post.slug}.webp"
        current_name = post.cover_image.name if post.cover_image else ""
        if current_name.endswith(expected_suffix):
            self.stdout.write(f"[OK] {post.slug}: cover already installed")
            return

        payload = source.read_bytes()
        post.cover_image.save(source.name, ContentFile(payload), save=False)
        post.save(update_fields=["cover_image"])
        self.stdout.write(f"[SET] {post.slug}: cover")

    def _find_anchor_block(self, queryset, heading: str, schema: BlockSchema):
        needle = _norm(heading)
        if not needle or not schema.searchable_fields:
            return None
        rows = queryset
        if schema.order_field:
            rows = rows.order_by(schema.order_field.name, "pk")
        else:
            rows = rows.order_by("pk")
        for row in rows:
            haystack = " ".join(_norm(getattr(row, field.name, "")) for field in schema.searchable_fields)
            if needle in haystack:
                return row
        return None

    def _existing_inline_block(self, queryset, spec: EditorialImageSpec, schema: BlockSchema):
        for row in queryset:
            image = getattr(row, schema.image_field.name, None)
            image_name = getattr(image, "name", "") or ""
            if image_name.endswith(spec.inline):
                return row
            if schema.alt_field and _norm(getattr(row, schema.alt_field.name, "")) == _norm(spec.alt_text):
                return row
        return None

    def _install_inline(
        self,
        post: NewsPost,
        spec: EditorialImageSpec,
        source: Path,
        schema: BlockSchema,
    ) -> None:
        queryset = schema.model._default_manager.filter(**{schema.post_fk.name: post})
        row = self._existing_inline_block(queryset, spec, schema)
        creating = row is None
        if row is None:
            row = schema.model()
            setattr(row, schema.post_fk.name, post)

        if schema.type_field is not None and schema.image_type_value is not None:
            setattr(row, schema.type_field.name, schema.image_type_value)
        if schema.alt_field is not None:
            setattr(row, schema.alt_field.name, spec.alt_text)
        if schema.anchor_field is not None:
            setattr(row, schema.anchor_field.name, spec.after_heading)

        if creating and schema.order_field is not None:
            anchor = self._find_anchor_block(queryset, spec.after_heading, schema)
            if anchor is not None:
                anchor_order = getattr(anchor, schema.order_field.name)
                insertion_order = anchor_order + 1
                queryset.filter(**{f"{schema.order_field.name}__gte": insertion_order}).update(
                    **{schema.order_field.name: F(schema.order_field.name) + 1}
                )
            else:
                maximum = queryset.aggregate(value=Max(schema.order_field.name))["value"]
                insertion_order = (maximum if maximum is not None else -1) + 1
            setattr(row, schema.order_field.name, insertion_order)

        # Supply harmless values for uncommon required scalar fields. Most block
        # implementations already use defaults/blank=True; this keeps the installer
        # tolerant of small schema variations without touching unrelated relations.
        for field in row._meta.concrete_fields:
            if field.primary_key or field.name in {
                schema.post_fk.name,
                schema.image_field.name,
                getattr(schema.alt_field, "name", None),
                getattr(schema.type_field, "name", None),
                getattr(schema.order_field, "name", None),
                getattr(schema.anchor_field, "name", None),
            }:
                continue
            if getattr(row, field.attname, None) not in (None, ""):
                continue
            if field.has_default() or field.null or field.blank or isinstance(field, models.AutoField):
                continue
            if isinstance(field, (models.CharField, models.TextField)):
                setattr(row, field.name, "")
            elif isinstance(field, models.BooleanField):
                setattr(row, field.name, False)
            elif isinstance(field, models.IntegerField):
                setattr(row, field.name, 0)

        payload = source.read_bytes()
        image = getattr(row, schema.image_field.name)
        current_name = getattr(image, "name", "") or ""
        if not current_name.endswith(spec.inline):
            image.save(spec.inline, ContentFile(payload), save=False)
        row.save()
        action = "ADD" if creating else "OK"
        self.stdout.write(f"[{action}] {post.slug}: inline after «{spec.after_heading}»")
