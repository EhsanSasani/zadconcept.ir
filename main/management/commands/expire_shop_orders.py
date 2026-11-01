from django.core.management.base import BaseCommand, CommandError

from main.shop_service import expire_orders


class Command(BaseCommand):
    help = "Release expired shop reservations only when no ambiguous payment exists."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 10000:
            raise CommandError("limit must be between 1 and 10000")
        count = expire_orders(limit=options["limit"])
        self.stdout.write(self.style.SUCCESS(f"Released {count} expired shop reservation(s)."))
