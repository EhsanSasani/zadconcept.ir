# Panel consistency — phase one

Implemented locally after approval of the panel audit. No production data repair,
deployment, or schema migration is part of this change.

## Operational boundaries

- Same-day Django Admin retains catalog presentation/publication controls. Creation,
  hard deletion, stock changes, operational price/photo/name edits are unavailable;
  the changelist links authorized users to Studio creation and Sales. Existing
  records link to their Studio detail; unlinked legacy products are identified for
  review rather than assigned invented makers or invoice codes.
- A catalog save cannot reopen a sold/withdrawn/cancelled Studio record. The Sales
  restore operation remains responsible for inventory and Telegram retirement.
- Manager edits require a form version, reject sending/uncertain delivery jobs,
  synchronize public product names, queue Telegram media/caption synchronization,
  and record the actor and before/after values in the existing sales audit.
- Legacy account POSTs redirect with an explanation and do not mutate accounts.
  Account writes use the current versioned, audited editor. Limited legacy manager
  grants are retained when the role remains selected, including on reactivation.

## Counter sales and navigation

- MISC sales remain in sales totals but are excluded from florist product lists and
  photo-only private Telegram notifications. They have their own analytics row,
  separate from the physical product category “other”. Creation has its own audit
  label. Existing notification jobs/data are not rewritten by this release.
- Sales bottom navigation has three fixed destinations. Workspace switching stays
  in the common switcher/account menu; a product action sits in a separate row.
- The existing mutable-price reporting semantics and independent roles remain.

## Verification

- Complete Django suite: 699 tests, successful, one skipped.
- Focused follow-up including inactive manager grants and Admin boundaries: 59
  tests, successful.
- Cloudflare Worker: 45 tests, successful.
- Django system check, migration drift check and Git whitespace check passed.
- Browser verification used a separate synthetic SQLite database, with a user
  holding manager, sales and florist access. Sales home, product action and counter
  form were inspected; 320/390/768/1440px layouts had no horizontal page overflow.

Cross-panel command consolidation, universal audit events, shared date/money UI,
account lifecycle redesign and financial-history changes remain later phases.
