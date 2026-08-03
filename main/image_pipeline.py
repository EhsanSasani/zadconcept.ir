"""Safe, high-quality image normalization for Django admin uploads."""

import logging
from io import BytesIO
from pathlib import Path

from django.core.checks import Error, Tags, register
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils.text import slugify
from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError, features

logger = logging.getLogger(__name__)

try:
    from pillow_heif import register_heif_opener

    # Only the primary, display-ready photo is needed. Ignoring thumbnails,
    # depth maps, and auxiliary HDR maps keeps daily admin uploads predictable.
    register_heif_opener(
        thumbnails=False,
        depth_images=False,
        aux_images=False,
    )
except (ImportError, OSError, RuntimeError) as error:
    HEIF_SUPPORT_AVAILABLE = False
    HEIF_SUPPORT_ERROR = error
else:
    HEIF_SUPPORT_AVAILABLE = True
    HEIF_SUPPORT_ERROR = None


# Nginx accepts a 20 MiB request body. A decimal 20 MB file leaves enough room
# inside that limit for multipart/form-data headers and boundaries.
MAX_UPLOAD_BYTES = 20_000_000
MAX_IMAGE_PIXELS = 60_000_000
MAX_IMAGE_DIMENSION = 3200
MAX_ICC_PROFILE_BYTES = 1024 * 1024
WEBP_QUALITY = 88
WEBP_METHOD = 6

# Pillow reports a decoded format, not necessarily the filename extension.
# MPO is included because several phone portrait/stereo JPEGs are detected as
# MPO even when their filename ends in .jpg or .jpeg.
ALLOWED_INPUT_FORMATS = frozenset(
    {
        "AVIF",
        "BMP",
        "GIF",
        "HEIF",
        "JPEG",
        "MPO",
        "PNG",
        "TIFF",
        "WEBP",
    }
)
FORMAT_ALIASES = {
    "HEIC": "HEIF",
    "JPE": "JPEG",
    "JFIF": "JPEG",
    "JPG": "JPEG",
}
ANIMATED_INPUT_FORMATS = frozenset({"AVIF", "GIF", "PNG", "WEBP"})
HEIF_BRANDS = frozenset(
    {
        b"heic",
        b"heix",
        b"hevc",
        b"hevx",
        b"heim",
        b"heis",
        b"hevm",
        b"hevs",
        b"mif1",
        b"msf1",
    }
)


class ImageUploadError(ValueError):
    """A safe, user-facing image validation failure."""


@register(Tags.files)
def check_admin_image_pipeline(app_configs, **kwargs):
    """Make missing production codecs visible during ``manage.py check``."""

    errors = []
    if not features.check("webp"):
        errors.append(
            Error(
                "Pillow cannot encode WebP images.",
                hint="Install a Pillow build with WebP support before deployment.",
                id="main.E101",
            )
        )
    if not HEIF_SUPPORT_AVAILABLE:
        detail = f" ({HEIF_SUPPORT_ERROR})" if HEIF_SUPPORT_ERROR else ""
        errors.append(
            Error(
                f"HEIC/HEIF image support is unavailable{detail}.",
                hint="Install pillow-heif==1.5.0 in the ZAD virtualenv.",
                id="main.E102",
            )
        )
    return errors


def _webp_filename(filename):
    original_name = Path(str(filename or "image")).name
    stem = Path(original_name).stem
    safe_stem = slugify(stem, allow_unicode=False).strip("-")[:80] or "image"
    return f"{safe_stem}.webp"


def _canonical_format(source_format):
    source_format = str(source_format or "").strip().upper()
    return FORMAT_ALIASES.get(source_format, source_format)


def _has_alpha(image):
    return "A" in image.getbands() or (
        image.mode == "P" and "transparency" in image.info
    )


def _is_disallowed_animation(image, source_format):
    frame_count = getattr(image, "n_frames", 1)
    is_animated = bool(getattr(image, "is_animated", False) or frame_count > 1)
    # Multi-picture JPEG/MPO, HEIF bursts/spatial photos, and multi-page TIFFs
    # are still photographs. Their primary frame is the intended web image.
    return is_animated and source_format in ANIMATED_INPUT_FORMATS


