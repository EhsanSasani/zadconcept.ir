from django.core.management.base import BaseCommand
from django.utils import timezone
from main.models import CustomerLoginRate


class Command(BaseCommand):
    help = "Remove expired customer login rate buckets; never removes accounts or passwords."

    def handle(self, *args, **options):
        count, _ = CustomerLoginRate.objects.filter(expires_at__lt=timezone.now()).delete()
        self.stdout.write(f"Removed {count} expired rate buckets.")
