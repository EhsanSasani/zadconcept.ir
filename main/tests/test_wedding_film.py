from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse

from main.models import Story, StoryClip, WeddingFilm, WeddingPageContent
from main.story_presentation import get_home_story_presentations


class WeddingFilmTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = get_user_model().objects.create_superuser('film-admin', password='test-password')

    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        self.override = override_settings(MEDIA_ROOT=self.media.name)
        self.override.enable()
        self.addCleanup(self.override.disable)

    def test_empty_gallery_has_honest_placeholder_without_fake_play_control(self):
        response = self.client.get(reverse('weddings'))
        self.assertContains(response, 'wedding-film--coming')
        self.assertContains(response, 'به‌زودی، یک روایت تازه')
        self.assertNotContains(response, '<video')

    def test_only_ready_active_output_appears_in_wedding_gallery(self):
        clip = WeddingFilm.objects.create(title='فیلم مراسم', source_video='stories/source/raw.mov')
        page = WeddingPageContent.objects.create(film_clip=clip)
        response = self.client.get(reverse('weddings'))
        self.assertNotContains(response, 'stories/source/raw.mov')
        self.assertContains(response, 'wedding-film--coming')
        StoryClip.objects.filter(pk=clip.pk).update(
            processing_status=StoryClip.ProcessingStatus.READY,
            optimized_video='stories/videos/film.mp4', poster_image='stories/posters/film.webp',
        )
        response = self.client.get(reverse('weddings'))
        self.assertContains(response, 'stories/videos/film.mp4')
        self.assertContains(response, 'playsinline preload="none"')
        self.assertNotContains(response, 'stories/source/raw.mov')
        self.assertEqual(get_home_story_presentations(), [])
        clip.is_active = False
        clip.save(update_fields=['is_active'])
        self.assertNotContains(self.client.get(reverse('weddings')), 'stories/videos/film.mp4')
        clip.delete()
        page.refresh_from_db()
        self.assertIsNone(page.film_clip_id)
        self.assertContains(self.client.get(reverse('weddings')), 'wedding-film--coming')

    def test_admin_upload_is_separate_from_home_story_and_uses_existing_queue(self):
        self.client.force_login(self.admin)
        for name in ('main_weddingfilm_add', 'main_weddingpagecontent_add'):
            self.assertEqual(self.client.get(reverse('admin:' + name)).status_code, 200)
        response = self.client.post(reverse('admin:main_weddingfilm_add'), {
            'title': 'فیلم تست', 'caption': 'شرح فیلم', 'is_active': 'on', '_save': 'Save',
            'source_video': SimpleUploadedFile('clip.mp4', b'queued-for-worker-validation', 'video/mp4'),
        })
        self.assertEqual(response.status_code, 302)
        clip = WeddingFilm.objects.get()
        self.assertIsNone(clip.story_id)
        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.QUEUED)
        self.assertTrue(clip.source_video.name.startswith('stories/source/'))
        self.assertFalse(clip.is_ready)
        self.assertEqual(Story.objects.count(), 0)

    def test_invalid_upload_stays_in_admin_form(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('admin:main_weddingfilm_add'), {
            'title': 'اشتباه', 'source_video': SimpleUploadedFile('bad.exe', b'bad', 'application/octet-stream'),
        })
        self.assertEqual(response.status_code, 200)
        self.assertIn('source_video', response.context['adminform'].form.errors)
        self.assertFalse(WeddingFilm.objects.exists())

    def test_partial_media_change_clears_stale_video_fields_in_database(self):
        clip = WeddingFilm.objects.create(source_video='stories/source/previous.mp4')
        clip = StoryClip.objects.get(pk=clip.pk)
        clip.media_type = StoryClip.MediaType.IMAGE
        clip.image = 'stories/images/photo.webp'
        clip.save(update_fields=['media_type', 'image'])
        clip.refresh_from_db()
        self.assertFalse(clip.source_video)
        self.assertFalse(clip.optimized_video)
        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.READY)
        clip.media_type = StoryClip.MediaType.VIDEO
        clip.source_video = SimpleUploadedFile('next.mp4', b'next-video', 'video/mp4')
        clip.save(update_fields=['media_type', 'source_video'])
        clip.refresh_from_db()
        self.assertFalse(clip.image)
        self.assertEqual(clip.processing_status, StoryClip.ProcessingStatus.QUEUED)

    def test_same_named_new_upload_is_queued_again(self):
        clip = WeddingFilm.objects.create(source_video='stories/source/camera.mp4')
        StoryClip.objects.filter(pk=clip.pk).update(processing_status='failed', processing_attempts=3)
        clip.refresh_from_db()
        from django.core.files.base import ContentFile
        clip.source_video = ContentFile(b'new-camera-upload', name=clip.source_video.name)
        clip.save(update_fields=['source_video'])
        clip.refresh_from_db()
        self.assertEqual(clip.processing_status, 'queued')
        self.assertEqual(clip.processing_attempts, 0)

    def test_shared_local_fonts_are_loaded_by_public_and_admin_pages(self):
        self.assertContains(self.client.get(reverse('weddings')), 'foundation/fonts.css')
        self.assertContains(self.client.get(reverse('admin:login')), 'foundation/fonts.css')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get(reverse('admin:index')), 'foundation/fonts.css')
        fonts = Path(settings.BASE_DIR) / 'main/static/main/css/foundation/fonts.css'
        import re
        for url in re.findall(r'url\("([^"\)]+)"\)', fonts.read_text()):
            self.assertFalse(url.startswith(('http:', 'https:', '//')))
            self.assertTrue((fonts.parent / url).is_file(), url)
