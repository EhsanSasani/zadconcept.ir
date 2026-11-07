# Staff panel user-journey and UX corrections — 2026-11-07

Independent continuation of `codex/panel-behavior-debug`, based on
`86ada927f8b5671c9a988eb351ac311937a08e7e`. Commerce/onboarding remains separate.

## Reproduced defects

1. Mobile product sorting discarded the active CUSTOM/DAILY quick filter. Mobile
   choices now use the existing server-side AJAX table navigation. Search, range,
   other-table sort parameters and history remain intact. Replaced mobile menus
   return keyboard focus to their summary; desktop sorts focus their header.
2. Long deleted-product receipts expanded the auto-sized third grid track until
   other tracks collapsed. Price/status cells covered the photo and product link;
   real clicks were intercepted. Three bounded tracks and wrapping prevent this.
   Long deletion receipts occupy a full-width row. This is a layout correction,
   not a pointer-events/z-index workaround.
3. Florist price formatting silently changed `۱۲٫۵` to `125`, removed negative
   signs and stripped text. Invalid amounts now remain visible and cannot pass
   browser validation; correcting them clears the error. Valid Persian/Arabic
   digits and grouping retain selection/caret behavior. Server validation remains
   authoritative and unchanged.
4. A material conversion error was below the viewport while autofocus selected
   the unrelated material name. Shared form enhancement reveals closed sections
   and focuses the actionable server error after autofocus, unless the user has
   deliberately interacted. Hidden metadata is skipped; non-field errors remain
   focusable. Broken help/error description IDs in material/account fields,
   Sales, waste formsets and florist profile were repaired. AJAX florist field
   errors now reference their actual messages.
5. Restored private notes remained inside a closed optional section. Nonempty
   restored notes are now revealed for review; the same submission UUID and image
   remain available for retries.
6. Settings offered jump links to missing empty sections. Only existing issue/
   missing-product sections receive jump links, including the zero-results case.
7. A historical invoice saved correctly but redirected to today's list, where it
   was invisible. Normal receipt save now opens the saved document, including an
   idempotent retry. Submit-and-another retains its existing behavior.

## Validation and boundaries

- Full PostgreSQL16: 869 run, 867 passed, 2 skipped, on an exclusive disposable
  container. Full SQLite: 869 run, 868 passed, 1 skipped, in-memory test database.
- Complete JavaScript inventory: 131 passed, 0 failed, across ten files.
- All 48 released staff screens checked under actual synthetic Manager, Sales,
  Procurement, Florist and technical Admin roles at 320/390/1440px: no bad HTTP
  statuses, page exceptions, root overflow, duplicate IDs or broken label/help
  references in the final audit. An additional pointer-level audit exercised
  180 target centers and 12 real photo dialogs across product, florist and metric
  tables at 320/390/768/1440px, including deleted receipts. No target interception.
- Real manager journeys cover menus/Escape, custom Jalali ranges, charts, quick
  filters, AJAX sorting/history, photo/status confirmation, canceled actions and
  exact post-save URL/filter/scroll restoration. Sales checks cover cancel/confirm,
  Persian final price, audit and return context. Procurement checks cover material
  return, upload preview, historical receipt/detail/void and dynamic waste rows.
  Florist/account journeys cover image removal/submission, private notes, access
  boundaries, account creation/search and existing password-login routing.
- Synthetic network failures preserve photo/data/UUID and unlock retry. A local
  test-only middleware replaced a successful committed upload response with 503;
  retry returned the same product and UUID with exactly two requests and one
  database record. Middleware/fault flags are output artifacts, never deployed.
- Django checks, migration consistency, migration plan and whitespace checks
  passed. No models, migrations, settings, authentication, role definitions or
  operational service implementations changed. The only view change is the
  reproduced successful receipt redirect.

Raw before/after evidence is retained under `output/panel-ux-audit-20261107/`,
excluded from source control. Earlier failed audit selectors and the browser
multipart-forwarding simulation were corrected in test artifacts and are not
misrepresented as application defects. The response-loss case uses a local
server-side fault to preserve the real multipart upload.

Runtime deployment is scoped to the reviewed files with verified before/after
hashes, backup and rollback. Only four staff assets are collected: panel-forms.js,
studio.js, team.js and panel-dark.css. Other static-manifest entries and existing
server customizations must be preserved. No migration, application DB operation,
media replacement, provider request or Commerce activation belongs to deployment.

The report does not claim every possible UX anomaly is eliminated. Chromium on
Windows with responsive viewports was exercised; physical phones, virtual mobile
keyboards, Safari/VoiceOver and authenticated production workflows were not.
