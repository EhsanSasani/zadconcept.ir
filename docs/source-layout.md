# Source layout

The public frontend follows the same domain vocabulary across templates, CSS,
JavaScript, and view modules. The folders are deliberately shallow so a page can
be found without searching a flat global bucket.

## Templates

- `main/templates/main/layout/` owns the shared document shell, header, footer,
  page hero, and flash messages.
- `main/templates/main/components/` owns reusable template fragments.
- `main/templates/main/pages/<domain>/` owns routed page templates.
- `main/templates/main/errors/` owns error responses.

## Static assets

- `main/static/main/css/foundation/` owns tokens, resets, and global responsive
  safeguards.
- `main/static/main/css/layout/` owns navigation, hero, footer, and page spacing.
- `main/static/main/css/components/` owns reusable component styling.
- `main/static/main/css/pages/<domain>/` owns page-specific presentation.
- `main/static/main/js/core/`, `layout/`, `components/`, and `pages/<domain>/`
  mirror the same responsibilities.

## Views

Public orchestration remains in `main/views/`, grouped by domain. `main.views`
is the compatibility facade used by the unchanged URL configuration.

## Tests

`main/tests/` owns the Django test suite. Test modules use responsibility-based
names and must not be added directly to the `main/` package root.

## Placement rule

When adding a routed page:

1. put its template under `templates/main/pages/<domain>/`;
2. put page-only styles under `static/main/css/pages/<domain>/`;
3. put page-only scripts under `static/main/js/pages/<domain>/`;
4. keep reusable presentation in `components/`;
5. keep shared chrome in `layout/`;
6. keep deterministic global rules in `foundation/`.

Do not create new root-level public CSS or JavaScript files. Do not add
`legacy`, `hotfix`, or `polish` buckets; fold the final behavior into its owner.

## Verification

`main.tests.test_source_layout` protects literal static references, relative CSS
assets, CSS block balance, domain-scoped placement, canonical responsive load
order, orphaned first-party CSS/JavaScript, and package-scoped test placement.
