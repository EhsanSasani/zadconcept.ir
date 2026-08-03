from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.db import models as django_models
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from PIL import Image, ImageCms

from .admin import AdminImageUploadField, CategoryAdminForm
from .image_pipeline import (
    ALLOWED_INPUT_FORMATS,
    HEIF_SUPPORT_AVAILABLE,
    MAX_IMAGE_DIMENSION,
    normalize_admin_image,
)
from .management.commands.optimize_images import create_width_variant
from .models import Category, Product, SameDayFlower, responsive_image_srcset


def encoded_image(image_format, size=(800, 600), mode="RGB", color="white", **kwargs):
    source = BytesIO()
    Image.new(mode, size, color).save(source, format=image_format, **kwargs)
    return source.getvalue()


def uploaded_image(name, content, content_type="application/octet-stream"):
    return SimpleUploadedFile(name, content, content_type=content_type)


class ResponsiveImageTests(SimpleTestCase):
    def test_phone_photo_formats_are_allowed(self):
        self.assertIn("HEIF", ALLOWED_INPUT_FORMATS)
        self.assertIn("JPEG", ALLOWED_INPUT_FORMATS)
        self.assertIn("MPO", ALLOWED_INPUT_FORMATS)

    def test_jpg_and_jpeg_names_are_accepted_regardless_of_mime(self):
        source = encoded_image("JPEG", progressive=True, quality=95)
        cases = (
            ("phone.jpg", "image/jpeg"),
            ("phone.jpeg", "image/jpeg"),
            ("PHONE.JPEG", "application/octet-stream"),
            ("edited-photo.heic", "image/heic"),
            ("photo-without-extension", "application/octet-stream"),
        )

        for filename, content_type in cases:
            with self.subTest(filename=filename, content_type=content_type):
                optimized = normalize_admin_image(
                    uploaded_image(filename, source, content_type)
                )
                self.assertTrue(optimized.name.endswith(".webp"))
                self.assertEqual(optimized.content_type, "image/webp")
                with Image.open(optimized) as image:
                    self.assertEqual(image.format, "WEBP")

    def test_admin_upload_is_normalized_to_resized_webp(self):
        source = BytesIO()
        Image.new("RGB", (3600, 1800), "white").save(source, format="PNG")

        optimized = normalize_admin_image(
            SimpleUploadedFile("large photo.png", source.getvalue(), "image/png")
        )

        self.assertEqual(optimized.name, "large-photo.webp")
        self.assertEqual(optimized.content_type, "image/webp")
        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (MAX_IMAGE_DIMENSION, 1600))

    def test_heic_and_heif_names_are_accepted_regardless_of_mime(self):
        self.assertTrue(
            HEIF_SUPPORT_AVAILABLE,
            "Install pillow-heif before running the image upload tests.",
        )
        source = encoded_image(
            "HEIF",
            size=(4032, 3024),
            color=(190, 70, 95),
            quality=95,
        )
        cases = (
            ("iphone-photo.heic", "image/heic"),
            ("iphone-photo.heif", "image/heif"),
            ("IPHONE-PHOTO.HEIC", "application/octet-stream"),
            ("edited-export.jpeg", "image/jpeg"),
        )

        for filename, content_type in cases:
            with self.subTest(filename=filename, content_type=content_type):
                optimized = normalize_admin_image(
                    uploaded_image(filename, source, content_type)
                )
                self.assertTrue(optimized.name.endswith(".webp"))
                self.assertEqual(optimized.content_type, "image/webp")
                with Image.open(optimized) as image:
                    self.assertEqual(image.format, "WEBP")
                    self.assertEqual(image.size, (MAX_IMAGE_DIMENSION, 2400))

    def test_admin_upload_uses_real_content_instead_of_claimed_mime(self):
        source = encoded_image("JPEG")

        optimized = normalize_admin_image(
            uploaded_image(
                "camera-upload.bin",
                source,
                "application/octet-stream",
            )
        )

        self.assertEqual(optimized.name, "camera-upload.webp")
        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")

    def test_edited_cmyk_jpeg_is_converted_to_rgb_webp(self):
        source = encoded_image(
            "JPEG",
            mode="CMYK",
            color=(20, 80, 120, 10),
            quality=95,
        )
        optimized = normalize_admin_image(
            uploaded_image("photoshop-export.jpeg", source, "image/jpeg")
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.mode, "RGB")

    def test_other_advertised_static_formats_are_converted(self):
        cases = (("AVIF", "avif"), ("BMP", "bmp"), ("TIFF", "tiff"))
        for image_format, extension in cases:
            with self.subTest(image_format=image_format):
                source = encoded_image(image_format)
                optimized = normalize_admin_image(
                    uploaded_image(
                        f"edited.{extension}",
                        source,
                        f"image/{extension}",
                    )
                )
                with Image.open(optimized) as image:
                    self.assertEqual(image.format, "WEBP")

    def test_admin_upload_applies_exif_orientation_before_resizing(self):
        source = BytesIO()
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (1200, 800), "white").save(
            source,
            format="JPEG",
            exif=exif,
        )

        optimized = normalize_admin_image(
            SimpleUploadedFile(
                "rotated.jpg",
                source.getvalue(),
                "image/jpeg",
            )
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.size, (800, 1200))

    def test_admin_upload_preserves_transparency_losslessly(self):
        source = BytesIO()
        Image.new("RGBA", (640, 480), (220, 30, 90, 0)).save(
            source,
            format="PNG",
        )

        optimized = normalize_admin_image(
            SimpleUploadedFile(
                "transparent.png",
                source.getvalue(),
                "image/png",
            )
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.mode, "RGBA")
            self.assertEqual(image.getpixel((0, 0))[3], 0)

    def test_admin_upload_preserves_rgb_colour_profile(self):
        source = BytesIO()
        profile = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
        Image.new("RGB", (640, 480), (220, 30, 90)).save(
            source,
            format="PNG",
            icc_profile=profile,
        )

        optimized = normalize_admin_image(
            SimpleUploadedFile(
                "profiled.png",
                source.getvalue(),
                "image/png",
            )
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.info.get("icc_profile"), profile)

    def test_webp_is_reencoded_and_private_metadata_is_removed(self):
        exif = Image.Exif()
        exif[271] = "Test Phone"
        source = encoded_image(
            "WEBP",
            size=(1000, 750),
            color=(220, 30, 90),
            quality=90,
            method=6,
            exif=exif,
        )

        optimized = normalize_admin_image(
            uploaded_image(
                "already-optimized.webp",
                source,
                "image/webp",
            )
        )

        self.assertNotEqual(optimized.read(), source)
        optimized.seek(0)
        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(len(image.getexif()), 0)

    def test_admin_upload_rejects_animated_image(self):
        source = BytesIO()
        first = Image.new("RGB", (64, 64), "white")
        second = Image.new("RGB", (64, 64), "black")
        first.save(
            source,
            format="GIF",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )

        with self.assertRaisesRegex(ValueError, "متحرک"):
            normalize_admin_image(
                SimpleUploadedFile(
                    "animated.gif",
                    source.getvalue(),
                    "image/gif",
                )
            )

    def test_admin_upload_rejects_non_image_content(self):
        with self.assertRaisesRegex(ValueError, "تصویر سالم"):
            normalize_admin_image(
                SimpleUploadedFile("not-an-image.jpg", b"not an image", "image/jpeg")
            )

    def test_admin_upload_rejects_truncated_jpeg(self):
        source = encoded_image("JPEG", progressive=True, quality=95)
        with self.assertRaisesRegex(ValueError, "تصویر سالم"):
            normalize_admin_image(
                uploaded_image("truncated.jpeg", source[:-100], "image/jpeg")
            )

    def test_admin_upload_rejects_files_over_twenty_decimal_megabytes(self):
        source = encoded_image("JPEG")
        with (
            patch("main.image_pipeline.MAX_UPLOAD_BYTES", len(source) - 1),
            self.assertRaisesRegex(ValueError, "۲۰ مگابایت"),
        ):
            normalize_admin_image(
                uploaded_image("too-large.jpg", source, "image/jpeg")
            )

    def test_admin_upload_rejects_excessive_pixel_dimensions(self):
        source = encoded_image("JPEG", size=(20, 20))
        with (
            patch("main.image_pipeline.MAX_IMAGE_PIXELS", 399),
            self.assertRaisesRegex(ValueError, "۶۰ مگاپیکسل"),
        ):
            normalize_admin_image(
                uploaded_image("too-many-pixels.jpg", source, "image/jpeg")
            )

    def test_pillow_decompression_bomb_has_a_clear_dimension_error(self):
        source = encoded_image("JPEG", size=(20, 20))
        with (
            patch(
                "main.image_pipeline.Image.open",
                side_effect=Image.DecompressionBombError("too many pixels"),
            ),
            self.assertRaisesRegex(ValueError, "۶۰ مگاپیکسل"),
        ):
            normalize_admin_image(
                uploaded_image("camera-200mp.jpg", source, "image/jpeg")
            )

    def test_invalid_icc_profile_is_removed_instead_of_breaking_upload(self):
        source = encoded_image("PNG", icc_profile=b"not-an-icc-profile")
        optimized = normalize_admin_image(
            uploaded_image("edited.png", source, "image/png")
        )

        with Image.open(optimized) as image:
            self.assertNotIn("icc_profile", image.info)

    def test_static_gif_is_accepted(self):
        source = encoded_image("GIF", mode="P", color=1)
        optimized = normalize_admin_image(
            uploaded_image("still.gif", source, "image/gif")
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")

    def test_multiframe_heif_uses_its_primary_still_image(self):
        self.assertTrue(HEIF_SUPPORT_AVAILABLE)
        source = BytesIO()
        primary = Image.new("RGB", (120, 80), "red")
        secondary = Image.new("RGB", (60, 40), "blue")
        primary.save(
            source,
            format="HEIF",
            save_all=True,
            append_images=[secondary],
            primary_index=0,
            quality=90,
        )

        optimized = normalize_admin_image(
            uploaded_image("burst.heic", source.getvalue(), "image/heic")
        )

        with Image.open(optimized) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (120, 80))

    def test_width_variant_preserves_ratio_and_does_not_upscale(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.png"
            small_variant = root / "source-520w.webp"
            oversized_variant = root / "source-2000w.webp"
            Image.new("RGB", (1800, 900), "white").save(source)

            self.assertTrue(create_width_variant(source, small_variant, 520, 82))
            with Image.open(small_variant) as image:
                self.assertEqual(image.size, (520, 260))
                self.assertEqual(image.format, "WEBP")

            self.assertFalse(
                create_width_variant(source, oversized_variant, 2000, 82)
            )
            self.assertFalse(oversized_variant.exists())

    def test_srcset_only_uses_variants_that_exist(self):
        class Storage:
            existing = {
                "products/covers/item-520w.webp",
                "products/covers/item-1040w.webp",
            }

            def exists(self, name):
                return name in self.existing

            def url(self, name):
                return f"/media/{name}"

        image_field = type(
            "ImageFieldStub",
            (),
            {"name": "products/covers/item.webp", "storage": Storage()},
        )()

        self.assertEqual(
            responsive_image_srcset(image_field),
            "/media/products/covers/item-520w.webp 520w, "
            "/media/products/covers/item-1040w.webp 1040w",
        )


class AdminImageFormIntegrationTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(
            name="Daily Flowers",
            slug="daily-flowers",
            section=Category.Section.FLOWERS,
        )
        self.user = get_user_model().objects.create_superuser(
            username="image-admin",
            email="image-admin@example.invalid",
            password="test-password",
        )
        self.request = RequestFactory().get("/admin/main/samedayflower/add/")
        self.request.user = self.user
        self.client.force_login(self.user)

    @staticmethod
    def category_data(name="Upload Test", slug="upload-test"):
        return {
            "name": name,
            "slug": slug,
            "section": Category.Section.FLOWERS,
            "description": "",
            "is_active": True,
            "sort_order": 0,
        }

    def product_data(self):
        return {
            "name": "Daily product",
            "slug": "daily-product-upload-test",
            "description": "",
            "pricing_type": Product.PricingType.INQUIRY,
            "price": "",
            "price_usd": "",
            "category": self.category.pk,
            "tags": [],
            "is_active": True,
            "publish_status": Product.PublishStatus.PUBLISHED,
            "stock_status": Product.StockStatus.IN_STOCK,
            "featured": False,
            "sort_order": 0,
        }

    def test_real_admin_form_accepts_jpg_jpeg_heic_and_heif(self):
        jpeg = encoded_image("JPEG", progressive=True, quality=95)
        heif = encoded_image("HEIF", quality=95)
        cases = (
            ("camera.jpg", jpeg, "image/jpeg"),
            ("camera.jpeg", jpeg, "application/octet-stream"),
            ("camera.heic", heif, "image/heic"),
            ("camera.heif", heif, "application/octet-stream"),
            # An editor or messenger can supply an incorrect extension/MIME.
            ("edited.heic", jpeg, "image/heif"),
            ("edited.jpeg", heif, "image/jpeg"),
        )

        for index, (filename, content, content_type) in enumerate(cases):
            with self.subTest(filename=filename, content_type=content_type):
                form = CategoryAdminForm(
                    data=self.category_data(
                        name=f"Upload Test {index}",
                        slug=f"upload-test-{index}",
                    ),
                    files={
                        "cover_image": uploaded_image(
                            filename,
                            content,
                            content_type,
                        )
                    },
                )
                self.assertTrue(form.is_valid(), form.errors.as_text())
                cleaned = form.cleaned_data["cover_image"]
                self.assertTrue(cleaned.name.endswith(".webp"))
                self.assertEqual(cleaned.content_type, "image/webp")

    def test_same_day_product_form_uses_content_aware_upload_field(self):
        model_admin = admin.site._registry[SameDayFlower]
        form_class = model_admin.get_form(self.request)

        self.assertIsInstance(
            form_class.base_fields["cover_image"],
            AdminImageUploadField,
        )
        accept = form_class.base_fields["cover_image"].widget.attrs["accept"]
        self.assertIn("image/*", accept)
        self.assertIn(".heic", accept)
        self.assertIn(".heif", accept)

        form = form_class(
            data=self.product_data(),
            files={
                "cover_image": uploaded_image(
                    "seller-edited.jpeg",
                    encoded_image("JPEG", progressive=True),
                    "application/octet-stream",
                )
            },
        )
        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(form.cleaned_data["cover_image"].content_type, "image/webp")

    def test_same_day_admin_http_post_saves_heif_as_webp(self):
        model_admin = admin.site._registry[SameDayFlower]
        same_day_tag = model_admin._ensure_same_day_tag()
        add_url = reverse("admin:main_samedayflower_add")
        get_response = self.client.get(add_url)
        self.assertEqual(get_response.status_code, 200)
        inline_prefix = get_response.context["inline_admin_formsets"][0].formset.prefix

        data = self.product_data()
        data.update(
            {
                "name": "HTTP HEIF product",
                "slug": "http-heif-product",
                "tags": [same_day_tag.pk],
                "cover_image": uploaded_image(
                    "iphone-camera.HEIF",
                    encoded_image("HEIF", quality=95),
                    "application/octet-stream",
                ),
                f"{inline_prefix}-TOTAL_FORMS": "0",
                f"{inline_prefix}-INITIAL_FORMS": "0",
                f"{inline_prefix}-MIN_NUM_FORMS": "0",
                f"{inline_prefix}-MAX_NUM_FORMS": "1000",
                "_save": "Save",
            }
        )

        with TemporaryDirectory() as media_root, override_settings(
            MEDIA_ROOT=media_root
        ):
            response = self.client.post(add_url, data)
            if response.status_code != 302:
                errors = response.context["adminform"].form.errors.as_text()
                inline_errors = [
                    {
                        "errors": item.formset.errors,
                        "non_form_errors": list(item.formset.non_form_errors()),
                    }
                    for item in response.context["inline_admin_formsets"]
                ]
                self.fail(
                    f"Admin POST returned {response.status_code}: {errors}; "
                    f"inlines={inline_errors}"
                )

            product = Product.objects.get(slug="http-heif-product")
            self.assertTrue(product.cover_image.name.endswith(".webp"))
            self.assertTrue(Path(product.cover_image.path).exists())
            with Image.open(product.cover_image.path) as image:
                self.assertEqual(image.format, "WEBP")

    def test_every_registered_admin_image_field_uses_the_pipeline_field(self):
        covered_fields = []
        for model, model_admin in admin.site._registry.items():
            form_class = model_admin.get_form(self.request)
            for model_field in model._meta.fields:
                if not isinstance(model_field, django_models.ImageField):
                    continue
                if model_field.name not in form_class.base_fields:
                    continue
                covered_fields.append(f"{model._meta.label}.{model_field.name}")
                with self.subTest(model=model._meta.label, field=model_field.name):
                    self.assertIsInstance(
                        form_class.base_fields[model_field.name],
                        AdminImageUploadField,
                    )

        self.assertGreaterEqual(len(covered_fields), 10, covered_fields)

    def test_edit_without_a_new_upload_keeps_the_existing_file(self):
        existing = Category.objects.create(
            name="Existing photo",
            slug="existing-photo",
            section=Category.Section.FLOWERS,
            cover_image="categories/existing-photo.webp",
        )
        form = CategoryAdminForm(
            data=self.category_data(
                name=existing.name,
                slug=existing.slug,
            ),
            instance=existing,
        )

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertEqual(
            form.cleaned_data["cover_image"].name,
            "categories/existing-photo.webp",
        )

    def test_clear_checkbox_removes_the_existing_file_reference(self):
        existing = Category.objects.create(
            name="Clear photo",
            slug="clear-photo",
            section=Category.Section.FLOWERS,
            cover_image="categories/clear-photo.webp",
        )
        data = self.category_data(name=existing.name, slug=existing.slug)
        data["cover_image-clear"] = "on"
        form = CategoryAdminForm(data=data, instance=existing)

        self.assertTrue(form.is_valid(), form.errors.as_text())
        self.assertFalse(form.cleaned_data["cover_image"])


class OptimizeImagesCommandTests(TestCase):
    def test_command_records_collision_safe_path_and_builds_variants(self):
        with TemporaryDirectory() as directory, override_settings(MEDIA_ROOT=directory):
            category = Category.objects.create(
                name="Bouquet",
                slug="bouquet",
                section=Category.Section.FLOWERS,
            )
            image_bytes = BytesIO()
            Image.new("RGB", (1800, 900), "white").save(image_bytes, format="PNG")
            product = Product.objects.create(
                name="Responsive test",
                category=category,
                cover_image=SimpleUploadedFile(
                    "cover.png",
                    image_bytes.getvalue(),
                    content_type="image/png",
                ),
            )

            expected = Path(directory) / "products/covers" / (
                f"product-{product.product_code}.webp"
            )
            expected.parent.mkdir(parents=True, exist_ok=True)
            Image.new("RGB", (20, 20), "white").save(expected, format="WEBP")

            call_command(
                "optimize_images",
                keep_originals=True,
                media_only=True,
                skip_static_rewrite=True,
                stdout=StringIO(),
            )
            product.refresh_from_db()

            optimized = Path(directory) / product.cover_image.name
            self.assertEqual(optimized.name, f"product-{product.product_code}-2.webp")
            self.assertTrue(optimized.exists())
            for width in (520, 1040, 1600):
                self.assertTrue(
                    optimized.with_name(f"{optimized.stem}-{width}w.webp").exists()
                )
