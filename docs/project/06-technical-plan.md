# Homepage stories and video pipeline

## Outcome

The home page gains a brand-aligned, Instagram-like story rail and full-screen
viewer. Staff manage story groups and their ordered video clips in Django
Admin. New clips are queued, transcoded by FFmpeg in a single background
worker, and become public only after the optimized MP4 and WebP poster pass
validation.

## Public experience

- Story rail sits directly below the home hero and disappears cleanly when no
  ready stories exist.
- Each circle represents one story group containing one or more ordered clips.
- Viewer supports autoplay, segmented progress, tap/click navigation, swipe,
  press-and-hold pause, mute, explicit previous/next controls, Escape/close,
  focus restoration, reduced motion, and local viewed-state rings.
- Only active, scheduled story groups with active `ready` clips are rendered.
- Video sources load on demand; the next clip receives metadata preloading.

## Content model

- `Story`: title, optional optimized cover, ordering, active flag, and optional
  publish window.
- `StoryClip`: source upload, optimized MP4, generated poster, CTA/caption,
  ordering, active flag, processing status/error, dimensions, duration, size,
  and processing timestamps.

## Processing contract

1. Admin upload is size-checked and saved under a private-by-convention source
   media prefix.
2. Saving a new source queues the clip and clears stale processing metadata.
3. `process_story_videos` claims one row at a time.
4. FFprobe rejects missing video streams, invalid dimensions, and clips longer
   than the configured limit.
5. FFmpeg outputs H.264/AAC MP4 with yuv420p, bounded 1080x1920 dimensions,
   30fps maximum, stripped metadata, and `faststart`; it also creates a WebP
   poster.
6. Outputs are probed/decoded before fields are swapped atomically to `ready`.
   Failed clips retain their source and expose a safe Persian error in Admin.
7. The source is removed after a successful swap unless runtime configuration
   explicitly retains originals.

## Runtime

- Required binaries: `ffmpeg`, `ffprobe`.
- Systemd runs one long-lived worker with graceful polling.
- Nginx permits story uploads up to the configured 100 MB ceiling while public
  media remains cacheable.

## Acceptance criteria

- No unprocessed or failed clip appears in home HTML.
- Admin exposes preview, queue/processing/ready/error states, retry, ordering,
  schedule, CTA, and activation controls in Persian.
- A real generated test video is transcoded to valid H.264 MP4 with a WebP
  poster and recorded metadata.
- Viewer works at 375px and desktop widths with mouse, touch, and keyboard.
- Existing catalog, hero, product-dialog, SEO, and no-story home behavior remain
  functional.
- Django checks, migration checks, focused tests, JavaScript syntax checks, CSS
  structure checks, and responsive browser inspection are completed.
