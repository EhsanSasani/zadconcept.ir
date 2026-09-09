import re
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.apps import apps
from django.core.files import File
from django.core.management.base import BaseCommand, CommandError
from django.db import models
from django.utils import timezone
from django.utils.text import slugify
from PIL import Image, ImageOps

from main.image_pipeline import (
    ImageUploadError, MAX_IMAGE_DIMENSION, MAX_UPLOAD_BYTES,
    create_responsive_image_variants, normalize_admin_image,
)

from main.models import Product, ProductImage


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
    with source.open("rb") as handle:
        normalized = normalize_admin_image(
            File(handle, name=source.name), max_dimension=max_dimension, quality=quality
        )
    temporary = destination.with_name(f"{destination.name}.optimizing")
    try:
        temporary.write_bytes(normalized.read())
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


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
    help = "Normalize referenced image fields; preserve original and untracked media."

    def add_arguments(self, parser):
        parser.add_argument("--quality", type=int, default=88)
        parser.add_argument("--max-dimension", type=int, default=MAX_IMAGE_DIMENSION)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--keep-originals", action="store_true", default=True,
            help="Compatibility option: originals are always preserved.",
        )
        parser.add_argument("--skip-static-rewrite", action="store_true")
        parser.add_argument("--skip-responsive", action="store_true")
        scope = parser.add_mutually_exclusive_group()
        scope.add_argument(
            "--media-only", action="store_true",
            help="Only referenced database images (the default).",
        )
        scope.add_argument(
            "--include-static", action="store_true",
            help="Also convert non-WebP source static assets and their references.",
        )

    def handle(self, *args, **options):
        self.quality = options["quality"]
        self.max_dimension = options["max_dimension"]
        if not 1 <= self.quality <= 100:
            raise CommandError("quality must be between 1 and 100")
        if not 1 <= self.max_dimension <= MAX_IMAGE_DIMENSION:
            raise CommandError(f"max-dimension must be between 1 and {MAX_IMAGE_DIMENSION}")
        self.dry_run = options["dry_run"]
        self.skip_responsive = options["skip_responsive"]
        self.static_root = Path(settings.BASE_DIR) / STATIC_IMG_ROOT
        self.path_replacements = {}
        self.used_paths = set()
        self.media_cache = {}
        changed = skipped = failed = 0
        for obj, field in self.get_database_targets():
            try:
                if self.optimize_database_image(obj, field):
                    changed += 1
                else:
                    skipped += 1
            except (OSError, ValueError, Image.DecompressionBombError) as error:
                failed += 1
                self.stderr.write(self.style.WARNING(
                    f"Skipped {obj._meta.label} #{obj.pk}.{field.name}: {error}"
                ))
        if options["include_static"]:
            for target in self.get_static_targets():
                destination = unique_path(
                    (self.static_root / target.new_relative_path).with_suffix(".webp"),
                    self.used_paths,
                )
                if self.dry_run:
                    self.stdout.write(f"Would optimize static: {target.path} -> {destination}")
                    continue
                try:
                    optimize_to_webp(target.path, destination, self.quality, True, self.max_dimension)
                except (OSError, ValueError, Image.DecompressionBombError) as error:
                    failed += 1
                    self.stderr.write(self.style.WARNING(f"Skipped {target.path}: {error}"))
                    continue
                self.path_replacements[self.static_reference(target.path)] = self.static_reference(destination)
            if self.path_replacements and not options["skip_static_rewrite"]:
                self.rewrite_static_references()
        self.stdout.write(self.style.SUCCESS(f"Optimized: {changed}; unchanged: {skipped}; failed: {failed}"))
        self.stdout.write("Original files and untracked media were preserved.")

    def get_database_targets(self):
        """Discover every concrete image field, including future content models."""
        for model in apps.get_app_config("main").get_models():
            if model._meta.proxy or model._meta.abstract:
                continue
            for field in model._meta.concrete_fields:
                if not isinstance(field, models.ImageField):
                    continue
                queryset = model._base_manager.exclude(
                    **{field.name: ""}
                ).filter(**{f"{field.name}__isnull": False})
                for obj in queryset.iterator(chunk_size=100):
                    yield obj, field

    def is_normalized(self, storage, name):
        """Avoid another lossy generation of already clean, bounded WebP files."""
        if Path(name).suffix.lower() != ".webp":
            return False
        with storage.open(name, "rb") as handle, Image.open(handle) as image:
            if (image.format != "WEBP" or getattr(image, "is_animated", False)
                    or max(image.size) > self.max_dimension
                    or image.info.get("exif") or image.info.get("xmp")):
                return False
            image.load()
        return True

    def output_name(self, obj, field, source):
        parent = Path(source).parent
        if isinstance(obj, Product):
            stem = f"product-{ascii_slug(str(obj.product_code or obj.pk), 'product')}"
        elif isinstance(obj, ProductImage):
            code = ascii_slug(str(obj.product.product_code or obj.product_id), "product")
            stem = f"product-{code}-gallery-{obj.ordering or obj.pk}"
        else:
            stem = f"{obj._meta.model_name}-{obj.pk}-{ascii_slug(field.name)}"
        return (parent / f"{stem}.webp").as_posix()

    def optimize_database_image(self, obj, field):
        image_file = getattr(obj, field.name)
        source_name, storage = image_file.name, image_file.storage
        label = f"{obj._meta.label} #{obj.pk}.{field.name}"
        if not storage.exists(source_name):
            raise OSError(f"Missing: {source_name}")
        if storage.size(source_name) > MAX_UPLOAD_BYTES:
            raise ImageUploadError("Image exceeds the 20 MB processing limit.")
        if self.dry_run:
            self.stdout.write(f"Would inspect/optimize: {label} ({source_name})")
            return True
        cache_key = (id(storage), source_name)
        destination = self.media_cache.get(cache_key)
        if destination is None:
            if self.is_normalized(storage, source_name):
                destination = source_name
            else:
                with storage.open(source_name, "rb") as handle:
                    normalized = normalize_admin_image(
                        File(handle, name=source_name),
                        max_dimension=self.max_dimension, quality=self.quality,
                    )
                desired_name = self.output_name(obj, field, source_name)
                destination = desired_name
                index = 2
                while storage.exists(destination):
                    desired_path = Path(desired_name)
                    destination = desired_path.with_name(
                        f"{desired_path.stem}-{index}.webp"
                    ).as_posix()
                    index += 1
                destination = storage.save(destination, normalized)
            self.media_cache[cache_key] = destination
        if destination != source_name:
            # Do not restore an older picture if an editor replaces it while
            # this command works. Never delete any source on success/failure.
            values = {field.name: destination}
            if any(item.name == "updated_at" for item in obj._meta.concrete_fields):
                values["updated_at"] = timezone.now()
            updated = type(obj)._base_manager.filter(
                pk=obj.pk, **{field.name: source_name}
            ).update(**values)
            if not updated:
                self.stdout.write(self.style.WARNING(f"Changed by an editor; retained newer image: {label}"))
                return False
            self.stdout.write(self.style.SUCCESS(f"{label}: {source_name} -> {destination}"))
        if not self.skip_responsive and isinstance(obj, (Product, ProductImage)):
            create_responsive_image_variants(storage, destination)
        return destination != source_name

    def get_static_targets(self):
        if not self.static_root.exists():
            return
        for path in self.static_root.rglob("*"):
            if (not path.is_file() or path.suffix.lower() not in IMAGE_SUFFIXES
                    or path.suffix.lower() == ".webp"):
                continue
            relative = path.relative_to(self.static_root).with_suffix(".webp")
            yield ImageTarget(path=path, new_relative_path=relative.as_posix(), is_static=True)

    def static_reference(self, path):
        return "main/img/" + path.relative_to(self.static_root).as_posix()

    def rewrite_static_references(self):
        roots = [Path(settings.BASE_DIR) / "main", Path(settings.BASE_DIR) / "config"]
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
                    self.stdout.write(self.style.SUCCESS(f"Updated references: {path}"))
