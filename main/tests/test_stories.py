import shutil
import subprocess
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import skipUnless

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Story, StoryClip
from main.story_presentation import get_home_story_presentations
from main.video_pipeline import (
    VideoUploadError,
    claim_next_story_clip,
    probe_video,
    process_story_clip,
    validate_story_video_upload,
)


class StoryVisibilityTests(TestCase):
    def setUp(self):
        self.now = timezone.now()

    def test_visible_queryset_honors_active_and_schedule(self):
        visible = Story.objects.create(title="همین امروز", sort_order=2)
        always_visible = Story.objects.create(title="همیشه", sort_order=1)
        Story.objects.create(title="خاموش", is_active=False)
        Story.objects.create(
            title="آینده",
            starts_at=self.now + timedelta(hours=1),
        )
        Story.objects.create(
            title="تمام‌شده",
            ends_at=self.now - timedelta(seconds=1),
        )

        result = list(Story.objects.visible(at=self.now))

        self.assertEqual(result, [always_visible, visible])

    def test_invalid_schedule_is_rejected(self):
        story = Story(
            title="زمان‌بندی اشتباه",
            starts_at=self.now,
            ends_at=self.now,
        )

        with self.assertRaises(ValidationError):
            story.full_clean()

    def test_story_cta_rejects_unsafe_scheme_and_protocol_relative_url(self):
        story = Story.objects.create(title="ایمن")

        for unsafe_url in ("javascript:alert(1)", "//example.com/path"):
            clip = StoryClip(
                story=story,
                cta_text="مشاهده",
                cta_url=unsafe_url,
            )
            with self.subTest(url=unsafe_url), self.assertRaises(ValidationError):
                clip.full_clean()


class StoryPresentationTests(TestCase):
    def setUp(self):
        self.story = Story.objects.create(title="پشت صحنه زاد", sort_order=1)
        self.ready_clip = StoryClip.objects.create(
            story=self.story,
            title="چیدمان امروز",
            caption="از انتخاب گل تا بسته‌بندی",
            optimized_video="stories/videos/demo/story-video.mp4",
            poster_image="stories/posters/demo/story-poster.webp",
            processing_status=StoryClip.ProcessingStatus.READY,
            duration_ms=8_400,
        )

    def test_presentation_uses_first_poster_as_cover(self):
        presentations = get_home_story_presentations()

        self.assertEqual(len(presentations), 1)
        self.assertEqual(presentations[0]["title"], self.story.title)
        self.assertEqual(
            presentations[0]["cover_url"],
            self.ready_clip.poster_image.url,
        )
        self.assertEqual(
            presentations[0]["clips"][0]["video_url"],
            self.ready_clip.optimized_video.url,
        )

    def test_unready_and_inactive_clips_are_never_exposed(self):
        queued = StoryClip.objects.create(
            story=self.story,
            title="فایل خام",
            source_video="stories/source/private/raw.mov",
        )
        inactive = StoryClip.objects.create(
            story=self.story,
            title="آماده اما خاموش",
            optimized_video="stories/videos/demo/inactive.mp4",
            poster_image="stories/posters/demo/inactive.webp",
            processing_status=StoryClip.ProcessingStatus.READY,
            is_active=False,
        )

        response = self.client.get(reverse("index"))
        body = response.content.decode()

        self.assertEqual(response.status_code, 200)
        self.assertIn(self.ready_clip.optimized_video.url, body)
        self.assertIn("data-story-viewer", body)
        self.assertNotIn(queued.source_video.url, body)
        self.assertNotIn(inactive.optimized_video.url, body)

    def test_story_without_ready_clip_is_not_rendered(self):
        empty_story = Story.objects.create(title="هنوز آماده نیست")
        StoryClip.objects.create(
            story=empty_story,
            source_video="stories/source/private/pending.mp4",
        )

        titles = [item["title"] for item in get_home_story_presentations()]

        self.assertNotIn(empty_story.title, titles)

    def test_raw_story_source_route_is_always_not_found(self):
        response = self.client.get("/media/stories/source/private/raw.mov")

        self.assertEqual(response.status_code, 404)


