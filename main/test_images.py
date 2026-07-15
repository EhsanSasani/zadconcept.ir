from io import BytesIO, StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import SimpleTestCase, TestCase, override_settings
from PIL import Image

from .management.commands.optimize_images import create_width_variant
from .models import Category, Product, responsive_image_srcset


class ResponsiveImageTests(SimpleTestCase):
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
