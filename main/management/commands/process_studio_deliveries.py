"""Run outside the web request; safe to stop and restart after an interrupted send."""
import time

from django.core.management.base import BaseCommand, CommandError
from django.db import close_old_connections

from main.studio_delivery import process_next_delivery
from main.studio_admin_notifications import process_next_admin_notification


class Command(BaseCommand):
    help = "Process the durable Studio Telegram delivery queue (no duplicate retries after uncertain sends)."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group()
        mode.add_argument("--once", action="store_true", help="Drain currently due deliveries, then exit (default).")
        mode.add_argument("--watch", action="store_true", help="Keep checking for due deliveries.")
        parser.add_argument("--interval", type=float, default=3, help="Idle polling interval in seconds (1–60).")
        parser.add_argument("--limit", type=int, default=100, help="Maximum deliveries in one-shot mode (1–1000).")

    def handle(self, *args, **options):
        if not 1 <= options["interval"] <= 60 or not 1 <= options["limit"] <= 1000:
            raise CommandError("Use an interval of 1–60 seconds and a limit of 1–1000 deliveries.")
        count = 0
        try:
            while True:
                close_old_connections()
                processed = False
                delivery = process_next_delivery()
                if delivery:
                    processed = True
                    count += 1
                    self.stdout.write(
                        f"delivery={delivery.pk} action={delivery.action} status={delivery.status}"
                    )
                    if not options["watch"] and count >= options["limit"]:
                        break
                notification = process_next_admin_notification()
                if notification:
                    processed = True
                    count += 1
                    self.stdout.write(
                        f"admin_notification={notification.pk} "
                        f"event={notification.event} status={notification.status}"
                    )
                    if not options["watch"] and count >= options["limit"]:
                        break
                if processed:
                    continue
                if not options["watch"]:
                    break
                time.sleep(options["interval"])
        except KeyboardInterrupt:
            self.stdout.write("Studio delivery worker stopped.")
        if not options["watch"]:
            self.stdout.write(f"Processed {count} due deliveries.")