def _looks_like_heif(uploaded_file):
    """Detect common ISO-BMFF HEIC/HEIF brands without trusting MIME/name."""

    try:
        position = uploaded_file.tell()
        uploaded_file.seek(0)
        header = uploaded_file.read(64)
        uploaded_file.seek(position)
    except (AttributeError, OSError, ValueError):
        return False

    if len(header) < 12 or header[4:8] != b"ftyp":
        return False
    return any(
        header[offset : offset + 4] in HEIF_BRANDS
        for offset in range(8, len(header) - 3, 4)
    )


def _looks_like_flat_graphic(image, source_format, has_alpha):
    """Use lossless WebP for palettes and genuinely low-colour graphics."""

    if image.mode in {"1", "P"} or source_format == "GIF":
        return True
    if source_format != "PNG" and not has_alpha:
        return False

    probe = image.copy()
    try:
        probe.thumbnail((256, 256), Image.Resampling.LANCZOS)
        sample = probe.convert("RGBA" if has_alpha else "RGB")
        try:
            colours = sample.getcolors(maxcolors=257)
            return colours is not None and len(colours) <= 256
        finally:
            sample.close()
    finally:
        probe.close()


def _validated_icc_profile(icc_profile):
    """Return a bounded, parseable ICC profile or ``None``."""

    if isinstance(icc_profile, memoryview):
        icc_profile = icc_profile.tobytes()
    if isinstance(icc_profile, bytearray):
        icc_profile = bytes(icc_profile)
    if not isinstance(icc_profile, bytes):
        return None
    if not icc_profile or len(icc_profile) > MAX_ICC_PROFILE_BYTES:
        return None

    try:
        ImageCms.ImageCmsProfile(BytesIO(icc_profile))
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
        return None
    return icc_profile


def _convert_cmyk_to_srgb(image, icc_profile):
    """Convert a profiled CMYK photo to sRGB; return ``None`` if invalid."""

    if image.mode != "CMYK":
        return None
    icc_profile = _validated_icc_profile(icc_profile)
    if not icc_profile:
        return None

    try:
        source_profile = ImageCms.ImageCmsProfile(BytesIO(icc_profile))
        destination_profile = ImageCms.createProfile("sRGB")
        converted = ImageCms.profileToProfile(
            image,
            source_profile,
            destination_profile,
            outputMode="RGB",
        )
        destination_bytes = ImageCms.ImageCmsProfile(destination_profile).tobytes()
    except (ImageCms.PyCMSError, OSError, TypeError, ValueError):
        return None
    return converted, destination_bytes


def _prepare_pixels_for_webp(image, has_alpha):
    """Return WebP-compatible pixels and a compatible ICC profile."""

    source_mode = image.mode
    icc_profile = image.info.get("icc_profile")
    cmyk_conversion = _convert_cmyk_to_srgb(image, icc_profile)
    if cmyk_conversion is not None:
        return cmyk_conversion

    output_mode = "RGBA" if has_alpha else "RGB"
    converted = image.convert(output_mode)

    # RGB-family profiles remain valid after resizing/conversion. Do not attach
    # grayscale or CMYK profiles to RGB pixels.
    compatible_profile = (
        _validated_icc_profile(icc_profile)
        if source_mode in {"P", "RGB", "RGBA"}
        else None
    )
    return converted, compatible_profile


