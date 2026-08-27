from pathlib import Path

from django.core.files import File
from django.core.management.base import BaseCommand, CommandError

from main.models import Category, Product, Tag


TAG_CODE_MAP = {
    "b": "engagement",
    "u": "unique",
    "t": "condolence",
    "l": "romantic",
    "h": "birthday",
    "k": "proposal",
    "m": "apology",
    "c": "congratulation",
    "w": "no-occasion",
}

PROPOSAL_TAG_SLUGS = {"proposal", "engagement"}

# A plain ``wedding`` directory does not prove whether an image is a bridal
# bouquet or wedding-car product. New imports must have an explicit type.
AMBIGUOUS_WEDDING_FOLDERS = {"wedding"}

FOLDER_RULES = {
    "bouquets": {
        "section": Category.Section.FLOWERS,
        "category_slug": "bouquet",
    },
    "box": {
        "section": Category.Section.FLOWERS,
        "category_slug": "box",
    },
    "daste gol": {
        "section": Category.Section.FLOWERS,
        "category_slug": "hand-bouquet",
    },
    "jarl": {
        "section": Category.Section.FLOWERS,
        "category_slug": "jarl",
    },
    "stand": {
        "section": Category.Section.FLOWERS,
        "category_slug": "stand",
    },
    "wedding car": {
        "wedding_type": Product.WeddingType.WEDDING_CAR,
    },
    "mashine aroos": {
        "wedding_type": Product.WeddingType.WEDDING_CAR,
    },
    "bridal bouquet": {
        "wedding_type": Product.WeddingType.BRIDAL_BOUQUET,
    },
    "wedding bouquet": {
        "wedding_type": Product.WeddingType.BRIDAL_BOUQUET,
    },
    "proposal bouquet": {
        "wedding_type": Product.WeddingType.PROPOSAL_BOUQUET,
    },
    "proposal sweets": {
        "wedding_type": Product.WeddingType.PROPOSAL_SWEETS,
    },
    "bale boroon sweets": {
        "wedding_type": Product.WeddingType.PROPOSAL_SWEETS,
    },
}

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


class Command(BaseCommand):
    help = (
        "Import ZAD products from the flash-folder layout. Wedding products "
        "require an explicit compatible folder type; proposal/engagement "
        "codes are accepted only from the hand-bouquet folder."
    )

    def add_arguments(self, parser):
        parser.add_argument("source_dir", type=str)

    def handle(self, *args, **options):
        source_dir = Path(options["source_dir"])
        if not source_dir.exists():
            raise CommandError(f"Folder not found: {source_dir}")
        if not source_dir.is_dir():
            raise CommandError(f"Not a directory: {source_dir}")

        created_count = 0
        skipped_count = 0

        for folder_name in sorted(AMBIGUOUS_WEDDING_FOLDERS):
            folder_path = source_dir / folder_name
            images = self.image_files(folder_path)
            if not images:
                continue
            skipped_count += len(images)
            self.stdout.write(
                self.style.WARNING(
                    f"Skipped {len(images)} file(s) in ambiguous folder "
                    f"{folder_path}. Rename/move them to an explicit Wedding "
                    "type folder before importing."
                )
            )

        for folder_name, rule in FOLDER_RULES.items():
            folder_path = source_dir / folder_name
            images = self.image_files(folder_path)
            if not images:
                continue

            for image_path in images:
                tag_slugs = self.tag_slugs_from_filename(image_path)
                wedding_type = rule.get("wedding_type")

                # Legacy filename codes ``k`` and ``b`` are an explicit
                # proposal/bale-boroon signal. They are no longer persisted as
                # public Occasion tags.
                if not wedding_type and PROPOSAL_TAG_SLUGS.intersection(tag_slugs):
                    if folder_name == "daste gol":
                        wedding_type = Product.WeddingType.PROPOSAL_BOUQUET
                    else:
                        skipped_count += 1
                        self.stderr.write(
                            self.style.ERROR(
                                "Proposal/engagement filename code is only valid "
                                "inside 'daste gol' or an explicit Wedding folder; "
                                f"skipped {image_path}"
                            )
                        )
                        continue

                if wedding_type:
                    section, category_slug = Product.WEDDING_CATEGORY_MAP[
                        wedding_type
                    ]
                else:
                    section = rule["section"]
                    category_slug = rule["category_slug"]

                category = Category.objects.filter(
                    section=section,
                    slug=category_slug,
                    is_active=True,
                ).first()
                if not category:
                    skipped_count += 1
                    self.stderr.write(
                        self.style.ERROR(
                            f"Category not found: {section}/{category_slug}; "
                            f"skipped {image_path.name}"
                        )
                    )
                    continue

                if wedding_type:
                    tags = []
                    catalog_scope = Product.CatalogScope.WEDDING
                else:
                    tags = list(
                        Tag.objects.for_general_catalog().filter(
                            slug__in=tag_slugs,
                            is_active=True,
                        )
                    )
                    catalog_scope = Product.CatalogScope.GENERAL

                product = Product.objects.create(
                    name="",
                    category=category,
                    catalog_scope=catalog_scope,
                    wedding_type=wedding_type or "",
                    wedding_needs_review=False,
                    pricing_type=Product.PricingType.INQUIRY,
                    publish_status=Product.PublishStatus.DRAFT,
                    stock_status=Product.StockStatus.IN_STOCK,
                    is_active=True,
                )

                with image_path.open("rb") as image_file:
                    product.cover_image.save(
                        image_path.name,
                        File(image_file),
                        save=True,
                    )

                # Wedding products deliberately receive no public or protected
                # tags. Same-day products are created only from their dedicated
                # admin. General imports receive active public tags only.
                if tags:
                    product.tags.set(tags)

                created_count += 1
                type_label = wedding_type or "general"
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {product.product_code} | {category.slug} | "
                        f"{type_label} | {image_path.name}"
                    )
                )

        self.stdout.write(self.style.SUCCESS(f"Created: {created_count}"))
        self.stdout.write(self.style.WARNING(f"Skipped: {skipped_count}"))

    @staticmethod
    def image_files(folder_path):
        if not folder_path.is_dir():
            return []
        return sorted(
            (
                path
                for path in folder_path.iterdir()
                if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
            ),
            key=lambda path: path.name.casefold(),
        )

    @staticmethod
    def tag_slugs_from_filename(image_path):
        codes = [
            part.casefold()
            for part in image_path.stem.replace("_", "-").split("-")
            if part
        ]
        # Preserve code order while removing duplicates.
        return list(
            dict.fromkeys(TAG_CODE_MAP[code] for code in codes if code in TAG_CODE_MAP)
        )
