import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils.text import slugify
from PIL import Image, ImageOps

from main.models import (
    Category,
    Event,
    HomeHeroSlide,
    NewsPost,
    Product,
    ProductImage,
    SiteHero,
    Tag,
)


IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp", ".gif", ".avif"}
TEXT_SUFFIXES = {".py", ".html", ".css", ".js", ".json"}
STATIC_IMG_ROOT = Path("main/static/main/img")


@dataclass(frozen=True)
class ImageTarget:
    path: Path
    new_relative_path: str
    model_object: object | None = None
    field_name: str = ""
    is_static: bool = False


def ascii_slug(value, fallback="image"):
    slug = slugify(value or "", allow_unicode=False)
    slug = re.sub(r"[^a-z0-9-]+", "-", slug.lower()).strip("-")
    return slug or fallback


def unique_path(path, used_paths, source=None):
    candidate = path
    index = 2
    source_resolved = source.resolve() if source else None
    while candidate in used_paths or (candidate.exists() and candidate.resolve() != source_resolved):
        candidate = path.with_name(f"{path.stem}-{index}{path.suffix}")
        index += 1
    used_paths.add(candidate)
    return candidate


def has_alpha(image):
    return image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )


def optimize_to_webp(source, destination, quality, lossless, max_dimension):
    destination.parent.mkdir(parents=True, exist_ok=True)
    write_destination = destination

    if source.resolve() == destination.resolve():
        write_destination = destination.with_name(f"{destination.stem}.optimizing{destination.suffix}")

    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)

        if image.width > max_dimension or image.height > max_dimension:
            image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

        if has_alpha(image):
            image = image.convert("RGBA")
            save_kwargs = {
                "format": "WEBP",
                "lossless": True if lossless else False,
                "quality": 90,
                "method": 6,
                "exact": True,
            }
        else:
            image = image.convert("RGB")
            save_kwargs = {
                "format": "WEBP",
                "quality": quality,
                "method": 6,
                "optimize": True,
            }

        image.save(write_destination, **save_kwargs)

    with Image.open(write_destination) as check_image:
        check_image.verify()

    if write_destination != destination:
        write_destination.replace(destination)


def create_width_variant(source, destination, width, quality):
    with Image.open(source) as image:
        image = ImageOps.exif_transpose(image)
        if image.width <= width:
            return False
        height = max(1, round(image.height * (width / image.width)))
        image = image.resize((width, height), Image.Resampling.LANCZOS)
        alpha = has_alpha(image)
        image = image.convert("RGBA" if alpha else "RGB")
        destination.parent.mkdir(parents=True, exist_ok=True)
        save_kwargs = {"format": "WEBP", "method": 6}
        if alpha:
            save_kwargs.update({"lossless": True, "exact": True})
        else:
            save_kwargs.update({"quality": quality, "optimize": True})
        image.save(destination, **save_kwargs)
    return True


