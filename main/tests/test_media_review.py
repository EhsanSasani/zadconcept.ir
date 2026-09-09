"""Regression coverage for shared uploads, safe backfills and stale video jobs."""

import json
from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch

from django.apps import apps
from django.core.exceptions import ValidationError
from django.core.files import File
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.db import models
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from ..image_pipeline import normalize_admin_image, normalize_new_model_images
from ..models import Category, Product, ProductImage, Story, StoryClip, WeddingFilm, WeddingPageContent
from ..video_pipeline import (
    StaleVideoUpload,
    VideoProcessingError,
    _materialize_source,
    claim_next_story_clip,
    mark_story_clip_failed,
    probe_video,
    process_story_clip,
)
from .test_images import encoded_image, uploaded_image


class ImageNormalizationCoverageTests(SimpleTestCase):
    def test_all_concrete_image_fields_accept_the_same_content_aware_pipeline(self):
        covered = []
        source = encoded_image("PNG", size=(64, 32))
        for model in apps.get_app_config("main").get_models():
            if model._meta.proxy:
                continue
            for field in model._meta.concrete_fields:
                if not isinstance(field, models.ImageField):
                    continue
                with self.subTest(model=model._meta.label, field=field.name):
                    instance = model(**{field.name: ContentFile(source, name="import.png")})
                    normalize_new_model_images(instance)
                    normalized = getattr(instance, field.name)
                    self.assertTrue(normalized.name.endswith(".webp"))
                    with Image.open(normalized.file) as output:
                        self.assertEqual(output.format, "WEBP")
                        self.assertEqual(output.size, (64, 32))
                    covered.append((model._meta.model_name, field.name))
        self.assertGreaterEqual(len(covered), 24)
        self.assertIn(("weddingpagecontent", "hero_mobile_image"), covered)
        self.assertIn(("storyclip", "image"), covered)
        self.assertIn(("workshopgalleryimage", "image"), covered)

    def test_normalized_upload_is_encoded_only_once_across_form_and_model(self):
        normalized = normalize_admin_image(uploaded_image("photo.jpg", encoded_image("JPEG")))
        with patch("main.image_pipeline.Image.open") as image_open:
            self.assertIs(normalize_admin_image(normalized), normalized)
            instance = Category(cover_image=normalized)
            normalize_new_model_images(instance)
            self.assertIs(instance.cover_image.file, normalized)
        image_open.assert_not_called()

    def test_model_import_has_field_specific_invalid_image_error(self):
        with self.assertRaises(ValidationError) as result:
            normalize_new_model_images(Category(cover_image=ContentFile(b"broken", name="photo.jpg")))
        self.assertIn("cover_image", result.exception.message_dict)


class CatalogUploadVariantsTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.category = Category.objects.create(name="گل", slug="media-review", section="flowers")

    def test_new_cover_and_gallery_files_generate_variants_after_commit(self):
        with self.captureOnCommitCallbacks(execute=True):
            product = Product.objects.create(
                name="گل تازه", category=self.category,
                cover_image=File(BytesIO(encoded_image("JPEG", size=(1800, 900))), name="camera.jpg"),
            )
            cover = Path(product.cover_image.path)
            self.assertFalse(cover.with_name(f"{cover.stem}-520w.webp").exists())
            gallery = ProductImage.objects.create(
                product=product,
                image=uploaded_image("gallery.png", encoded_image("PNG", size=(1800, 900))),
            )
        for field_file in (product.cover_image, gallery.image):
            source = Path(field_file.path)
            self.assertEqual(source.suffix, ".webp")
            for width in (520, 1040, 1600):
                with Image.open(source.with_name(f"{source.stem}-{width}w.webp")) as image:
                    self.assertEqual(image.size, (width, width // 2))

    def test_content_edit_does_not_read_or_reencode_an_existing_image(self):
        category = Category.objects.create(name="موجود", slug="existing-ref", cover_image="legacy/photo.png")
        with patch.object(category.cover_image.storage, "open") as storage_open:
            category.description = "متن تازه"
            category.save(update_fields=["description"])
        storage_open.assert_not_called()
        self.assertEqual(category.cover_image.name, "legacy/photo.png")

    def test_excluded_new_image_is_not_written_by_partial_save(self):
        self.category.cover_image = ContentFile(b"not-an-image", name="excluded.jpg")
        self.category.description = "متن"
        self.category.save(update_fields=["description"])
        self.category.refresh_from_db()
        self.assertFalse(self.category.cover_image)


class SafeImageBackfillTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.settings_override = override_settings(MEDIA_ROOT=self.root)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.original = self.root / "legacy/wedding.png"
        self.original.parent.mkdir(parents=True)
        self.original.write_bytes(encoded_image("PNG", size=(600, 400)))
        self.page = WeddingPageContent.objects.create(
            hero_image="legacy/wedding.png", hero_mobile_image="legacy/wedding.png"
        )
        self.untracked = self.root / "legacy/untracked.jpg"
        self.untracked.write_bytes(encoded_image("JPEG"))

    def optimize(self, **kwargs):
        call_command("optimize_images", stdout=StringIO(), stderr=StringIO(), **kwargs)
        self.page.refresh_from_db()

    def test_discovers_previously_uncovered_fields_and_preserves_shared_originals(self):
        original_bytes = self.original.read_bytes()
        untracked_bytes = self.untracked.read_bytes()
        self.optimize()
        self.assertEqual(self.page.hero_image.name, self.page.hero_mobile_image.name)
        self.assertTrue(self.page.hero_image.name.endswith(".webp"))
        self.assertEqual(self.original.read_bytes(), original_bytes)
        self.assertEqual(self.untracked.read_bytes(), untracked_bytes)
        before = {path.name: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.optimize()
        after = {path.name: path.read_bytes() for path in self.root.rglob("*") if path.is_file()}
        self.assertEqual(before, after)

    def test_dry_run_does_not_write_files_or_database(self):
        before = set(self.root.rglob("*"))
        self.optimize(dry_run=True)
        self.assertEqual(self.page.hero_image.name, "legacy/wedding.png")
        self.assertEqual(set(self.root.rglob("*")), before)

    def test_backfill_does_not_overwrite_a_concurrent_editor(self):
        def replace_during_decode(*args, **kwargs):
            WeddingPageContent.objects.filter(pk=self.page.pk).update(hero_image="editor/new.webp")
            return normalize_admin_image(*args, **kwargs)
        with patch("main.management.commands.optimize_images.normalize_admin_image", side_effect=replace_during_decode):
            self.optimize()
        self.assertEqual(self.page.hero_image.name, "editor/new.webp")
        self.assertTrue(self.original.exists())

    def test_bad_image_does_not_abort_other_image_fields(self):
        bad = self.root / "legacy/broken.jpg"
        bad.write_bytes(b"not an image")
        WeddingPageContent.objects.filter(pk=self.page.pk).update(hero_image="legacy/broken.jpg")
        self.optimize()
        self.assertEqual(self.page.hero_image.name, "legacy/broken.jpg")
        self.assertTrue(self.page.hero_mobile_image.name.endswith(".webp"))
        self.assertTrue(bad.exists())


class VideoInputBoundsTests(SimpleTestCase):
    def test_ffprobe_rejects_nonfinite_and_invalid_durations(self):
        for duration in ("NaN", "inf", "-Infinity", "0", "-1"):
            payload = {"streams": [{"codec_type": "video", "width": 360, "height": 640}], "format": {"duration": duration}}
            with self.subTest(duration=duration), patch(
                "main.video_pipeline._run_media_command",
                return_value=SimpleNamespace(stdout=json.dumps(payload)),
            ), self.assertRaises(VideoProcessingError):
                probe_video("source.mp4")

    @override_settings(STORY_VIDEO_MAX_UPLOAD_BYTES=10)
    def test_worker_rejects_oversized_local_file_before_probe(self):
        with TemporaryDirectory() as directory:
            path = Path(directory) / "source.mp4"
            path.write_bytes(b"x" * 11)
            with self.assertRaises(VideoProcessingError):
                _materialize_source(SimpleNamespace(path=path, name=path.name), directory)

    @override_settings(STORY_VIDEO_MAX_UPLOAD_BYTES=10)
    def test_remote_storage_copy_is_bounded_even_without_size_metadata(self):
        class RemoteFile(File):
            @property
            def path(self):
                raise NotImplementedError
        source = RemoteFile(BytesIO(b"x" * 1000), name="source.mp4")
        with TemporaryDirectory() as directory, self.assertRaises(VideoProcessingError):
            _materialize_source(source, directory)
        self.assertTrue(source.closed)


class StaleVideoJobTests(TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.settings_override = override_settings(MEDIA_ROOT=self.directory.name)
        self.settings_override.enable()
        self.addCleanup(self.settings_override.disable)
        self.story = Story.objects.create(title="رسانه")
        self.clip = StoryClip.objects.create(story=self.story, source_video="stories/source/original.mp4")

    def test_image_rows_cannot_enter_video_queue(self):
        StoryClip.objects.filter(pk=self.clip.pk).update(media_type="image")
        self.assertIsNone(claim_next_story_clip())

    def test_failed_old_job_does_not_mutate_a_replacement_or_retry(self):
        claim_next_story_clip()
        for changes in (
            {"source_video": "stories/source/replacement.mp4"},
            {"processing_status": "queued"},
            {"media_type": "image"},
            {"processing_attempts": 2},
        ):
            with self.subTest(changes=changes):
                StoryClip.objects.filter(pk=self.clip.pk).update(
                    source_video="stories/source/original.mp4", processing_status="processing",
                    media_type="video", processing_attempts=1,
                )
                StoryClip.objects.filter(pk=self.clip.pk).update(**changes)
                mark_story_clip_failed(self.clip.pk, "stories/source/original.mp4", "old failure", expected_attempt=1)
                self.clip.refresh_from_db()
                self.assertNotEqual(self.clip.processing_status, "failed")

    def test_replaced_media_during_encoding_cannot_publish_old_video(self):
        clip_id = claim_next_story_clip()
        metadata = {"duration": 1.0, "width": 360, "height": 640}
        def switch_to_image(*args):
            StoryClip.objects.filter(pk=clip_id).update(media_type="image", processing_status="ready", image="new/photo.webp")
        with patch("main.video_pipeline._materialize_source", return_value=Path("/unused/source.mp4")), patch(
            "main.video_pipeline.probe_video", return_value=metadata
        ), patch("main.video_pipeline._encode_video", side_effect=switch_to_image), patch(
            "main.video_pipeline._create_poster"
        ), patch("main.video_pipeline._validate_outputs", return_value=metadata), self.assertRaises(StaleVideoUpload):
            process_story_clip(clip_id)
        self.clip.refresh_from_db()
        self.assertEqual(self.clip.media_type, "image")
        self.assertEqual(self.clip.image.name, "new/photo.webp")
        self.assertFalse(self.clip.optimized_video)

    def test_standalone_film_uses_the_same_queue(self):
        self.clip.delete()
        film = WeddingFilm.objects.create(source_video="stories/source/wedding.mp4")
        self.assertIsNone(film.story_id)
        self.assertEqual(claim_next_story_clip(), film.pk)

    def test_proxy_delete_keeps_shared_media_until_last_reference(self):
        image = Path(self.directory.name) / "poster.webp"
        image.write_bytes(encoded_image("WEBP"))
        first = WeddingFilm.objects.create(poster_image="poster.webp")
        second = WeddingFilm.objects.create(poster_image="poster.webp")
        with self.captureOnCommitCallbacks(execute=True):
            first.delete()
        self.assertTrue(image.exists())
        with self.captureOnCommitCallbacks(execute=True):
            second.delete()
        self.assertFalse(image.exists())
