# ZAD homepage story system

The homepage story rail is managed entirely from Django Admin. A story is one
ring in the rail; each story can contain multiple ordered video clips. Only
active, scheduled stories with at least one successfully optimized clip are
rendered publicly.

## Publishing workflow

1. Open **استوری‌ها** in Admin and create a story.
2. Optionally upload a square cover. Without one, the first ready clip poster
   becomes the ring cover automatically.
3. Add one or more clips, set their order, caption, and optional CTA, then save.
4. Each original video enters **در صف بهینه‌سازی**. The background worker
   validates its real media metadata, encodes it, creates a poster, and marks it
   **آماده انتشار**.
5. Refresh the Admin page to see the preview, output dimensions, duration, and
   size. A ready active clip appears on the homepage automatically.

The viewer supports tap/click navigation, segmented progress, press-and-hold
pause, mute, keyboard controls, story-to-story swipes, swipe-down close,
preloading, and reduced-motion preferences. Videos start muted so mobile
autoplay remains reliable.

## Optimization contract

- Accepted originals: MP4, MOV, M4V, WebM
- Maximum upload size: 100,000,000 bytes by default
- Maximum duration: 45 seconds by default
- Video output: MP4, H.264 High, `yuv420p`, maximum 1080×1920, maximum 30 fps
- Audio output: AAC stereo, 96 kbps
- Streaming: `faststart` metadata at the beginning of the MP4
- Poster: WebP generated near the beginning of the optimized clip
- Metadata: stripped from the public output
- Concurrency: one low-priority worker on the current 2-core/4-GB VPS

The worker publishes the video and poster only after both outputs validate. By
default, a successfully processed original is deleted. A failed original is
retained so the operator can use **تلاش دوباره برای بهینه‌سازی**. Uploading a
new source resets the clip to the queue without exposing a half-built output.

## Production installation

Back up the production database and media directory before applying a release.
Then, from `/var/www/zad/app`:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
.venv/bin/python manage.py check
.venv/bin/python manage.py migrate
.venv/bin/python manage.py collectstatic --noinput
```

Install the worker definition and reload systemd:

```bash
sudo cp deploy/systemd/zad-story-video-worker.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now zad-story-video-worker.service
sudo systemctl status zad-story-video-worker.service
```

Merge the supplied Nginx rules into the active virtual host, then validate and
reload it:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

The Nginx configuration intentionally returns 404 for
`/media/stories/source/`. Never remove this rule: original uploads are worker
inputs and are not public assets. Django also rejects that route as a
defense-in-depth fallback. The `/admin/` limit is 110 MiB so a
100,000,000-byte multipart upload can pass through; Django enforces the exact
application limit.

## Operational checks

```bash
# Process the existing queue and exit (safe maintenance command)
.venv/bin/python manage.py process_story_videos --once

# Follow the persistent worker
sudo journalctl -u zad-story-video-worker.service -f

# Confirm raw media is blocked publicly; expected response is 404
curl -I https://www.zadconcept.ir/media/stories/source/probe.mp4
```

If a clip fails, its Admin row contains a safe Persian error. Check the worker
journal for the technical FFmpeg diagnostic, correct or replace the original,
and queue it again. Rows left in `processing` after an interrupted worker are
automatically requeued after 30 minutes; the worker checks this condition
periodically, so a fast service restart cannot leave a clip stuck forever.

## Environment settings

All settings have production-safe defaults and corresponding entries in
`.env.example`:

- `STORY_VIDEO_MAX_UPLOAD_BYTES`
- `STORY_VIDEO_MAX_DURATION_SECONDS`
- `STORY_VIDEO_PROCESS_TIMEOUT_SECONDS`
- `STORY_VIDEO_KEEP_ORIGINALS`
- `STORY_VIDEO_CRF`
- `STORY_VIDEO_FFMPEG_PRESET`
- `STORY_VIDEO_FFMPEG_THREADS`
- `STORY_FFMPEG_BINARY`
- `STORY_FFPROBE_BINARY`

Keep `STORY_VIDEO_FFMPEG_THREADS=1` on the current VPS. A lower CRF improves
quality but increases file size and CPU time; 24 is the intended balance for
short portrait stories.
