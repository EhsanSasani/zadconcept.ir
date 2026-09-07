# ZAD Moments + Discover — scoped mock implementation

Baseline: `c9df23bdbc935c919ba476f79bee64164fff260d`, branch
`feat/home-v2-story-redesign`. Reference: the user-supplied September 7, 2026
desktop/mobile mock. This contract applies only to Moments + Discover.

## Protected components

Do not change Hero media, sequence, geometry or motion; header, notice bar,
search, menu, navigation; the story viewer's image/video pipeline, cube motion,
hold-to-pause, admin ownership or data. Preserve all homepage sections following
Discover. No migrations, settings changes, commits or remote writes in this patch.

## Composition

- One ivory surface with rounded top corners, slightly overlapping the preceding
  Hero without modifying it; centered Discover title and subtitle.
- Persian Moments title on the right, orange letterspaced English on the left.
- Real, admin-managed story covers in a left-to-right horizontal scroll rail.
  Unseen rings orange; seen rings gray. Play badges visually suppressed here only.
- Native horizontal touch/trackpad scroll plus keyboard focus navigation.
  Rail arrow buttons removed by user request. There are no fake stories just to
  fill the mock. With no stories, Discover remains visible independently.
- Four category links, in physical left-to-right order: Flower Studio, Wedding,
  Sweet Bar, Workshops. Labels remain live selectable HTML, not baked into photos.
- Mobile: two columns, 12px outside gutters, no desktop decoration. Tablet
  761–1023px: two wider columns and 36px gutters. Desktop 1024px+: four columns,
  max 1280px content, leaf-shadow texture, bottom-left navy wave, brand closing.
- Colors: ivory `#fbf7f0`, navy `#073e52`, decorative orange `#ff713d`.
  Small orange text uses darker `#b83d13` for contrast on ivory.
  Orange action circles use `#f76532` to keep white arrow contrast above 3:1.
- Reuse local Estedad, Plus Jakarta Sans and Cormorant Garamond. The decorative
  English handwritten flourish uses a system script-font stack, so its precise
  appearance is platform-dependent.
- Honor reduced motion. Native zoom stays enabled. Longer story titles can wrap.

## Files and adjustment points

- `main/static/main/css/pages/home/moments-discover.css`: scoped layout, breakpoints,
  palette, cover size and spacing (`--moments-*` variables).
- `main/templates/main/components/home_moments_discover.html`: category order,
  copy, image references, ornament and closing signature.
- `main/static/main/js/pages/home/moments-rail.js`: independent rail controls;
  never changes playback or cube timing in the existing viewer.

## Images and provenance

Generated with the built-in image tool using the mock as a visual reference.
These are new matching photographs, not byte-identical source photos extracted
from the mock. The mock does not provide the original font or separate photo files.
All final assets live in `main/static/main/img/home/moments/`. Photographs have
640px and 960px square WebP variants; the surface is desktop-only. Existing static
images and uploaded/admin media are not overwritten.

Prompt specifications used (one generation per asset):

- Flowers: recreate the mock's Flower Studio photo as a square editorial image:
  white ceramic vase, peach/orange roses, white cosmos and tiny daisies, airy
  branches, warm beige plaster studio, natural side sunlight; no UI/text.
- Wedding: recreate the mock's wedding photo: bride cropped chest-to-hips,
  ivory veil/dress, cascading white and cream bouquet with pale peach accents,
  warm beige light; no face, UI or text.
- Bakery: recreate the mock's Sweet Bar photo: white three-tier buttercream cake,
  peach-orange roses and daisies, scattered petals, rustic pale table,
  warm taupe background and side sunlight; no UI/text.
- Workshops: recreate the mock's workshop photo: close crop of florist hands
  and dark apron arranging orange roses, white cosmos/daisies on a warm worktable,
  realistic hands, golden side light; no face, UI or text.
- Surface: flat warm ivory background, subtle blurred botanical shadows at
  the outer edges, peach cosmos/daisies confined to bottom-right, empty center;
  no typography, cards, logos, border or navy wave (the wave is native SVG).

## Verification contract

Before final visual approval, inspect 320, 375, 390, 440, 768, 1024, 1280 and
1440px, plus phone landscape and enlarged text. Check one/six/twelve highlights,
long names, no stories, beginning/end controls, keyboard focus, reduced motion,
opening/closing image and video stories, and cube/hold behavior. Confirm no
horizontal page overflow and no regressions outside this wrapper.

Unit checks: `node --test main/tests/moments-rail.test.cjs` and
`python manage.py test main.tests.test_home_moments main.tests.test_stories`.
Follow with `python manage.py check` and `git diff --check`.

Current environment limitation: the cloud browser rejects localhost
(`ERR_BLOCKED_BY_CLIENT`), and dependency installation was not approved, so
responsive browser verification and Django execution cannot be claimed here.
Python syntax, Node behavioral tests, asset checks and forward/reverse patch
validation are separate checks and do not substitute for device verification.

## Follow-up: arrowless rail + mobile Hero cover

The user approved changing mobile Hero scroll behavior only. Its dimensions,
artwork, sequence and all navbar/menu rules remain unchanged. A scoped mobile
sticky override beats the later portrait-only relative-position rule in
hero-policy.css. Following sections receive the same opaque backgrounds as
desktop so they cover the Hero. No scroll handlers or synthetic spacers are added.
Desktop Hero behavior is unchanged. Rail arrows and their spacing/handlers are
removed on all widths; viewer previous/next controls are preserved. Verify the
cover effect on a real phone in portrait and landscape after applying the follow-up.
