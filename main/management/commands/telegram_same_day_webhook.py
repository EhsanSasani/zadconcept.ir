"""Explicit webhook registration; never puts credentials in argv or output."""
import re
from urllib.parse import urlsplit

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from main.telegram_same_day.client import TelegramTransportError, bot_api
from main.telegram_same_day.service import SyncConfigurationError, _category


class Command(BaseCommand):
    help = "Check same-day configuration, register its webhook, or inspect delivery health."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["check", "register", "info"])
        parser.add_argument("--url", help="Explicit public HTTPS endpoint (Django or existing Worker).")

    def handle(self, *args, **options):
        action = options["action"]
        if action in {"check", "register"}:
            if not re.fullmatch(r"[A-Za-z0-9_-]{1,256}", settings.TELEGRAM_WEBHOOK_SECRET):
                raise CommandError("TELEGRAM_WEBHOOK_SECRET is missing or invalid.")
            channel = str(settings.TELEGRAM_CHANNEL_ID)
            direct = str(settings.TELEGRAM_SAME_DAY_GROUP_ID)
            if not channel and not direct:
                raise CommandError("Set TELEGRAM_CHANNEL_ID or TELEGRAM_SAME_DAY_GROUP_ID.")
            for value in (channel, direct):
                if value and not re.fullmatch(r"-[0-9]+", value):
                    raise CommandError("Telegram source IDs must be numeric negative IDs.")
            group = str(settings.TELEGRAM_DISCUSSION_GROUP_ID)
            if group and (not re.fullmatch(r"-[0-9]+", group) or group == str(settings.TELEGRAM_CHANNEL_ID)):
                raise CommandError("TELEGRAM_DISCUSSION_GROUP_ID must be a distinct negative group ID.")
            if direct and direct in (channel, group):
                raise CommandError("Direct product group must be distinct from channel/discussion IDs.")
            custom = str(settings.TELEGRAM_STUDIO_CUSTOM_GROUP_ID)
            if custom and (not re.fullmatch(r"-[0-9]+", custom) or custom in (channel, group, direct)):
                raise CommandError("TELEGRAM_STUDIO_CUSTOM_GROUP_ID must be a distinct negative group ID.")
        if action == "check":
            try:
                category = _category()
            except SyncConfigurationError:
                raise CommandError("Select an active general flower category with TELEGRAM_SAME_DAY_CATEGORY_ID.") from None
            if settings.TELEGRAM_SAME_DAY_RELAY_URL:
                if urlsplit(settings.TELEGRAM_SAME_DAY_RELAY_URL).scheme != "https" or not settings.TELEGRAM_LEAD_RELAY_SECRET:
                    raise CommandError("Worker download needs an HTTPS relay URL and TELEGRAM_LEAD_RELAY_SECRET.")
            elif not settings.TELEGRAM_BOT_TOKEN:
                raise CommandError("Direct download requires TELEGRAM_BOT_TOKEN.")
            self.stdout.write(self.style.SUCCESS(f"Same-day configuration OK; category_id={category.pk}. No network call made."))
            return
        try:
            if action == "register":
                url = options["url"] or ""
                parts = urlsplit(url)
                if parts.scheme != "https" or not parts.hostname or parts.username or parts.password or parts.query or parts.fragment:
                    raise CommandError("Supply --url with a public HTTPS endpoint without credentials or query string.")
                result = bot_api("setWebhook", {
                    "url": url, "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                    "allowed_updates": ["channel_post", "edited_channel_post", "message", "edited_message"],
                    "max_connections": 1, "drop_pending_updates": False,
                })
                if result is not True:
                    raise CommandError("Telegram did not confirm registration.")
                self.stdout.write(self.style.SUCCESS("Webhook registered; pending updates preserved."))
            else:
                result = bot_api("getWebhookInfo", {})
                # Do not echo arbitrary upstream errors or credential-bearing URLs.
                self.stdout.write(f"registered={bool(result.get('url'))}; pending={int(result.get('pending_update_count', 0))}; last_error_date={result.get('last_error_date', 'none')}")
        except TelegramTransportError:
            raise CommandError("Telegram API unavailable or rejected the request. Check the token and outbound access; credentials were not printed.") from None
