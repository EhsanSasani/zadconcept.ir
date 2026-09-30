"""Populate the private studio ledger with removable local design data."""

import random
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone

from main.models import Florist, StudioIngestionIssue, StudioProduct


MARKER = "[ZAD_STUDIO_DEMO_V1]"
FACTOR_PREFIX = "DEMO-ZAD-"
IMAGE_PREFIX = "studio/demo-seed-v1/"
ISSUE_CHAT_ID = -900000006271
PHOTOS = {
    "box": "flowers/categories/box-640.webp",
    "bouquet": "flowers/categories/bouquet-640.webp",
    "jar": "flowers/categories/jarl-640.webp",
    "stand": "flowers/categories/stand-640.webp",
    "basket": "flowers/categories/hand-bouquet-640.webp",
    "bridal": "sub-bridal-bouquet.webp",
    "car": "sub-bridal-car.webp",
    "other": "flowers/categories/plants-640.webp",
}
FLORISTS = (
    ("demo-mz", "مهدی زعفری", True),
    ("demo-ns", "نیوشا", True),
    ("demo-ar", "آرزو", False),
)


class Command(BaseCommand):
    help = "Create or remove marked visual demo records in a local SQLite database only."

    def add_arguments(self, parser):
        parser.add_argument("--clear", action="store_true", help="Remove only marked demo data and its images")
        parser.add_argument("--count", type=int, default=72, help="Number of records (12–120; default 72)")

    def handle(self, *args, **options):
        if not settings.DEBUG or connection.vendor != "sqlite":
            raise CommandError("Demo data is allowed only with DEBUG=True and SQLite. No data was changed.")
        if options["clear"]:
            self._clear()
            return
        count = options["count"]
        if not 12 <= count <= 120:
            raise CommandError("--count must be between 12 and 120.")
        self._seed(count)

    def _demo_records(self):
        records = StudioProduct.objects.filter(factor_code__startswith=FACTOR_PREFIX)
        if records.exclude(notes__startswith=MARKER).exists():
            raise CommandError("A factor in the demo namespace belongs to a non-demo record. No data was changed.")
        return records

    def _clear(self):
        records = self._demo_records()
        photos = set(records.exclude(image="").values_list("image", flat=True))
        with transaction.atomic():
            count = records.count()
            records.delete()
            issues = StudioIngestionIssue.objects.filter(
                telegram_chat_id=ISSUE_CHAT_ID, reason__startswith=MARKER
            ).delete()[0]
            removed_florists = 0
            for code, _, _ in FLORISTS:
                florist = Florist.objects.filter(code=code, notes=MARKER).first()
                if florist and not florist.studio_products.exists():
                    florist.delete()
                    removed_florists += 1
        for name in photos:
            if (name.startswith(IMAGE_PREFIX) and
                    not StudioProduct.objects.filter(image=name).exists()):
                default_storage.delete(name)
        self.stdout.write(self.style.SUCCESS(
            f"Removed {count} demo records, {removed_florists} demo florists, {issues} demo issues."
        ))

    def _seed(self, count):
        self._demo_records()
        for code, _, _ in FLORISTS:
            if Florist.objects.filter(code=code).exclude(notes=MARKER).exists():
                raise CommandError(f"Florist code {code} already belongs to non-demo data.")
        assets = Path(__file__).resolve().parents[3] / "main" / "static" / "main" / "img"
        missing = [relative for relative in PHOTOS.values() if not (assets / relative).is_file()]
        if missing:
            raise CommandError(f"Demo image missing: {', '.join(missing)}")

        image_names = {}
        new_files = []
        try:
            for kind, relative in PHOTOS.items():
                name = IMAGE_PREFIX + Path(relative).name
                if not default_storage.exists(name):
                    name = default_storage.save(name, ContentFile((assets / relative).read_bytes()))
                    new_files.append(name)
                image_names[kind] = name
            rng = random.Random(6217)
            now = timezone.now()
            created = 0
            with transaction.atomic():
                florists = {}
                for code, name, active in FLORISTS:
                    florist, _ = Florist.objects.get_or_create(
                        code=code,
                        defaults={"name": name, "is_active": active, "notes": MARKER,
                                  "joined_at": timezone.localdate() - timedelta(days=180)},
                    )
                    florists[code] = florist
                kinds = list(PHOTOS)
                prices = {"box": 2850000, "bouquet": 1950000, "jar": 2300000,
                          "stand": 4200000, "basket": 3100000, "bridal": 3800000,
                          "car": 5900000, "other": 1750000}
                for index in range(count):
                    factor = f"{FACTOR_PREFIX}{index + 1:04d}"
                    if StudioProduct.objects.filter(factor_code=factor).exists():
                        continue
                    kind = kinds[index % len(kinds)]
                    florist = florists["demo-mz" if index % 3 != 1 else "demo-ns"]
                    production = (StudioProduct.ProductionType.CUSTOM if index % 4 == 0
                                  else StudioProduct.ProductionType.DAILY)
                    outcome = rng.choices(
                        [StudioProduct.Status.SOLD, StudioProduct.Status.AVAILABLE,
                         StudioProduct.Status.WITHDRAWN, StudioProduct.Status.CANCELLED],
                        weights=[55, 22, 18, 5],
                    )[0]
                    age_days = index * 66 // count
                    produced = now - timedelta(days=age_days, hours=index % 7)
                    result_time = produced + timedelta(hours=2 + index % 26)
                    StudioProduct.objects.create(
                        factor_code=factor, florist=florist, product_type=kind,
                        production_type=production, price=prices[kind] + rng.randrange(-5, 9) * 100000,
                        status=outcome, source=StudioProduct.Source.DASHBOARD,
                        image=image_names[kind], produced_at=produced,
                        sold_at=result_time if outcome == StudioProduct.Status.SOLD else None,
                        withdrawn_at=result_time if outcome == StudioProduct.Status.WITHDRAWN else None,
                        notes=f"{MARKER} فقط برای بررسی ظاهر داشبورد؛ فاکتور واقعی نیست.",
                    )
                    created += 1
                for message_id, reason in ((1, "کد فلوریست در کپشن وارد نشده"),
                                           (2, "شماره فاکتور نیازمند اصلاح است")):
                    StudioIngestionIssue.objects.get_or_create(
                        telegram_chat_id=ISSUE_CHAT_ID, telegram_message_id=message_id,
                        defaults={"reason": f"{MARKER} {reason}"},
                    )
        except Exception:
            for name in new_files:
                default_storage.delete(name)
            raise
        self.stdout.write(self.style.SUCCESS(
            f"Created {created} demo records; {self._demo_records().count()} in total. "
            "Open /studio/ and use --clear to remove the demo data."
        ))
