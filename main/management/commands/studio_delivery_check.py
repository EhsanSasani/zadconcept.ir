"""Safe diagnostics: no sends, retries, webhook registration or data changes."""
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count

from main.models import StudioAdminNotification, StudioDelivery
from main.studio_admin_notifications import _admin_chat_id
from main.studio_transport import TelegramDeliveryError, _chat_id, get_chat


class Command(BaseCommand):
    help = "Read-only Studio configuration/queue report; --network checks Telegram getChat only."

    def add_arguments(self, parser):
        parser.add_argument("--network", action="store_true", help="Check configured destinations using getChat; never send messages.")
        parser.add_argument("--destination", choices=["all", "ready", "custom", "admin"], default="all")

    def handle(self, *args, **options):
        relay = str(getattr(settings, "TELEGRAM_SAME_DAY_RELAY_URL", "")).strip()
        self.stdout.write("transport=" + ("relay" if relay else "direct"))
        if relay:
            try:
                self.stdout.write("relay_host=" + (urlsplit(relay).hostname or "invalid"))
            except ValueError:
                self.stdout.write("relay_host=invalid")
        for label, model in (("group_queue", StudioDelivery), ("private_queue", StudioAdminNotification)):
            counts = dict(model.objects.values_list("status").annotate(total=Count("pk")))
            self.stdout.write(label + " " + " ".join(f"{state}={counts.get(state, 0)}" for state in model.Status.values))
        destinations = {
            "ready": "TELEGRAM_SAME_DAY_GROUP_ID",
            "custom": "TELEGRAM_STUDIO_CUSTOM_GROUP_ID",
            "admin": "TELEGRAM_STUDIO_ADMIN_CHAT_ID",
        }
        failures = []
        for label, name in destinations.items():
            if options["destination"] not in {"all", label}:
                continue
            value = str(getattr(settings, name, "")).strip()
            if not value:
                self.stdout.write(f"{label}=not_configured")
                if options["destination"] == label:
                    failures.append(label)
                continue
            try:
                if label == "admin" and _admin_chat_id() is None:
                    raise TelegramDeliveryError("configuration_error")
                valid = _chat_id(value)
                self.stdout.write(f"{label}_chat_id={valid}")
                if options["network"]:
                    result = get_chat(valid)
                    self.stdout.write(f"{label}_getChat=OK type={result['type']}")
            except TelegramDeliveryError as error:
                failures.append(label)
                self.stdout.write(f"{label}_check=ERROR code={error.code} retryable={error.retryable}")
                if label == "admin" and error.code == "invalid_payload":
                    self.stdout.write("admin_hint=compare deployed Worker version, relay host and TELEGRAM_STUDIO_ADMIN_CHAT_ID allowlist; no resend performed")
        if failures:
            raise CommandError("Destination checks failed: " + ", ".join(failures) + ". No messages sent or queue rows changed.")
        if not options["network"]:
            self.stdout.write("No network call made. Add --network for read-only getChat checks.")
