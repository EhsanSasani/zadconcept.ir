from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from main.models import (
    Category,
    Product,
    PROPOSAL_COLLECTION_TAG_SLUG,
    Tag,
)


PROPOSAL_COLLECTION_CODES = (
    "0407",
    "0401",
    "0404",
    "0402",
    "0400",
    "0398",
    "0445",
    "0446",
    "0439",
    "0433",
    "0435",
    "0432",
    "0429",
    "0430",
    "0431",
    "0422",
    "0420",
    "0424",
    "0423",
    "0415",
    "0417",
    "0418",
    "0419",
    "0411",
    "0413",
    "0414",
    "0487",
    "0482",
    "0481",
    "0475",
    "0474",
    "0463",
    "0460",
    "0454",
    "0456",
    "0452",
    "0451",
)

DELETE_CODES = (
    "0681",
    "0682",
    "0678",
    "0684",
    "0668",
    "0672",
    "0462",
    "0624",
    "0632",
    "0615",
    "0618",
    "0617",
    "0610",
    "0613",
    "0607",
    "0608",
    "0604",
    "0605",
    "0596",
)

BRIDAL_PRIORITY_CODES = (
    "0655",
    "0656",
    "0646",
    "0638",
    "0640",
    "0635",
    "0636",
    "0633",
    "0629",
    "0627",
    "0620",
    "0611",
)

FORMAL_VISIT_CODES = (
    "0427",
    "0432",
    "0459",
    "0464",
    "0474",
    "0423",
    "0510",
    "0511",
    "0505",
    "0490",
)

JUST_BECAUSE_CODES = (
    "0450",
    "0449",
    "0448",
)

CODE_GROUPS = {
    "proposal_collection": PROPOSAL_COLLECTION_CODES,
    "delete": DELETE_CODES,
    "bridal_priority": BRIDAL_PRIORITY_CODES,
    "formal_visit": FORMAL_VISIT_CODES,
    "just_because": JUST_BECAUSE_CODES,
}

EXPECTED_COUNTS = {
    "proposal_collection": 37,
    "delete": 19,
    "bridal_priority": 12,
    "formal_visit": 10,
    "just_because": 3,
}


