from django.core.management.base import BaseCommand, CommandError

from main.models import ShopPayment
from main.shop_payments import get_gateway, verify_payment
from main.shop_service import ShopError


class Command(BaseCommand):
    help = "Securely reconcile existing pending/review payments using the configured real gateway."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if not 1 <= options["limit"] <= 10000:
            raise CommandError("limit must be between 1 and 10000")
        try:
            get_gateway()
        except ShopError:
            raise CommandError("A real payment gateway must be configured before reconciliation.") from None
        authorities = list(ShopPayment.objects.filter(
            status__in=[ShopPayment.Status.PENDING, ShopPayment.Status.REVIEW], authority__isnull=False,
        ).exclude(authority="").order_by("created_at").values_list("authority", flat=True)[:options["limit"]])
        counts = {"paid": 0, "cancelled": 0, "review": 0, "pending": 0, "errors": 0}
        for authority in authorities:
            try:
                order = verify_payment(authority=authority)
                counts[order.status] += 1
            except ShopError as error:
                counts["pending" if error.code == "payment_pending" else "errors"] += 1
        manual = ShopPayment.objects.filter(
            status__in=[ShopPayment.Status.REQUESTING, ShopPayment.Status.REVIEW], authority__isnull=True,
        ).count()
        # Output counts only: authorities, customer information and provider errors
        # can contain sensitive data and have no place in scheduler logs.
        self.stdout.write(self.style.SUCCESS(
            "Reconciled {count}: paid={paid}, cancelled={cancelled}, review={review}, pending={pending}, errors={errors}; "
            "request_unknown_manual_review={manual}.".format(count=len(authorities), manual=manual, **counts)
        ))
