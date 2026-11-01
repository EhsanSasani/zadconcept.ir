# Home and Flower Studio hero assets

Home uses the approved ZAD CONCEPT autumn triptych. Its master is
`output/hero-design/zad-concept-autumn-final.png` (1944 × 809). Runtime files are
versioned source assets under `main/static/main/img/home/hero-autumn/`:

| Width | Height | Approximate size |
| --- | --- | --- |
| 640 | 266 | 56 KB |
| 960 | 400 | 106 KB |
| 1440 | 599 | 184 KB |
| 1944 | 809 | 270 KB |

These WebP exports use quality 90 and retain the entire composition without
cropping or changing the artwork. `srcset` and `sizes="100vw"` select a suitable
file for viewport width and pixel density. Following user review, Home uses a
2:1 frame (about 20% taller than the master ratio), with a centered cover crop
that keeps the logo and three departments visible. The rounded foreground
overlaps its lower edge by 18 px on phones and 24 px on larger screens, matching
the shared page treatment. It has no slideshow script.

Phones (up to 760 px viewport width) use a dedicated art-directed 2:1 master,
`output/hero-design/zad-concept-autumn-mobile-v2.png` (1774 x 887), with a
rebalanced center sweetbar panel and complete flowerstudio/conceptstore
side scenes. WebP source widths are 640, 960, and 1536 (mobile-v2 filenames). A media-specific
`picture` source selects this artwork; the original desktop master stays in
use above 760 px. The mobile master fits the hero ratio without cropping.

Flower Studio owns the former Home worktable scene. Its three original WebP
files were moved unchanged to `main/static/main/img/flowers/hero-sequence/`.
The sequence template, styles, and script now belong to Flower Studio and keep
the original 3500 ms frame duration, 900 ms crossfade, decode-before-playback,
reduced-motion handling, and pause when hidden or outside the viewport. Its
desktop and phone framing follow the previous Home sequence geometry.

The previous managed hero records are preserved; the approved Home artwork and
Flower Studio sequence take precedence on these two pages. Other catalog hero
templates and uploaded production media are unaffected. No migration required.
