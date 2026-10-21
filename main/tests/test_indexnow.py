import json
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from django.utils import timezone


MODULE = "main.management.commands.submit_indexnow"
ORIGIN = "https://www.zadconcept.ir"


@override_settings(INDEXNOW_KEY="test-key-12345", ZAD_SITE_URL=ORIGIN,
                   INDEXNOW_ENDPOINT="https://api.indexnow.org/indexnow")
class IndexNowIncrementalTests(SimpleTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.state = Path(self.directory.name) / "state.json"
        self.previous = {"last_success_at": "2026-10-20T00:00:00+00:00",
                         "known_urls": [ORIGIN + "/old/", ORIGIN + "/kept/"]}
        self.state.write_text(json.dumps(self.previous), encoding="utf-8")
        self.settings_override = override_settings(INDEXNOW_STATE_FILE=self.state)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)

    def run_command(self, **options):
        call_command("submit_indexnow", stdout=StringIO(), **options)

    def test_new_and_removed_urls_are_not_lost_without_timestamp_changes(self):
        with patch(MODULE + ".all_public_urls", return_value={ORIGIN + "/new/", ORIGIN + "/kept/"}), \
             patch(MODULE + ".changed_public_urls", return_value={ORIGIN + "/private/"}), \
             patch(MODULE + ".Command.submit_batch") as submit:
            self.run_command()
        self.assertEqual(submit.call_args.args[0], [ORIGIN + "/new/", ORIGIN + "/old/"])
        self.assertEqual(json.loads(self.state.read_text())["known_urls"],
                         [ORIGIN + "/kept/", ORIGIN + "/new/"])

    def test_cursor_precedes_snapshot_and_only_advances_after_success(self):
        marker = timezone.now()
        order = []
        with patch(MODULE + ".timezone.now", side_effect=lambda: order.append("cursor") or marker), \
             patch(MODULE + ".all_public_urls", side_effect=lambda: order.append("snapshot") or {ORIGIN + "/new/"}), \
             patch(MODULE + ".changed_public_urls", return_value=set()), \
             patch(MODULE + ".Command.submit_batch"):
            self.run_command()
        self.assertEqual(order, ["cursor", "snapshot"])
        self.assertEqual(json.loads(self.state.read_text())["last_success_at"], marker.isoformat())

    def test_failed_submission_preserves_retry_state(self):
        with patch(MODULE + ".all_public_urls", return_value={ORIGIN + "/new/"}), \
             patch(MODULE + ".changed_public_urls", return_value=set()), \
             patch(MODULE + ".Command.submit_batch", side_effect=CommandError("failed")):
            with self.assertRaises(CommandError):
                self.run_command()
        self.assertEqual(json.loads(self.state.read_text()), self.previous)

    def test_dry_run_does_not_submit_or_write_state(self):
        with patch(MODULE + ".all_public_urls", return_value={ORIGIN + "/new/"}), \
             patch(MODULE + ".changed_public_urls", return_value=set()), \
             patch(MODULE + ".Command.submit_batch") as submit:
            self.run_command(dry_run=True)
        submit.assert_not_called()
        self.assertEqual(json.loads(self.state.read_text()), self.previous)

    def test_batches_only_include_canonical_origin(self):
        with patch(MODULE + ".all_public_urls", return_value={ORIGIN + "/a/", ORIGIN + "/b/", "https://example.org/"}), \
             patch(MODULE + ".Command.submit_batch") as submit:
            self.run_command(all=True, batch_size=2)
        urls = [url for call in submit.call_args_list for url in call.args[0]]
        self.assertEqual(len(urls), 4)
        self.assertTrue(all(url.startswith(ORIGIN + "/") for url in urls))
        self.assertTrue(all(len(call.args[0]) <= 2 for call in submit.call_args_list))
