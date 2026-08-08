# ZAD Responsive UI Pass — Final Audit

## Implemented
- Central responsive/UI token layer in `main/static/main/css/responsive-system.css`.
- Fluid page gutters from 320px through wide desktop.
- Shared typography, spacing, section rhythm, control-size and content-measure tokens.
- 44px minimum target for primary/icon controls and 48px mobile primary controls.
- 48px / 16px form controls for mobile usability and iOS focus behavior.
- Safe-area support via `env(safe-area-inset-*)`.
- `svh` / `dvh` handling for mobile heroes and the product modal.
- Flex/grid `min-width: 0` safeguards and long-string overflow protection.
- Visible `:focus-visible` keyboard states.
- `prefers-reduced-motion` support in CSS and slider JS.
- Larger effective hit areas for hero/page-hero pagination dots without enlarging the visible dots.
- Responsive behavior standardized across existing button families without flattening page-specific visual variants.
- Viewport meta includes `viewport-fit=cover`.

## Final audit fixes
- Removed the overly broad `button[aria-label]` target rule that was enlarging carousel dots to 44×44 visually.
- Fixed the mobile navbar conflict between horizontal scrolling and the products dropdown.
- Changed the mobile header to content-safe sticky behavior so a wrapped notice bar cannot overlap it.
- Overrode legacy `70vh` / `720px !important` home-hero rules with bounded `svh` sizing for narrow phones and landscape.
- Kept generic fluid typography scoped to normal content surfaces so bespoke Wedding/About/Hero typography is not unintentionally flattened.
- Added 44px footer social targets and improved small mobile footer/notice text readability.
- Added mobile `dvh` product-modal sizing and safe-area bottom padding.
- Corrected product-card `sizes` from `92vw` to `46vw` for the actual two-column mobile grid, reducing unnecessary image downloads when `srcset` is available.
- Removed the nested `<main>` landmark from `wedding_collection.html` because `base.html` already owns the page `<main>`.
- Added dropdown `aria-controls` / `aria-haspopup` and Escape-to-close behavior.
- Home hero slides now expose `aria-hidden` / `aria-current`; auto-rotation is disabled for reduced-motion users and pauses during hover/focus.
- Page hero and featured-product sliders respect reduced-motion preferences.

## Media
The supplied archive intentionally omits image/media files. No image/media URL, static image path, upload field, or media reference was removed or renamed by this audit. The only image-related template change is the responsive `sizes` hint on product cards.

## Verification completed in this workspace
- Python source compilation (`compileall`) passed.
- All project JavaScript files passed `node --check`.
- All CSS files parsed with `tinycss2` with zero parse errors.
- CSS brace-balance validation passed.
- Only one `<main>` landmark remains in the template tree (`base.html`).
- Responsive stylesheet is loaded after page CSS, legacy responsive CSS, hero overrides, and navbar CSS.
- Changed-file diff was reviewed; changes are limited to the responsive system, slider/navbar accessibility behavior, product image sizing hint, and one semantic template fix.

## Environment limitation
The supplied archive has no dependency manifest and this workspace does not have Django installed, so `manage.py check` / Django tests cannot be executed here. A headless Chromium render probe was also attempted, but the sandbox Chromium process does not initialize reliably because its system DBus/zygote environment stalls; it is not counted as a passed visual test.

## Required checks in the real project venv
```bash
python manage.py check
python manage.py test main
```

After restoring the original media, visually verify at minimum: 320, 360, 390, 430, 768, 980, 1280, 1440 and 1920px widths, plus mobile landscape and 200% browser zoom. Pay special attention to CMS-controlled hero crop/object-position because those images are intentionally absent from this archive.
