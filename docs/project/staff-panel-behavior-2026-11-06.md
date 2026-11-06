# Staff panel behavior release — 2026-11-06

This release fixes context loss when staff return from records and reports or save
supported forms. It is based on `3ebcd92544dc7bd9896caaae0ce4a17c96601aed`
and intentionally excludes the unshipped Commerce/onboarding branch.

## Confirmed behavior and corrections

- Sales detail lost its search, tab, page and scroll when returning to the list.
- Procurement document detail lost the filtered list context.
- Florist ranking drilldown lost the ranking query and scroll.
- A manager purchase-report drilldown returned to the writer workspace instead
  of the originating management report.
- Confirmed manager status POSTs discarded the list query, quick filter and scroll.
- Material-form Cancel discarded the search and page; supported material/account
  saves and account archive now use the same guarded return mechanism.

A shared private navigation component remembers only route and presentation
state in tab-scoped session storage, bounded to 30 pages and 30 minutes. The
state belongs to the rendered staff user and is cleared on logout/anonymous entry
or account changes. It does not store form values, server records, credentials
or tokens. Blocked storage leaves server links usable. Direct entries retain
real fallback links. Modified clicks and new tabs keep normal browser behavior.

The existing Studio reload on history/BFCache transitions remains in place to
refresh permissions and optimistic-concurrency tokens. AJAX sorting announces
its state transition so the old URL is saved before replacement. Confirmed native
form submission announces its form without replaying or intercepting the POST.
Server return hints accept only relative, resolved, explicitly allowed routes;
they do not grant access. Existing CSRF, permission, version, audit and business
operation checks remain authoritative.

## Validation

- Full JavaScript inventory: 113 passed across all eight existing/new test files.
- Full final Django suites: 860 tests on each backend; SQLite 859 passed/1 skipped,
  PostgreSQL 858 passed/2 skipped. PostgreSQL is a disposable isolated PG16 container.
- Checks and migration consistency clean; no migration source changed or added.
- Browser audit: 48 real screens, actual Manager/Sales/Procurement/Florist/Admin
  roles, at 320/390/1440px; all HTTP 200, no page exceptions or root overflow.
- Browser operations: mobile menu/Escape, Jalali custom period, chart toggles,
  quick filters, AJAX sort/history, photo dialogs, status and delete confirmation,
  Persian final-price sale/cancel/audit, material save/Cancel, receipt preview and
  submission/void, dynamic waste add/remove/save, florist image remove/submit and
  private note, account creation/search and existing single-role password routing.
- URL allowlist, CSRF and unauthorized POST regressions are included. Existing
  permissions/authentication/service implementations and historical migrations
  are not changed.

The full PostgreSQL run exposed existing test-fixture incompatibilities:
worker commands recycle connections and require TransactionTestCase rather than
TestCase's enclosing atomic block. Three worker integration classes now use real
test transactions with their existing assertions retained. The visual seed command
deliberately supports SQLite only; its two successful-seed tests are conditional
and an explicit PostgreSQL rejection regression was added. These are test-only
corrections, not changes to worker or seed behavior.

## Release boundary and recovery

Deploy only this commit's 16 runtime source files after verifying their previous
hashes. Preserve the live repository's existing customizations. Back up those
files and the static manifest, run checks and scoped collectstatic for the three
JavaScript assets, merge their entries into the existing manifest without
rebuilding unrelated public assets or using --clear, then
gracefully reload only the web Gunicorn master. No migration, database mutation,
media replacement, provider calls, Commerce activation or worker restart belongs
to this release. For rollback restore the backed-up runtime files/static manifest
and gracefully reload the same web service. Retain deployment receipts and hashes.

Raw before/after browser evidence, full test logs, source fingerprints and release
receipts remain local under `output/panel-behavior-debug-20261106/` and are excluded
from Git. Earlier onboarding files were independently rehashed: all 31 match their
existing final manifest. Synthetic account passwords and test fixtures are not
production credentials. No production customer/staff records are inspected or
used for validation.

Browser evidence is Chromium on Windows with responsive viewports; physical
mobile devices and Safari were not tested. Only the released staff workspaces
are in scope. The unshipped Commerce/Shop experience remains separate.
