"""Durable, single-worker video optimization for homepage stories."""

import json
import logging
import shutil
import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory

from django.conf import settings
from django.core.checks import Tags, Warning, register
from django.core.files import File
from django.db import connection, transaction
from django.db.models import F
from django.utils import timezone
from PIL import Image, UnidentifiedImageError

from .models import StoryClip

logger = logging.getLogger("main.story_video")

ALLOWED_VIDEO_EXTENSIONS = frozenset({".mp4", ".mov", ".m4v", ".webm"})
DEFAULT_MAX_UPLOAD_BYTES = 100_000_000
DEFAULT_MAX_DURATION_SECONDS = 45.0
DEFAULT_PROCESS_TIMEOUT_SECONDS = 600


class VideoUploadError(ValueError):
    """A safe validation error suitable for the Persian admin interface."""


class VideoProcessingError(RuntimeError):
    """A safe processing error suitable for the Persian admin interface."""


class StaleVideoUpload(RuntimeError):
    """The source changed while a worker was encoding an older upload."""


def _ffmpeg_binary():
    return getattr(settings, "STORY_FFMPEG_BINARY", "ffmpeg")


def _ffprobe_binary():
    return getattr(settings, "STORY_FFPROBE_BINARY", "ffprobe")


def _max_upload_bytes():
    return int(
        getattr(settings, "STORY_VIDEO_MAX_UPLOAD_BYTES", DEFAULT_MAX_UPLOAD_BYTES)
    )


def _max_duration_seconds():
    return float(
        getattr(
            settings,
            "STORY_VIDEO_MAX_DURATION_SECONDS",
            DEFAULT_MAX_DURATION_SECONDS,
        )
    )


def validate_story_video_upload(uploaded_file):
    """Perform cheap request-time checks; FFprobe remains the source of truth."""

    if not uploaded_file or not hasattr(uploaded_file, "content_type"):
        return uploaded_file

    try:
        size = uploaded_file.size
        filename = uploaded_file.name
    except (AttributeError, OSError, ValueError) as error:
        raise VideoUploadError(
            "فایل ویدئو خوانده نشد؛ لطفاً دوباره آن را انتخاب کنید."
        ) from error

    if not isinstance(size, int) or isinstance(size, bool) or size < 1:
        raise VideoUploadError("فایل ویدئو خالی یا نامعتبر است.")
    if size > _max_upload_bytes():
        limit_mb = _max_upload_bytes() // 1_000_000
        raise VideoUploadError(
            f"حجم فایل اصلی نباید بیشتر از {limit_mb} مگابایت باشد."
        )

    extension = Path(str(filename or "")).suffix.lower()
    if extension not in ALLOWED_VIDEO_EXTENSIONS:
        raise VideoUploadError(
            "فرمت ویدئو باید MP4، MOV، M4V یا WebM باشد."
        )
    return uploaded_file


@register(Tags.files)
def check_story_video_pipeline(app_configs, **kwargs):
    """Expose missing worker binaries without breaking non-video dev work."""

    warnings = []
    for binary, error_id in (
        (_ffmpeg_binary(), "main.W201"),
        (_ffprobe_binary(), "main.W202"),
    ):
        if not shutil.which(binary):
            warnings.append(
                Warning(
                    f"Story video binary is unavailable: {binary}",
                    hint="Install FFmpeg before starting the story video worker.",
                    id=error_id,
                )
            )
    return warnings


def _run_media_command(arguments, *, timeout=None):
    timeout = timeout or int(
        getattr(
            settings,
            "STORY_VIDEO_PROCESS_TIMEOUT_SECONDS",
            DEFAULT_PROCESS_TIMEOUT_SECONDS,
        )
    )
    try:
        result = subprocess.run(
            arguments,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as error:
        raise VideoProcessingError(
            "ابزار بهینه‌سازی ویدئو روی سرور نصب یا قابل اجرا نیست."
        ) from error
    except subprocess.TimeoutExpired as error:
        raise VideoProcessingError(
            "زمان پردازش ویدئو بیش از حد طول کشید؛ فایل کوتاه‌تر یا سبک‌تری بارگذاری کنید."
        ) from error
    except OSError as error:
        raise VideoProcessingError("اجرای ابزار بهینه‌سازی ویدئو ناموفق بود.") from error

    if result.returncode:
        diagnostic = (result.stderr or result.stdout or "").strip()[-2000:]
        logger.warning("Story media command failed: %s", diagnostic)
        raise VideoProcessingError(
            "فایل ویدئو سالم یا قابل تبدیل نیست؛ یک خروجی MP4 یا MOV معتبر بارگذاری کنید."
        )
    return result


def probe_video(path):
    result = _run_media_command(
        [
            _ffprobe_binary(),
            "-v",
            "error",
            "-protocol_whitelist",
            "file,crypto,data",
            "-show_entries",
            "format=duration:stream=codec_type,codec_name,width,height,pix_fmt,duration",
            "-of",
            "json",
            str(path),
        ],
        timeout=30,
    )
    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError) as error:
        raise VideoProcessingError("اطلاعات فنی ویدئو قابل خواندن نیست.") from error

    video_stream = next(
        (
            stream
            for stream in payload.get("streams", [])
            if stream.get("codec_type") == "video"
        ),
        None,
    )
    if not video_stream:
        raise VideoProcessingError("فایل انتخاب‌شده جریان تصویری ندارد.")

    try:
        width = int(video_stream.get("width") or 0)
        height = int(video_stream.get("height") or 0)
        duration = float(
            payload.get("format", {}).get("duration")
            or video_stream.get("duration")
            or 0
        )
    except (TypeError, ValueError) as error:
        raise VideoProcessingError("ابعاد یا مدت ویدئو معتبر نیست.") from error

    if (
        width < 2
        or height < 2
        or width > 4096
        or height > 4096
        or width * height > 16_777_216
    ):
        raise VideoProcessingError("ابعاد ویدئو معتبر یا قابل پردازش نیست.")
    if duration <= 0:
        raise VideoProcessingError("مدت ویدئو قابل تشخیص نیست.")

    return {
        "codec_name": str(video_stream.get("codec_name") or ""),
        "pix_fmt": str(video_stream.get("pix_fmt") or ""),
        "width": width,
        "height": height,
        "duration": duration,
    }


