# ZAD Refactor V2 - Canonical State

## Contract
BEFORE == AFTER.

This refactor is structural only.
No intentional changes to:
- UI / UX
- content
- URLs / redirects
- SEO semantics
- business logic
- query behavior
- forms
- database schema
- migrations

Production behavior is the source of truth.

## Git State

Golden baseline:
main @ 3f8c6b1
tag: refactor-v2-baseline-2026-08-20

Refactor code checkpoint described by this document:
refactor/zad-v2 @ e5e8715

Always confirm the live branch HEAD with:
git rev-parse --short HEAD

Old donor/reference only:
archive/refactor-v1 @ 5618c74

Never merge the old refactor branch into the current target.

## Current Boundaries

main/catalog_selectors.py
main/page_presentation.py
main/occasion_presentation.py
main/page_context.py
main/managed_heroes.py
main/views/__init__.py
main/views/international_order_views.py
main/views/event_views.py
main/views/static_page_views.py
main/views/policy_views.py
main/views/seo_views.py
main/views/hero_style_views.py
main/views/security_views.py
main/views/error_views.py
main/views/blog_views.py
main/views/home_views.py
main/views/occasion_views.py
main/views/local_seo_views.py
main/views/product_redirect_views.py
main/views/product_detail_views.py
main/views/catalog_views.py
main/views/wedding_views.py
main/views/section_views.py
main/category_presentation.py

main.views remains a compatibility facade.

Intentional implementation residue in main.views:
- _lead_rate_limited
- submit_lead_request

These remain in the facade intentionally because lead notification/test patch bindings are compatibility-sensitive. Do not extract them merely to make the facade empty.

Important preserved bindings include:
- _public_brand_copy
- INTERNATIONAL_FAQ_FA
- INTERNATIONAL_FAQ_EN
- WorkshopPageContent
- event_node
- _with_home
- _occasion_card
- index
- occasions
- international_orders
- international_orders_en
- events
- event_detail

Do not clean facade imports during unrelated refactor phases.

## Completed Structural Phases

Phase 10:
d7c6a06 refactor(views): extract international order views

Phase 11:
810cf27 refactor(events): extract event views

Phase 12:
35e03c7 refactor(views): extract static page views

Phase 13:
1716393 refactor(views): extract policy views

Phase 14:
4d6c499 refactor(views): extract SEO utility views

Phase 15:
015077b refactor(views): extract hero style view

Phase 16:
d4682f7 refactor(views): consolidate view modules into package

Phase 17:
ee183d7 refactor(views): extract security reporting view

Phase 18:
651249a refactor(views): extract error view

Phase 19:
5f4b614 refactor(views): extract blog views

Phase 20:
32b5c9d refactor(presentation): extract occasion card

Phase 21:
59e6b8d refactor(views): extract home view

Phase 22:
7ef4bc7 refactor(views): extract occasions view

Phase 23:
7b74b66 refactor(views): extract mashhad hub view

Phase 24:
7bb975d refactor(views): extract legacy product redirects

Phase 25:
a8e73a8 refactor(presentation): extract category presentation

Phase 26:
836348f refactor(views): complete local seo view family

Phase 27:
a315cf0 refactor(views): extract product detail view family

Phase 28:
85a4da5 refactor(views): extract catalog all-products family

Phase 29:
a301253 refactor(views): extract catalog subcategory family

Phase 30:
e781722 refactor(views): extract occasion detail family

Phase 31:
d2b83cb refactor(views): extract catalog landing family

Phase 32:
59c1ca3 refactor(views): extract same-day catalog view

Phase 33:
793e953 refactor(views): extract wedding view family

Phase 34:
e5e8715 refactor(views): extract legacy section view family

## Current Baselines

Django:
209 / 209 PASS

Worker:
9 / 9 PASS

Django check:
PASS

makemigrations --check --dry-run:
No changes detected

migrate --plan:
No planned migration operations

collectstatic:
339 unmodified
2 known duplicate-static conflicts:
- admin/js/cancel.js
- admin/js/popup_response.js

SEO known baseline:

Unlinked sitemap products:
- /flowers/bridal-bouquet/zad-flo-0527/
- /flowers/bridal-bouquet/zad-flo-0528/
- /flowers/bridal-bouquet/zad-flo-0537/
- /flowers/bridal-bouquet/zad-flo-0538/

Missing exactly-one-H1:
- /bakery/
- /bakery/all/
- /flowers/
- /flowers/all/
- /gifts/
- /gifts/all/

Do not fix known baseline findings inside parity refactor phases.

## Phase Protocol

Before every phase:

1. Confirm branch, HEAD and git status.
2. Read current repository code. Do not design from memory alone.
3. Define exact boundary, symbols and allowed files.
4. Add or identify characterization tests.
5. Run BEFORE tests.
6. Make the smallest mechanical move.
7. Preserve facade compatibility.
8. Keep URLconf unchanged unless explicitly required.
9. Source/AST compare moved code against pre-phase HEAD.
10. Verify remaining source functions are unchanged.
11. Run focused tests.
12. Run full gates.
13. Audit git diff.
14. Stage explicit files only.
15. Verify staged diff.
16. Commit, push and verify remote parent/file scope.

Never use:
git add .
git add -A

## Stop Conditions

Stop and re-scope if:
- dependency ownership becomes unclear
- unrelated helpers must move
- query semantics become uncertain
- migrations unexpectedly enter scope
- admin/models unexpectedly enter scope
- URL semantics need redesign
- compatibility creates cycles
- catalog/wedding/proposal/same-day concerns become entangled
- a mechanical move turns into architecture redesign
- tests need changing just to tolerate the new architecture
- unexpected files change

At a stop condition, do not push through.

## External Agent Rule

Work/Codex are reserve tools, not authority.

Use them only for genuinely ambiguous or high-coupling work such as:
- complex dependency graphs
- major catalog splits
- cyclic ownership
- migration-sensitive changes
- difficult query-equivalence analysis

Routine extraction should be done from repository evidence + tests + Git audits.

## Next Phase

Phase 35 completed final structural validation.

No further structural extraction is selected.
The refactor is closed with main.views retained as a compatibility facade and the lead flow intentionally left in place.

## Governing Principle

Reduce architectural risk while preserving production behavior exactly.

Git + tests + current repository state are authority.
Chat memory is not authority.