class Command(BaseCommand):
    help = (
        "Validate and apply the reviewed ZAD catalog curation hotfix. "
        "The default mode is read-only; pass --apply to write changes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the validated changes inside one database transaction.",
        )

    def handle(self, *args, **options):
        self._validate_manifest()
        products_by_code = self._load_and_validate_products()
        self._validate_tag_name_conflicts()
        self._write_plan()

        if not options["apply"]:
            self.stdout.write(
                self.style.WARNING(
                    "DRY-RUN only: no database rows were changed. "
                    "Run the same command with --apply after taking a database backup."
                )
            )
            return

        with transaction.atomic():
            result = self._apply(products_by_code)

        self.stdout.write(
            self.style.SUCCESS(
                "Catalog hotfix applied successfully: "
                f"proposal={result['proposal']}, "
                f"deleted={result['deleted']}, "
                f"bridal_priority={result['bridal']}, "
                f"formal_visit={result['formal']}, "
                f"just_because={result['just_because']}."
            )
        )

    def _validate_manifest(self):
        for name, codes in CODE_GROUPS.items():
            expected = EXPECTED_COUNTS[name]
            if len(codes) != expected or len(set(codes)) != expected:
                raise CommandError(
                    f"Invalid {name} manifest: expected {expected} unique codes."
                )

        destructive_overlap = set(DELETE_CODES).intersection(
            set(PROPOSAL_COLLECTION_CODES)
            | set(BRIDAL_PRIORITY_CODES)
            | set(FORMAL_VISIT_CODES)
            | set(JUST_BECAUSE_CODES)
        )
        if destructive_overlap:
            raise CommandError(
                "Delete codes overlap another operation: "
                + ", ".join(sorted(destructive_overlap))
            )

    def _load_and_validate_products(self):
        all_codes = set().union(*(set(codes) for codes in CODE_GROUPS.values()))
        products_by_code = Product.objects.select_related(
            "category",
            "category__parent",
        ).in_bulk(all_codes, field_name="product_code")

        missing_groups = {}
        for name, codes in CODE_GROUPS.items():
            missing = [code for code in codes if code not in products_by_code]
            if missing:
                missing_groups[name] = missing

        if missing_groups:
            details = "; ".join(
                f"{name}: {', '.join(codes)}"
                for name, codes in missing_groups.items()
            )
            raise CommandError(f"Missing product codes; nothing was changed. {details}")

        valid_general_flower_codes = set(
            Product.objects.for_general_catalog()
            .published()
            .filter(
                product_code__in=PROPOSAL_COLLECTION_CODES,
                category__section=Category.Section.FLOWERS,
            )
            .values_list("product_code", flat=True)
        )
        invalid_proposal = [
            code
            for code in PROPOSAL_COLLECTION_CODES
            if code not in valid_general_flower_codes
        ]
        if invalid_proposal:
            raise CommandError(
                "Proposal products must be published general flower products: "
                + ", ".join(invalid_proposal)
            )

        occasion_codes = set(FORMAL_VISIT_CODES) | set(JUST_BECAUSE_CODES)
        valid_occasion_codes = set(
            Product.objects.for_general_catalog()
            .published()
            .filter(product_code__in=occasion_codes)
            .values_list("product_code", flat=True)
        )
        invalid_occasions = sorted(occasion_codes - valid_occasion_codes)
        if invalid_occasions:
            raise CommandError(
                "Occasion products must be published general products: "
                + ", ".join(invalid_occasions)
            )

        valid_bridal_codes = set(
            Product.objects.valid_weddings()
            .published()
            .filter(
                product_code__in=BRIDAL_PRIORITY_CODES,
                wedding_type=Product.WeddingType.BRIDAL_BOUQUET,
            )
            .values_list("product_code", flat=True)
        )
        invalid_bridal = [
            code for code in BRIDAL_PRIORITY_CODES if code not in valid_bridal_codes
        ]
        if invalid_bridal:
            raise CommandError(
                "Bridal priority products must be valid published bridal bouquets: "
                + ", ".join(invalid_bridal)
            )

        return products_by_code

    def _validate_tag_name_conflicts(self):
        tag_targets = (
            (PROPOSAL_COLLECTION_TAG_SLUG, "کالکشن خواستگاری (سیستمی)"),
            ("formal-visit", "دیدار رسمی"),
            ("no-occasion", "بی‌بهانه"),
        )
        for slug, name in tag_targets:
            conflict = Tag.objects.filter(name=name).exclude(slug=slug).first()
            if conflict:
                raise CommandError(
                    f"Tag name conflict for {name}: existing slug={conflict.slug}."
                )

    def _write_plan(self):
        self.stdout.write("Catalog hotfix 2026-08-11 validated:")
        for name, codes in CODE_GROUPS.items():
            self.stdout.write(f"- {name}: {len(codes)} products")
        overlap = sorted(set(PROPOSAL_COLLECTION_CODES) & set(FORMAL_VISIT_CODES))
        self.stdout.write(
            "- additive proposal/formal overlap: "
            + (", ".join(overlap) if overlap else "none")
        )
        self.stdout.write("- existing product tags and original categories are preserved")
        self.stdout.write("- media files are not physically deleted")

    def _sync_tag(self, *, slug, name, is_occasion, is_active, sort_order):
        tag = Tag.objects.filter(slug=slug).first()
        if tag is None:
            tag = Tag(slug=slug)
        tag.name = name
        tag.is_occasion = is_occasion
        tag.is_active = is_active
        tag.sort_order = sort_order
        tag.save()
        return tag

    def _apply(self, products_by_code):
        proposal_tag = self._sync_tag(
            slug=PROPOSAL_COLLECTION_TAG_SLUG,
            name="کالکشن خواستگاری (سیستمی)",
            is_occasion=False,
            is_active=False,
            sort_order=110,
        )
        formal_visit_tag = self._sync_tag(
            slug="formal-visit",
            name="دیدار رسمی",
            is_occasion=True,
            is_active=True,
            sort_order=70,
        )
        just_because_tag = self._sync_tag(
            slug="no-occasion",
            name="بی‌بهانه",
            is_occasion=True,
            is_active=True,
            sort_order=90,
        )

        Tag.objects.filter(slug="apology").update(
            is_occasion=False,
            updated_at=timezone.now(),
        )

        for code in PROPOSAL_COLLECTION_CODES:
            products_by_code[code].tags.add(proposal_tag)
        for code in FORMAL_VISIT_CODES:
            products_by_code[code].tags.add(formal_visit_tag)
        for code in JUST_BECAUSE_CODES:
            products_by_code[code].tags.add(just_because_tag)

        selected_ids = {
            products_by_code[code].pk for code in BRIDAL_PRIORITY_CODES
        }
        remaining_bridal = list(
            Product.objects.valid_weddings()
            .filter(wedding_type=Product.WeddingType.BRIDAL_BOUQUET)
            .exclude(pk__in=selected_ids)
            .order_by(
                "wedding_sort_order",
                "sort_order",
                "-created_at",
                "id",
            )
        )
        ordered_bridal = [
            products_by_code[code] for code in BRIDAL_PRIORITY_CODES
        ] + remaining_bridal
        now = timezone.now()
        for index, product in enumerate(ordered_bridal):
            if index < len(BRIDAL_PRIORITY_CODES):
                product.wedding_sort_order = index + 1
            else:
                product.wedding_sort_order = 1000 + index
            product.updated_at = now
        Product.objects.bulk_update(
            ordered_bridal,
            ["wedding_sort_order", "updated_at"],
        )

        delete_ids = [products_by_code[code].pk for code in DELETE_CODES]
        deleted_count = Product.objects.filter(pk__in=delete_ids).count()
        if deleted_count != len(DELETE_CODES):
            raise CommandError(
                "Delete target count changed during the transaction; rolled back."
            )
        Product.objects.filter(pk__in=delete_ids).delete()

        return {
            "proposal": len(PROPOSAL_COLLECTION_CODES),
            "deleted": deleted_count,
            "bridal": len(BRIDAL_PRIORITY_CODES),
            "formal": len(FORMAL_VISIT_CODES),
            "just_because": len(JUST_BECAUSE_CODES),
        }