def normalize_admin_image(uploaded_file):
    """Validate a new upload and return a clean, high-quality WebP upload.

    Existing ``FieldFile`` instances and clear-checkbox values are returned
    untouched, so editing a product without choosing a new photo never reads or
    re-encodes the stored image. Filename extensions and browser MIME values are
    deliberately ignored; only successfully decoded content is trusted.
    """

    if not uploaded_file or not hasattr(uploaded_file, "content_type"):
        return uploaded_file

    try:
        size = uploaded_file.size
    except (AttributeError, OSError, ValueError):
        raise ImageUploadError(
            "فایل تصویر خوانده نشد؛ لطفاً دوباره آن را انتخاب کنید."
        )

    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise ImageUploadError("فایل تصویر خالی یا نامعتبر است.")
    if size > MAX_UPLOAD_BYTES:
        raise ImageUploadError("حجم فایل اصلی نباید بیشتر از ۲۰ مگابایت باشد.")

    is_heif_container = _looks_like_heif(uploaded_file)
    if is_heif_container and not HEIF_SUPPORT_AVAILABLE:
        raise ImageUploadError(
            "پشتیبانی HEIC/HEIF روی سرور فعال نیست؛ با مدیر فنی تماس بگیرید."
        )

    try:
        uploaded_file.seek(0)
        with Image.open(uploaded_file) as source_image:
            source_format = _canonical_format(source_image.format)
            if source_format not in ALLOWED_INPUT_FORMATS:
                detected = source_format or "نامشخص"
                logger.warning(
                    "Rejected admin image format: detected=%r name=%r mime=%r",
                    detected,
                    getattr(uploaded_file, "name", None),
                    getattr(uploaded_file, "content_type", None),
                )
                raise ImageUploadError(
                    "این فرمت تصویری پشتیبانی نمی‌شود؛ از JPG/JPEG، PNG، WebP، "
                    "HEIC/HEIF، AVIF، TIFF، BMP یا GIF ثابت استفاده کنید. "
                    f"فرمت تشخیص‌داده‌شده: {detected}."
                )

            if _is_disallowed_animation(source_image, source_format):
                raise ImageUploadError(
                    "تصاویر متحرک قابل آپلود نیستند؛ یک عکس ثابت انتخاب کنید."
                )

            width, height = source_image.size
            if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
                raise ImageUploadError(
                    "ابعاد تصویر بیش از حد بزرگ است؛ حداکثر ۶۰ مگاپیکسل مجاز است."
                )

            # Full decoding catches damaged files before any database/storage
            # write. exif_transpose also handles normal phone rotation safely.
            source_image.load()
            normalized_image = ImageOps.exif_transpose(source_image)

            try:
                if (
                    normalized_image.width > MAX_IMAGE_DIMENSION
                    or normalized_image.height > MAX_IMAGE_DIMENSION
                ):
                    normalized_image.thumbnail(
                        (MAX_IMAGE_DIMENSION, MAX_IMAGE_DIMENSION),
                        Image.Resampling.LANCZOS,
                    )

                has_alpha = _has_alpha(normalized_image)
                use_lossless = _looks_like_flat_graphic(
                    normalized_image,
                    source_format,
                    has_alpha,
                )
                webp_image, icc_profile = _prepare_pixels_for_webp(
                    normalized_image,
                    has_alpha,
                )
                try:
                    output = BytesIO()
                    save_options = {
                        "format": "WEBP",
                        "method": WEBP_METHOD,
                    }
                    if use_lossless:
                        save_options.update(
                            {
                                "lossless": True,
                                "quality": 100,
                                "exact": True,
                            }
                        )
                    else:
                        save_options.update(
                            {
                                "quality": WEBP_QUALITY,
                                "alpha_quality": 100,
                            }
                        )
                    if icc_profile:
                        save_options["icc_profile"] = icc_profile

                    # EXIF/XMP are intentionally not copied. This removes GPS,
                    # device, edit-history, and stale orientation metadata.
                    webp_image.save(output, **save_options)
                    output_bytes = output.getvalue()
                finally:
                    webp_image.close()
            finally:
                normalized_image.close()

        with Image.open(BytesIO(output_bytes)) as check_image:
            if check_image.format != "WEBP":
                raise ImageUploadError("خروجی WebP معتبر ساخته نشد.")
            check_image.load()
    except ImageUploadError:
        raise
    except Image.DecompressionBombError as error:
        raise ImageUploadError(
            "ابعاد تصویر بیش از حد بزرگ است؛ حداکثر ۶۰ مگاپیکسل مجاز است."
        ) from error
    except (
        EOFError,
        MemoryError,
        OSError,
        RuntimeError,
        SyntaxError,
        UnidentifiedImageError,
        ValueError,
    ) as error:
        logger.warning(
            "Admin image decode/encode failed: name=%r mime=%r error=%s",
            getattr(uploaded_file, "name", None),
            getattr(uploaded_file, "content_type", None),
            type(error).__name__,
        )
        raise ImageUploadError(
            "این فایل یک تصویر سالم و قابل تبدیل نیست؛ لطفاً یک عکس معتبر انتخاب کنید."
        ) from error
    finally:
        try:
            uploaded_file.seek(0)
        except (AttributeError, OSError, ValueError):
            pass

    return SimpleUploadedFile(
        _webp_filename(uploaded_file.name),
        output_bytes,
        content_type="image/webp",
    )
