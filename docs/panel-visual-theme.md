# Operational panel theme

`main/static/main/css/components/panel-theme.css` is the shared presentation
layer for the manager, sales, florist, procurement and workspace selection/login
pages. Each base template loads it after page styles, followed by
`main/static/main/css/components/panel-dark.css`, scoped with `panel-ui` on the body.
The public site and technical Django Admin keep their separate styles.

The workspace styles still own layout, responsive breakpoints and component
behavior. The shared dark layer unifies navy surfaces, blue actions, restrained orange
selection indicators, Estedad typography, card borders, focus rings and touch
targets. Existing status, error and warning semantics are retained. It does not
change permissions or financial calculations.

Purchase and waste entry use compact rows, optional metadata and a fixed save
bar. Enter in purchase price or waste quantity continues to the next row; saving
remains explicit. Ledger pages paginate whole days, show active daily totals and
expand to the day's documents. Voided documents remain visible but do not add to
daily totals. Waste amounts remain estimates, not material inventory balances.

Use the `--ui-*` tokens for future shared presentation changes. Procurement reports
declare their own scoped variables, so the theme explicitly maps those variables
as well. Load this stylesheet after page-specific `extra_head` styles. When
changing either shared stylesheet in a release, increment its cache version in
the five base templates. Keep dark overrides in `panel-dark.css`; do not create
separate palettes for each workspace. Compact mobile lists preserve record details
and at least 44px touch targets. Seven-day metric charts fit without horizontal
scrolling; longer periods can scroll within the chart.

Check manager summaries with large amounts, responsive tables and the mobile
drawer; sales search/product cards and counter-entry form; florist home/product
entry; procurement line entry and reports; and workspace selection. Retain 48px
form/action targets, visible keyboard focus and reduced-motion support.
