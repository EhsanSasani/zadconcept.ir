# ZAD: media and interface review — 2026-09-09

Base: `cc0035e` with `zad-admin-modern-cc0035e.patch` already applied.
This patch does not contain that earlier admin patch or any production media/database.

## Changes

- Every concrete image field in `main` (currently 24, including the generated video poster) passes through the same content-aware normalizer when a **new file object** is saved. Admin field validation returns readable field errors before saving. HEIC/HEIF, AVIF and the existing supported still formats become bounded WebP; orientation, transparency and valid color profiles are handled, EXIF/XMP removed. Existing stored paths and ordinary edits are untouched.
- Product covers and galleries create 520/1040/1600px variants after successful transaction commit, without upscaling. The public srcset helper uses the variants that exist. Custom import code using bulk SQL/`bulk_create` must normalize files explicitly; assigning an existing path is intentionally not treated as a new upload.
- `optimize_images` discovers database image fields instead of maintaining an incomplete model list. Its default is referenced media only. Originals and untracked files are preserved. Already normalized WebP is not recompressed. Concurrent editor changes are not overwritten. Source static conversion is now explicit with `--include-static`.
- Video processing rejects invalid/non-finite durations and oversized imported sources; it verifies source, media type, processing state and attempt before publishing a result or marking a failure. Replacing a video under the same input name queues a new job. Media-type changes persist all derived fields together. Story and Wedding use the same worker, with concurrency one.
- A separate **فیلم‌های عروسی** admin entry manages standalone Wedding films. These use the existing StoryClip storage/worker through a proxy and do not appear on Home. Choose the film in **تنظیمات صفحه عروسی → گالری تصاویر → فیلم گالری**; the related + button can add one. Staff require the new proxy-model permissions through their existing groups.
- The Wedding gallery includes a responsive editorial placeholder until the chosen film is active and ready. Ready films use processed MP4/poster, native controls, `playsinline`, and `preload="none"`; no autoplay. Page hiding pauses playback. Existing gallery photos remain.
- Shared overlay handling restores scroll position and previous keyboard focus, keeps the background inert, supports nested image viewers, and follows the visible viewport when the mobile keyboard opens. Product dialog CSS was repaired and consolidated. Detail pages no longer clip at tablet widths, and their gallery thumbnails select real images; the full-screen viewer includes previous/next controls.
- Public/admin typography shares local Estedad, Vazirmatn, Plus Jakarta Sans and Cormorant Garamond definitions. Invalid legacy font-family names were replaced. Icon fonts remain independent.
- Home receives a screen-reader H1 without changing its approved visible layout. Three superseded/unreferenced Home assets were removed. Stale tests were updated to the approved Home/Workshop/Admin behavior. Historical migration tests bypass only the unrelated irreversible0027 cleanup on their empty disposable database, leaving production migrations unchanged.

## Apply locally

```powershell
git apply --check --binary .\zad-final-review-after-admin.patch
git apply --binary .\zad-final-review-after-admin.patch
git diff --check
python manage.py check
python manage.py migrate --plan
python manage.py migrate
python manage.py test
node --test ops/tests/overlays.test.cjs
```

Migration `0030_wedding_film` adds the optional gallery film relationship, allows standalone video rows, and introduces WeddingFilm proxy permissions. It does not delete or backfill production content. Before rolling back this schema after uploading standalone films, those records need a deliberate data plan; do not blindly reverse the migration on populated data.

## Existing images

Review the inventory, then run the media conversion. Neither command deletes original images:

```powershell
python manage.py optimize_images --media-only --dry-run
python manage.py optimize_images --media-only
```

Missing/corrupt/oversized files are reported and skipped, so inspect the command's `failed` count. Conversion of historical production media is not performed by applying this source patch.

## Uploading the Wedding film

Add the film in the new admin entry, then select it on Wedding settings. The configured defaults are 100 MB and 45 seconds (same existing video pipeline). Current configured limits appear next to the upload field. Keep Nginx's existing source-media deny rule and video upload body limit; see `docs/story-system.md`.

If no worker is running locally, process the queue in a separate terminal:

```powershell
python manage.py process_story_videos --once
```

Production uses the existing dedicated worker service; restart it with the application during the normal manual deployment. Keep one worker and FFmpeg thread setting at one on the current VPS.

## Verification and remaining visual gate

Django system/migration checks, complete Django suite, native FFmpeg integration, JavaScript syntax checks and overlay lifecycle unit tests were run. Patch application is checked on the exact pre-patch combined baseline.

The cloud browser returns `net::ERR_BLOCKED_BY_CLIENT` for localhost. This is **not** visual verification. Before production deployment, inspect 360/390/768/1024/1440px and phone landscape: menu/search keyboard opening, repeated open/close, product long text, absent/multiple photos, nested viewer Escape/focus return, Wedding placeholder/ready video, admin add/change/view-only forms, and reduced-motion mode. Browser screenshots and device performance were not measured in this environment.
