from datetime import timedelta
from io import BytesIO
from tempfile import TemporaryDirectory

from PIL import Image
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from main.models import Florist, StudioProduct


def portrait():
    stream = BytesIO()
    Image.new('RGB', (1200, 900), '#9bad91').save(stream, 'PNG')
    return SimpleUploadedFile('portrait.png', stream.getvalue(), content_type='image/png')


class StudioUITests(TestCase):
    def setUp(self):
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        override = override_settings(MEDIA_ROOT=self.media.name)
        override.enable()
        self.addCleanup(override.disable)
        self.admin = get_user_model().objects.create_superuser(username='ui-editor', password='pass')
        self.client.force_login(self.admin)
        self.florist = Florist.objects.create(name='نیوشا', code='ns')

    def test_sorting_uses_the_whole_filtered_dataset_and_keeps_pagination(self):
        for i in range(26):
            StudioProduct.objects.create(factor_code=f'UI-{i:03}', florist=self.florist,
                product_type='box', production_type='DAILY', price=(26-i)*100000,
                source='DASHBOARD', image='studio/test.webp', produced_at=timezone.now()-timedelta(days=i%4))
        url = reverse('studio_products')
        response = self.client.get(url, {'q':'UI-', 'sort':'price', 'dir':'asc'})
        prices = [int(row.price) for row in response.context['page']]
        self.assertEqual(prices, list(range(100000, 2000001, 100000)))
        self.assertContains(response, 'aria-sort="ascending"')
        self.assertContains(response, 'q=UI-')
        response = self.client.get(url, {'q':'UI-', 'sort':'price', 'dir':'asc', 'page':2})
        self.assertEqual(int(response.context['page'][0].price), 2100000)
        response = self.client.get(url, {'sort':'price', 'dir':'desc'})
        self.assertEqual(int(response.context['page'][0].price), 2600000)
        response = self.client.get(reverse('studio_florist_profile', args=[self.florist.pk]), {'sort':'factor','dir':'asc'})
        self.assertEqual(response.context['page'][0].factor_code, 'UI-000')
        self.assertEqual(self.client.get(url, {'sort':'florist__password', 'dir':'nonsense'}).status_code, 200)

    def test_product_florist_picker_is_empty_and_excludes_inactive_people(self):
        Florist.objects.create(name='غیرفعال', code='inactive', is_active=False)
        response = self.client.get(reverse('studio_product_add'))
        field = response.context['form']['florist']
        self.assertIsNone(field.value())
        self.assertEqual(field.field.label, 'فلوریست سازنده')
        self.assertEqual(list(field.field.queryset), [self.florist])
        self.assertContains(response, '<option value="" selected>فلوریست را انتخاب کنید</option>', html=True)

    def test_florist_photo_create_edit_preserve_and_clear(self):
        response = self.client.post(reverse('studio_florist_add'), {
            'name':'مهدی', 'code':'mz', 'is_active':'on', 'photo':portrait()})
        self.assertEqual(response.status_code, 302)
        florist = Florist.objects.get(code='mz')
        self.assertTrue(florist.photo.name.endswith('.webp'))
        with Image.open(florist.photo.path) as image:
            self.assertLessEqual(max(image.size), 800)
        self.assertContains(self.client.get(reverse('studio_florists')), florist.photo.url)
        self.assertContains(self.client.get(reverse('studio_florist_profile', args=[florist.pk])), florist.photo.url)
        existing_name = florist.photo.name
        self.client.post(reverse('studio_florist_edit', args=[florist.pk]), {'name':'مهدی', 'code':'mz', 'is_active':'on'})
        florist.refresh_from_db()
        self.assertEqual(florist.photo.name, existing_name)
        self.client.post(reverse('studio_florist_edit', args=[florist.pk]), {
            'name':'مهدی', 'code':'mz', 'is_active':'on', 'photo-clear':'on'})
        florist.refresh_from_db()
        self.assertFalse(florist.photo)

    def test_invalid_photo_and_missing_permission_are_rejected(self):
        response = self.client.post(reverse('studio_florist_add'), {
            'name':'نام', 'code':'bad', 'photo':SimpleUploadedFile('bad.jpg',b'not an image')})
        self.assertEqual(response.status_code, 200)
        self.assertIn('photo', response.context['form'].errors)
        self.assertFalse(Florist.objects.filter(code='bad').exists())
        staff = get_user_model().objects.create_user(username='viewer', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.post(reverse('studio_florist_add'), {
            'name':'نام', 'code':'blocked', 'photo':portrait()}).status_code, 403)