class StoryUploadValidationTests(TestCase):
    def test_supported_short_upload_passes_request_time_validation(self):
        upload = SimpleUploadedFile(
            "clip.MOV",
            b"small-placeholder",
            content_type="video/quicktime",
        )

        self.assertIs(validate_story_video_upload(upload), upload)

    @override_settings(STORY_VIDEO_MAX_UPLOAD_BYTES=10)
    def test_oversized_upload_is_rejected_before_storage(self):
        upload = SimpleUploadedFile(
            "clip.mp4",
            b"x" * 11,
            content_type="video/mp4",
        )

        with self.assertRaises(VideoUploadError):
            validate_story_video_upload(upload)

    def test_unsupported_extension_is_rejected(self):
        upload = SimpleUploadedFile(
            "clip.avi",
            b"not-a-video",
            content_type="video/x-msvideo",
        )

        with self.assertRaises(VideoUploadError):
            validate_story_video_upload(upload)


class StoryAdminTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin_user = get_user_model().objects.create_superuser(
            username="story-admin",
            email="story@example.com",
            password="strong-test-password",
        )

    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.media_override = override_settings(
            MEDIA_ROOT=Path(self.temporary_directory.name) / "media"
        )
        self.media_override.enable()
        self.client.force_login(self.admin_user)

    def tearDown(self):
        self.media_override.disable()
        self.temporary_directory.cleanup()

    def test_story_admin_exposes_inline_upload_and_processing_guidance(self):
        response = self.client.get(reverse("admin:main_story_add"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کلیپ‌های این استوری")
        self.assertContains(response, "video/mp4")
        self.assertContains(response, "وارد صف")

    def test_story_clip_admin_is_available(self):
        response = self.client.get(reverse("admin:main_storyclip_changelist"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "کلیپ‌های استوری")

    def test_inline_admin_upload_creates_a_queued_clip(self):
        response = self.client.post(
            reverse("admin:main_story_add"),
            data={
                "title": "آپلود از پنل",
                "slug": "admin-upload",
                "is_active": "on",
                "sort_order": "1",
                "clips-TOTAL_FORMS": "1",
                "clips-INITIAL_FORMS": "0",
                "clips-MIN_NUM_FORMS": "0",
                "clips-MAX_NUM_FORMS": "1000",
                "clips-0-title": "کلیپ پنل",
                "clips-0-caption": "",
                "clips-0-cta_text": "",
                "clips-0-cta_url": "",
                "clips-0-sort_order": "0",
                "clips-0-is_active": "on",
                "clips-0-source_video": SimpleUploadedFile(
                    "phone-video.mp4",
                    b"request-time-placeholder",
                    content_type="video/mp4",
                ),
                "_save": "ذخیره",
            },
        )

        self.assertEqual(response.status_code, 302)
        clip = StoryClip.objects.get(story__slug="admin-upload")
        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.QUEUED)
        self.assertTrue(clip.source_video.name.startswith("stories/source/"))


@skipUnless(
    shutil.which("ffmpeg") and shutil.which("ffprobe"),
    "FFmpeg is required for the story optimizer integration test.",
)
class StoryVideoPipelineIntegrationTests(TestCase):
    def setUp(self):
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.media_root = Path(self.temporary_directory.name) / "media"
        self.override = override_settings(
            MEDIA_ROOT=self.media_root,
            STORY_VIDEO_KEEP_ORIGINALS=False,
            STORY_VIDEO_MAX_DURATION_SECONDS=45,
            STORY_VIDEO_FFMPEG_THREADS=1,
        )
        self.override.enable()

    def tearDown(self):
        self.override.disable()
        self.temporary_directory.cleanup()

    def _make_source_video(self):
        path = Path(self.temporary_directory.name) / "source.mp4"
        subprocess.run(
            [
                shutil.which("ffmpeg"),
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-y",
                "-f",
                "lavfi",
                "-i",
                "color=c=0xd7aa86:s=360x640:r=24:d=1",
                "-f",
                "lavfi",
                "-i",
                "anullsrc=channel_layout=stereo:sample_rate=44100",
                "-shortest",
                "-t",
                "1",
                "-c:v",
                "libx264",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                str(path),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        return path

    def test_real_video_is_claimed_optimized_postered_and_published(self):
        source_path = self._make_source_video()
        story = Story.objects.create(title="تست پردازش")
        with source_path.open("rb") as source_handle:
            clip = StoryClip.objects.create(
                story=story,
                title="یک ثانیه",
                source_video=File(source_handle, name="camera-upload.mp4"),
            )
        raw_name = clip.source_video.name

        claimed_id = claim_next_story_clip()
        with self.captureOnCommitCallbacks(execute=True):
            processed = process_story_clip(claimed_id)

        self.assertEqual(claimed_id, clip.pk)
        self.assertEqual(
            processed.processing_status,
            StoryClip.ProcessingStatus.READY,
        )
        self.assertFalse(processed.source_video)
        self.assertEqual(processed.video_width, 360)
        self.assertEqual(processed.video_height, 640)
        self.assertGreater(processed.duration_ms, 0)
        self.assertGreater(processed.optimized_size_bytes, 0)
        self.assertTrue(processed.optimized_video.storage.exists(processed.optimized_video.name))
        self.assertTrue(processed.poster_image.storage.exists(processed.poster_image.name))
        self.assertFalse(processed.optimized_video.storage.exists(raw_name))

        metadata = probe_video(processed.optimized_video.path)
        self.assertEqual(metadata["codec_name"], "h264")
        self.assertEqual(metadata["pix_fmt"], "yuv420p")

        video_bytes = Path(processed.optimized_video.path).read_bytes()
        self.assertGreater(video_bytes.find(b"mdat"), video_bytes.find(b"moov"))

        with processed.poster_image.open("rb") as poster_handle:
            self.assertEqual(poster_handle.read(4), b"RIFF")

    def test_worker_marks_invalid_media_failed_and_keeps_source_for_retry(self):
        story = Story.objects.create(title="فایل خراب")
        clip = StoryClip.objects.create(
            story=story,
            source_video=SimpleUploadedFile(
                "broken.mp4",
                b"this-is-not-a-video",
                content_type="video/mp4",
            ),
        )
        source_name = clip.source_video.name
        stdout = StringIO()
        stderr = StringIO()

        call_command(
            "process_story_videos",
            once=True,
            stdout=stdout,
            stderr=stderr,
        )
        clip.refresh_from_db()

        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.FAILED)
        self.assertEqual(clip.processing_attempts, 1)
        self.assertTrue(clip.source_video)
        self.assertTrue(clip.source_video.storage.exists(source_name))
        self.assertTrue(clip.processing_error)
        self.assertIn("failed", stderr.getvalue())

    def test_worker_recovers_a_stale_processing_clip(self):
        story = Story.objects.create(title="پردازش قطع‌شده")
        clip = StoryClip.objects.create(
            story=story,
            source_video=SimpleUploadedFile(
                "interrupted.mp4",
                b"this-is-not-a-video",
                content_type="video/mp4",
            ),
            processing_status=StoryClip.ProcessingStatus.PROCESSING,
        )
        StoryClip.objects.filter(pk=clip.pk).update(
            processing_status=StoryClip.ProcessingStatus.PROCESSING,
            updated_at=timezone.now() - timedelta(minutes=2),
        )
        stdout = StringIO()

        call_command(
            "process_story_videos",
            once=True,
            retry_stale_minutes=1,
            stdout=stdout,
            stderr=StringIO(),
        )
        clip.refresh_from_db()

        self.assertIn("Requeued 1 stale story clip", stdout.getvalue())
        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.FAILED)
        self.assertEqual(clip.processing_attempts, 1)
