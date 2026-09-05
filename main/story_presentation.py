import hashlib

from django.db.models import Prefetch

from .models import Story, StoryClip


def _media_url(field_file):
    if not field_file or not field_file.name:
        return ""
    try:
        return field_file.url
    except (AttributeError, OSError, ValueError):
        return ""


def _public_story_version(story, clips):
    """Version only public story state, never queued/failed background work."""
    payload = [f"story:{story.pk}:{story.updated_at.isoformat()}"]
    payload.extend(
        f"clip:{clip.pk}:{clip.updated_at.isoformat()}" for clip in clips
    )
    return hashlib.blake2s("|".join(payload).encode("utf-8"), digest_size=8).hexdigest()


def get_home_story_presentations(*, story_limit=12, clip_limit=20):
    ready_clips = (
        StoryClip.objects.filter(
            is_active=True,
            processing_status=StoryClip.ProcessingStatus.READY,
        )
        .exclude(optimized_video="")
        .exclude(poster_image="")
        .order_by("sort_order", "id")
    )
    stories = (
        Story.objects.visible()
        .filter(clips__in=ready_clips)
        .distinct()
        .prefetch_related(Prefetch("clips", queryset=ready_clips, to_attr="public_clips"))[:story_limit]
    )

    presentations = []
    for story in stories:
        public_clip_objects = list(story.public_clips[:clip_limit])
        clips = []
        version_clip_objects = []
        for clip in public_clip_objects:
            video_url = _media_url(clip.optimized_video)
            poster_url = _media_url(clip.poster_image)
            if not video_url or not poster_url:
                continue
            version_clip_objects.append(clip)
            clips.append(
                {
                    "id": clip.pk,
                    "title": clip.title,
                    "caption": clip.caption,
                    "video_url": video_url,
                    "poster_url": poster_url,
                    "duration_ms": clip.duration_ms,
                    "cta_text": clip.cta_text,
                    "cta_url": clip.cta_url,
                }
            )

        if not clips:
            continue

        cover_url = _media_url(story.cover_image) or clips[0]["poster_url"]
        presentations.append(
            {
                "id": story.pk,
                "title": story.title,
                "version": _public_story_version(story, version_clip_objects),
                "cover_url": cover_url,
                "clips": clips,
            }
        )
    return presentations
