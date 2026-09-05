import logging
import signal
import time
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from ...models import StoryClip
from ...video_pipeline import (
    StaleVideoUpload,
    VideoProcessingError,
    claim_next_story_clip,
    mark_story_clip_failed,
    process_story_clip,
)

logger = logging.getLogger("main.story_video")


class Command(BaseCommand):
    help = "Process queued ZAD story videos with FFmpeg."

    def add_arguments(self, parser):
        parser.add_argument(
            "--once",
            action="store_true",
            help="Exit when the current queue is empty.",
        )
        parser.add_argument(
            "--poll-interval",
            type=float,
            default=3.0,
            help="Seconds between empty-queue checks in worker mode.",
        )
        parser.add_argument(
            "--max-jobs",
            type=int,
            default=0,
            help="Stop after this many jobs; zero means unlimited.",
        )
        parser.add_argument(
            "--retry-stale-minutes",
            type=int,
            default=30,
            help="Requeue processing rows older than this many minutes.",
        )

    def handle(self, *args, **options):
        stop_requested = False

        def request_stop(signum, frame):
            nonlocal stop_requested
            stop_requested = True

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

        stale_minutes = max(1, options["retry_stale_minutes"])

        def recover_stale_clips():
            stale_before = timezone.now() - timedelta(minutes=stale_minutes)
            stale = StoryClip.objects.filter(
                processing_status=StoryClip.ProcessingStatus.PROCESSING,
                updated_at__lt=stale_before,
            )
            failed = stale.filter(source_video="").update(
                processing_status=StoryClip.ProcessingStatus.FAILED,
                processing_error="فایل اصلی ویدئو برای ادامه پردازش در دسترس نیست.",
                processed_at=timezone.now(),
                updated_at=timezone.now(),
            )
            recovered = stale.exclude(source_video="").update(
                processing_status=StoryClip.ProcessingStatus.QUEUED,
                processing_error=(
                    "پردازش قبلی ناتمام ماند و دوباره در صف قرار گرفت."
                ),
                updated_at=timezone.now(),
            )
            if recovered:
                self.stdout.write(f"Requeued {recovered} stale story clip(s).")
            if failed:
                self.stdout.write(f"Failed {failed} stale story clip(s) without source media.")

        recover_stale_clips()
        next_stale_check = time.monotonic() + min(60, stale_minutes * 60)

        processed_jobs = 0
        poll_interval = min(max(options["poll_interval"], 0.25), 60.0)

        while not stop_requested:
            close_old_connections()
            if time.monotonic() >= next_stale_check:
                recover_stale_clips()
                next_stale_check = time.monotonic() + min(
                    60,
                    stale_minutes * 60,
                )
            clip_id = claim_next_story_clip()
            if clip_id is None:
                if options["once"]:
                    break
                time.sleep(poll_interval)
                continue

            source_name = (
                StoryClip.objects.filter(pk=clip_id)
                .values_list("source_video", flat=True)
                .first()
                or ""
            )
            try:
                clip = process_story_clip(clip_id)
            except StaleVideoUpload:
                logger.info("Skipped stale story clip upload: clip_id=%s", clip_id)
            except VideoProcessingError as error:
                mark_story_clip_failed(clip_id, source_name, str(error))
                self.stderr.write(f"Story clip {clip_id} failed: {error}")
            except Exception:
                logger.exception("Unexpected story processing failure: clip_id=%s", clip_id)
                mark_story_clip_failed(
                    clip_id,
                    source_name,
                    "خطای غیرمنتظره‌ای هنگام پردازش رخ داد؛ دوباره تلاش کنید.",
                )
                self.stderr.write(f"Story clip {clip_id} failed unexpectedly.")
            else:
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Story clip {clip.pk} ready: "
                        f"{clip.video_width}x{clip.video_height}, "
                        f"{clip.duration_seconds:.2f}s"
                    )
                )

            processed_jobs += 1
            if options["max_jobs"] and processed_jobs >= options["max_jobs"]:
                break

        self.stdout.write("Story video worker stopped.")
