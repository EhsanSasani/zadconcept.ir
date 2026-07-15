from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from main.models import Category, Product, Tag


TAG_CODE_MAP = {
    "b": "engagement",
    "u": "special",
    "t": "condolence",
    "d": "same-day",
    "l": "romantic",
    "h": "birthday",
    "k": "proposal",
    "m": "apology",
    "c": "congratulation",
    "w": "no-occasion",
}

FOLDER_CATEGORY_MAP = {
    "bouquets": "bouquet",
    "box": "box",
    "daste gol": "hand-bouquet",
    "jarl": "jarl",
    "stand": "stand",
    "wedding": "bridal-bouquet",
    "wedding car": "wedding-car",
    "mashine aroos": "wedding-car",
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = "Import ZAD products from Behzad flash folder."

    def add_arguments(self, parser):
        parser.add_argument("source_dir", type=str)

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])

        if not source_dir.exists():
            raise CommandError(f"Folder not found: {source_dir}")

        created_count = 0
        skipped_count = 0

        for folder_name, category_slug in FOLDER_CATEGORY_MAP.items():
            folder_path = source_dir / folder_name

            if not folder_path.exists():
                self.stdout.write(self.style.WARNING(f"Missing folder: {folder_path}"))
                continue

            category = Category.objects.filter(
                section=Category.Section.FLOWERS,
                slug=category_slug,
                is_active=True,
            ).first()

            if not category:
                self.stdout.write(self.style.ERROR(f"Category not found: {category_slug}"))
                continue

            for image_path in folder_path.iterdir():
                if image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue

                tag_codes = [
                    part.lower()
                    for part in image_path.stem.replace("_", "-").split("-")
                    if part
                ]

                tag_slugs = [
                    TAG_CODE_MAP[code]
                    for code in tag_codes
                    if code in TAG_CODE_MAP
                ]

                tags = list(Tag.objects.filter(slug__in=tag_slugs, is_active=True))

                product = Product.objects.create(
                    name="",
                    category=category,
                    pricing_type=Product.PricingType.INQUIRY,
                    publish_status=Product.PublishStatus.DRAFT,
                    stock_status=Product.StockStatus.IN_STOCK,
                    is_active=True,
                )

                with image_path.open("rb") as image_file:
                    product.cover_image.save(image_path.name, File(image_file), save=True)

                if tags:
                    product.tags.set(tags)

                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {product.product_code} | {category.slug} | {image_path.name}"
                    )
                )

        self.stdout.write(self.style.SUCCESS(f"Created: {created_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped: {skipped_count}"))
