# ZAD repository guidance

## Commands

Run project commands from the repository root with the virtual environment
activated:

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py test
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
node --test ops/cloudflare/zad-telegram-relay-worker.test.mjs
```

Before handing off a scoped change, also run `git diff --check` and any focused
tests for the affected module.

## Architecture

- `config/` owns Django settings and root project configuration.
- `main/` owns the catalog, content models, Django Admin, views, templates,
  static assets, and tests.
- `ops/cloudflare/zad-telegram-relay-worker.js` is the canonical deployed
  Cloudflare Worker source for Telegram.
- `docs/telegram-integration.md` documents Telegram runtime configuration and
  deployment order.

## Project invariants

- The public site is Persian-first and RTL. Preserve existing Persian labels
  and admin language unless a requirement explicitly changes them.
- Product pricing uses `Product.pricing_type`, `price`, `price_usd`, and the
  existing display-price properties. Do not duplicate price formatting.
- Uploaded media and generated `staticfiles` are not source code. Never replace
  production media as part of a code deployment.
- Store secrets only in runtime environment configuration. Never commit `.env`,
  Telegram tokens, relay secrets, database dumps, or private media.
- Model changes require an explicit migration. Inspect the migration and run
  the migration plan before production deployment.
- Telegram users and capabilities are authorized in Django. The Worker
  validates transport secrets but must not become the permission source.
- Story videos are never served from the original admin upload. The dedicated
  worker must validate, transcode, probe, and mark a clip ready before it can
  appear publicly. Keep worker concurrency at one on the current VPS.
- Story playback is progressive MP4, mobile-first, keyboard accessible, and
  respectful of reduced motion. Do not make critical controls gesture-only.

## Change discipline

Preserve unrelated user work and keep patches scoped. Verify backend changes
with Django tests and checks. For frontend changes, run the site and inspect the
affected responsive states in a browser before calling the work complete.