class Command(BaseCommand):
    help = "Optimize and standardize media/static image files."

    def add_arguments(self, parser):
        parser.add_argument("--quality", type=int, default=82)
        parser.add_argument("--max-dimension", type=int, default=1920)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--keep-originals", action="store_true")
        parser.add_argument("--skip-static-rewrite", action="store_true")
        parser.add_argument("--skip-responsive", action="store_true")
        parser.add_argument(
            "--media-only",
            action="store_true",
            help="Optimize database/untracked media without touching source static assets.",
        )

    def handle(self, *args, **options):
        self.quality = options["quality"]
        self.max_dimension = options["max_dimension"]
        self.dry_run = options["dry_run"]
        self.keep_originals = options["keep_originals"]
        self.skip_static_rewrite = options["skip_static_rewrite"]
        self.skip_responsive = options["skip_responsive"]
        self.media_only = options["media_only"]
        self.media_root = Path(settings.MEDIA_ROOT)
        self.static_root = Path(settings.BASE_DIR) / STATIC_IMG_ROOT
        self.used_paths = set()
        self.destination_cache = {}
        self.path_replacements = {}

        targets = self.get_database_targets()
        targets.extend(self.get_untracked_media_targets(targets))
        if not self.media_only:
            targets.extend(self.get_static_targets())

        before_size = sum(target.path.stat().st_size for target in targets if target.path.exists())

        changed_count = 0
        skipped_count = 0

        with transaction.atomic():
            for target in targets:
                if not target.path.exists():
                    skipped_count += 1
                    self.stdout.write(self.style.WARNING(f"Missing: {target.path}"))
                    continue

                destination = self.resolve_destination(target)
                old_size = target.path.stat().st_size

                if self.dry_run:
                    self.stdout.write(f"Would optimize: {target.path} -> {destination}")
                    changed_count += 1
                    continue

                optimize_to_webp(
                    target.path,
                    destination,
                    quality=self.quality,
                    lossless=True,
                    max_dimension=self.max_dimension,
                )

                if (
                    not self.skip_responsive
                    and isinstance(target.model_object, (Product, ProductImage))
                ):
                    for width in (520, 1040, 1600):
                        variant = destination.with_name(
                            f"{destination.stem}-{width}w.webp"
                        )
                        create_width_variant(
                            destination,
                            variant,
                            width=width,
                            quality=self.quality,
                        )

                new_size = destination.stat().st_size

                if destination != target.path and not self.keep_originals:
                    target.path.unlink()

                if target.model_object and target.field_name:
                    actual_relative_path = str(
                        destination.relative_to(self.media_root)
                    ).replace("\\", "/")
                    setattr(target.model_object, target.field_name, actual_relative_path)
                    target.model_object.save(update_fields=[target.field_name, "updated_at"])

                if target.is_static:
                    self.path_replacements[self.static_reference(target.path)] = self.static_reference(destination)

                changed_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"{target.path.name} -> {destination.name} | "
                        f"{old_size / 1024:.1f}KB -> {new_size / 1024:.1f}KB"
                    )
                )

            if self.path_replacements and not self.skip_static_rewrite and not self.dry_run:
                self.rewrite_static_references()

        after_paths = [self.resolve_destination(target) for target in targets if self.resolve_destination(target).exists()]
        after_size = sum(path.stat().st_size for path in set(after_paths))

        self.stdout.write(self.style.SUCCESS(f"Optimized: {changed_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped: {skipped_count}"))
        self.stdout.write(
            self.style.SUCCESS(
                f"Total: {before_size / 1024 / 1024:.2f}MB -> {after_size / 1024 / 1024:.2f}MB"
            )
        )

    def get_database_targets(self):
        targets = []

        for product in Product.objects.exclude(cover_image="").filter(cover_image__isnull=False):
            code = ascii_slug(product.product_code or product.slug or product.pk, "product")
            targets.append(self.db_target(product, "cover_image", f"products/covers/product-{code}.webp"))

        for image in ProductImage.objects.exclude(image="").filter(image__isnull=False).select_related("product"):
            code = ascii_slug(image.product.product_code or image.product.slug or image.product_id, "product")
            order = image.ordering or image.pk
            targets.append(
                self.db_target(
                    image,
                    "image",
                    f"products/gallery/product-{code}-gallery-{order}.webp",
                )
            )

        for tag in Tag.objects.exclude(cover_image="").filter(cover_image__isnull=False):
            targets.append(self.db_target(tag, "cover_image", f"tags/tag-{ascii_slug(tag.slug or tag.name, tag.pk)}.webp"))

        for category in Category.objects.exclude(cover_image="").filter(cover_image__isnull=False):
            name = f"{ascii_slug(category.section, 'section')}-{ascii_slug(category.slug or category.name, category.pk)}"
            targets.append(self.db_target(category, "cover_image", f"categories/category-{name}.webp"))

        for event in Event.objects.exclude(cover_image="").filter(cover_image__isnull=False):
            targets.append(self.db_target(event, "cover_image", f"events/covers/event-{ascii_slug(event.slug or event.title, event.pk)}.webp"))

        for post in NewsPost.objects.exclude(cover_image="").filter(cover_image__isnull=False):
            targets.append(self.db_target(post, "cover_image", f"news/covers/news-{ascii_slug(post.slug or post.title, post.pk)}.webp"))

        for slide in HomeHeroSlide.objects.exclude(image="").filter(image__isnull=False):
            targets.append(self.db_target(slide, "image", f"heroes/home/home-hero-{slide.sort_order or slide.pk}.webp"))

        for slide in HomeHeroSlide.objects.exclude(mobile_image="").filter(mobile_image__isnull=False):
            targets.append(self.db_target(slide, "mobile_image", f"heroes/home/mobile/home-hero-mobile-{slide.sort_order or slide.pk}.webp"))

        for hero in SiteHero.objects.exclude(image="").filter(image__isnull=False):
            name = self.hero_name(hero)
            targets.append(self.db_target(hero, "image", f"heroes/pages/page-hero-{name}.webp"))

        for hero in SiteHero.objects.exclude(mobile_image="").filter(mobile_image__isnull=False):
            name = self.hero_name(hero)
            targets.append(self.db_target(hero, "mobile_image", f"heroes/pages/mobile/page-hero-{name}-mobile.webp"))

        return [target for target in targets if target.path.exists()]

    def get_untracked_media_targets(self, tracked_targets):
        tracked_paths = {target.path.resolve() for target in tracked_targets}
        targets = []
        if not self.media_root.exists():
            return targets

        for path in self.media_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if path.resolve() in tracked_paths:
                continue

            relative = path.relative_to(self.media_root)
            clean_parts = [ascii_slug(part, "media") for part in relative.with_suffix("").parts]
            new_relative = str(Path(*clean_parts).with_suffix(".webp")).replace("\\", "/")
            targets.append(ImageTarget(path=path, new_relative_path=new_relative))

        return targets

    def get_static_targets(self):
        targets = []
        if not self.static_root.exists():
            return targets

        for path in self.static_root.rglob("*"):
            if not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES:
                continue
            if path.suffix.lower() == ".webp":
                relative = path.relative_to(self.static_root)
                targets.append(
                    ImageTarget(
                        path=path,
                        new_relative_path=str(relative).replace("\\", "/"),
                        is_static=True,
                    )
                )
                continue

            relative = path.relative_to(self.static_root).with_suffix(".webp")
            targets.append(
                ImageTarget(
                    path=path,
                    new_relative_path=str(relative).replace("\\", "/"),
                    is_static=True,
                )
            )

        return targets

    def db_target(self, obj, field_name, new_relative_path):
        image_field = getattr(obj, field_name)
        return ImageTarget(
            path=self.media_root / image_field.name,
            new_relative_path=new_relative_path,
            model_object=obj,
            field_name=field_name,
        )

    def hero_name(self, hero):
        parts = [
            ascii_slug(hero.target_page, "page"),
            ascii_slug(hero.target_slug, "default"),
            str(hero.sort_order or hero.pk),
        ]
        return "-".join(parts)

    def resolve_destination(self, target):
        cache_key = (
            str(target.path),
            target.new_relative_path,
            target.field_name,
            id(target.model_object) if target.model_object else "",
            target.is_static,
        )
        if cache_key in self.destination_cache:
            return self.destination_cache[cache_key]

        root = self.static_root if target.is_static else self.media_root
        destination = (root / target.new_relative_path).with_suffix(".webp")
        destination = unique_path(destination, self.used_paths, source=target.path)
        self.destination_cache[cache_key] = destination
        return destination

    def static_reference(self, path):
        return "main/img/" + str(path.relative_to(self.static_root)).replace("\\", "/")

    def rewrite_static_references(self):
        roots = [Path(settings.BASE_DIR) / "main", Path(settings.BASE_DIR) / "config"]
        changed_files = 0
        for root in roots:
            for path in root.rglob("*"):
                if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                    continue

                text = path.read_text(encoding="utf-8")
                updated = text
                for old, new in self.path_replacements.items():
                    updated = updated.replace(old, new)
                    updated = updated.replace(old.replace("main/img/", "../img/"), new.replace("main/img/", "../img/"))

                if updated != text:
                    path.write_text(updated, encoding="utf-8")
                    changed_files += 1
                    self.stdout.write(self.style.SUCCESS(f"Updated references: {path}"))

        self.stdout.write(self.style.SUCCESS(f"Reference files updated: {changed_files}"))