def _materialize_source(field_file, directory):
    """Return a local path for FileSystemStorage and future remote storage."""

    try:
        source_path = Path(field_file.path)
    except (AttributeError, NotImplementedError, OSError, ValueError):
        source_path = None

    if source_path and source_path.is_file():
        return source_path

    extension = Path(field_file.name).suffix.lower() or ".video"
    local_path = Path(directory) / f"source{extension}"
    try:
        field_file.open("rb")
        with local_path.open("wb") as destination:
            shutil.copyfileobj(field_file.file, destination, length=1024 * 1024)
    except (OSError, ValueError) as error:
        raise VideoProcessingError("فایل اصلی ویدئو روی سرور قابل خواندن نیست.") from error
    finally:
        try:
            field_file.close()
        except (AttributeError, OSError, ValueError):
            pass
    return local_path


def _encode_video(source_path, output_path):
    scale_filter = (
        "scale=w='min(1080,iw)':h='min(1920,ih)':"
        "force_original_aspect_ratio=decrease:force_divisible_by=2,setsar=1"
    )
    _run_media_command(
        [
            _ffmpeg_binary(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-protocol_whitelist",
            "file,crypto,data",
            "-i",
            str(source_path),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-vf",
            scale_filter,
            "-fpsmax",
            "30",
            "-c:v",
            "libx264",
            "-preset",
            str(getattr(settings, "STORY_VIDEO_FFMPEG_PRESET", "medium")),
            "-crf",
            str(int(getattr(settings, "STORY_VIDEO_CRF", 24))),
            "-profile:v",
            "high",
            "-level",
            "4.1",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "96k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-map_metadata",
            "-1",
            "-movflags",
            "+faststart",
            "-max_muxing_queue_size",
            "1024",
            "-threads",
            str(max(1, int(getattr(settings, "STORY_VIDEO_FFMPEG_THREADS", 1)))),
            str(output_path),
        ]
    )


def _create_poster(video_path, output_path, duration):
    seek_seconds = min(max(duration * 0.15, 0.1), 2.0)
    _run_media_command(
        [
            _ffmpeg_binary(),
            "-nostdin",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-ss",
            f"{seek_seconds:.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-vf",
            "scale=w='min(1080,iw)':h='min(1920,ih)':"
            "force_original_aspect_ratio=decrease:force_divisible_by=2",
            "-c:v",
            "libwebp",
            "-quality",
            "86",
            "-compression_level",
            "6",
            str(output_path),
        ],
        timeout=60,
    )


def _validate_outputs(video_path, poster_path):
    metadata = probe_video(video_path)
    if metadata["codec_name"] != "h264":
        raise VideoProcessingError("خروجی استاندارد H.264 ساخته نشد.")
    if metadata["pix_fmt"] != "yuv420p":
        raise VideoProcessingError("فرمت رنگ خروجی برای مرورگرهای موبایل سازگار نیست.")
    if metadata["width"] > 1080 or metadata["height"] > 1920:
        raise VideoProcessingError("ابعاد خروجی بیشتر از حد مجاز است.")
    if metadata["duration"] > _max_duration_seconds() + 0.5:
        raise VideoProcessingError("مدت خروجی بیشتر از حد مجاز است.")

    try:
        with Image.open(poster_path) as poster:
            if poster.format != "WEBP":
                raise VideoProcessingError("پوستر WebP معتبر ساخته نشد.")
            poster.verify()
    except VideoProcessingError:
        raise
    except (OSError, SyntaxError, UnidentifiedImageError) as error:
        raise VideoProcessingError("پوستر ویدئو سالم ساخته نشد.") from error

    return metadata


def claim_next_story_clip():
    """Atomically claim one queued item; safe with one or multiple workers."""

    with transaction.atomic():
        queryset = StoryClip.objects.filter(
            processing_status=StoryClip.ProcessingStatus.QUEUED,
        ).exclude(source_video="").order_by("created_at", "id")

        if connection.features.has_select_for_update:
            lock_options = {}
            if connection.features.has_select_for_update_skip_locked:
                lock_options["skip_locked"] = True
            queryset = queryset.select_for_update(**lock_options)

        clip = queryset.first()
        if clip is None:
            return None

        claimed = StoryClip.objects.filter(
            pk=clip.pk,
            processing_status=StoryClip.ProcessingStatus.QUEUED,
        ).update(
            processing_status=StoryClip.ProcessingStatus.PROCESSING,
            processing_error="",
            processing_attempts=F("processing_attempts") + 1,
            updated_at=timezone.now(),
        )
        return clip.pk if claimed else None


def mark_story_clip_failed(clip_id, source_name, message):
    safe_message = str(message or "پردازش ویدئو ناموفق بود.")[:1000]
    with transaction.atomic():
        try:
            clip = StoryClip.objects.select_for_update().get(pk=clip_id)
        except StoryClip.DoesNotExist:
            return
        if clip.source_video.name != source_name:
            return
        clip.processing_status = StoryClip.ProcessingStatus.FAILED
        clip.processing_error = safe_message
        clip.processed_at = timezone.now()
        clip.save(
            update_fields=[
                "processing_status",
                "processing_error",
                "processed_at",
                "updated_at",
            ]
        )


def process_story_clip(clip_id):
    """Transcode one claimed clip and atomically publish validated outputs."""

    try:
        clip = StoryClip.objects.select_related("story").get(pk=clip_id)
    except StoryClip.DoesNotExist as error:
        raise StaleVideoUpload("Story clip was removed before processing.") from error

    source_name = clip.source_video.name
    if not source_name:
        raise VideoProcessingError("فایل اصلی برای پردازش در دسترس نیست.")

    with TemporaryDirectory(prefix="zad-story-") as temp_directory:
        source_path = _materialize_source(clip.source_video, temp_directory)
        input_metadata = probe_video(source_path)
        if input_metadata["duration"] > _max_duration_seconds():
            limit = int(_max_duration_seconds())
            raise VideoProcessingError(
                f"مدت ویدئو نباید بیشتر از {limit} ثانیه باشد."
            )

        output_path = Path(temp_directory) / "optimized.mp4"
        poster_path = Path(temp_directory) / "poster.webp"
        _encode_video(source_path, output_path)
        _create_poster(output_path, poster_path, input_metadata["duration"])
        output_metadata = _validate_outputs(output_path, poster_path)

        new_video_name = ""
        new_poster_name = ""
        old_video_name = ""
        old_poster_name = ""
        source_storage = clip.source_video.storage

        try:
            with transaction.atomic():
                try:
                    current = (
                        StoryClip.objects.select_for_update()
                        .select_related("story")
                        .get(pk=clip_id)
                    )
                except StoryClip.DoesNotExist as error:
                    raise StaleVideoUpload(
                        "Story clip was removed while processing."
                    ) from error

                if current.source_video.name != source_name:
                    raise StaleVideoUpload(
                        "A newer story video upload replaced the claimed source."
                    )

                old_video_name = current.optimized_video.name
                old_poster_name = current.poster_image.name

                with output_path.open("rb") as output_handle:
                    current.optimized_video.save(
                        "story.mp4",
                        File(output_handle),
                        save=False,
                    )
                new_video_name = current.optimized_video.name

                with poster_path.open("rb") as poster_handle:
                    current.poster_image.save(
                        "story.webp",
                        File(poster_handle),
                        save=False,
                    )
                new_poster_name = current.poster_image.name

                current.processing_status = StoryClip.ProcessingStatus.READY
                current.processing_error = ""
                current.duration_ms = max(
                    1,
                    int(round(output_metadata["duration"] * 1000)),
                )
                current.video_width = output_metadata["width"]
                current.video_height = output_metadata["height"]
                current.optimized_size_bytes = output_path.stat().st_size
                current.processed_at = timezone.now()

                keep_original = bool(
                    getattr(settings, "STORY_VIDEO_KEEP_ORIGINALS", False)
                )
                if not keep_original:
                    current.source_video = ""

                current.save(
                    update_fields=[
                        "source_video",
                        "optimized_video",
                        "poster_image",
                        "processing_status",
                        "processing_error",
                        "duration_ms",
                        "video_width",
                        "video_height",
                        "optimized_size_bytes",
                        "processed_at",
                        "updated_at",
                    ]
                )

                def clean_replaced_files():
                    for stored_name in (old_video_name, old_poster_name):
                        if stored_name and stored_name not in {
                            new_video_name,
                            new_poster_name,
                        }:
                            try:
                                source_storage.delete(stored_name)
                            except OSError:
                                logger.warning(
                                    "Could not delete replaced story media: %s",
                                    stored_name,
                                )
                transaction.on_commit(clean_replaced_files)
        except Exception:
            for stored_name in (new_video_name, new_poster_name):
                if stored_name:
                    try:
                        source_storage.delete(stored_name)
                    except OSError:
                        logger.warning(
                            "Could not clean incomplete story output: %s",
                            stored_name,
                        )
            raise

    return StoryClip.objects.get(pk=clip_id)
