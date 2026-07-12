# ZAD V1 Final Polish

## Local verification

```powershell
py manage.py check
py manage.py makemigrations --check --dry-run
py manage.py migrate
py manage.py test
py manage.py collectstatic --noinput
```

## Production deployment

Back up the PostgreSQL database and media first, then from `/var/www/zad`:

```bash
source /var/www/zad/venv/bin/activate
python manage.py check
python manage.py migrate
python manage.py collectstatic --noinput
sudo systemctl restart gunicorn
sudo systemctl reload nginx
```

Use the actual Gunicorn service name if it is not `gunicorn`.

## July 2026 follow-up

- Published workshops remain visible while ongoing and disappear only after `end_at`.
- Internal page heroes support multiple ordered slides, autoplay, controls, responsive images, and per-slide copy.
- Canonical product URLs include section, category, and product slugs; legacy product URLs permanently redirect.
- Workshop URLs live under `/workshops/`; legacy `/events/` URLs permanently redirect.
- `PageContentBlock` exposes structured page-section copy in admin without changing the existing layout.
- Migration `0011_pagecontentblock` must be applied before opening the updated site.

## Required manual QA

- Create Flower, Bakery, Gift, Category, Event, Home Hero, and Site Hero records with JPG/PNG/WEBP images.
- Verify the first 12 catalog cards, category switching during a slow request, automatic next-page loading, the manual load-more button, and Quick View.
- Verify multiple active homepage slides remain visible and ordered.
- Verify product gallery ordering and the promote-to-cover admin action.
- Verify Workshop editable copy, future-event cards, empty state, and registration/contact links.
- Check desktop and mobile layouts with the production media files.

## Commit hygiene

Do not commit databases, `.env`, production exports, patches, backups, generated static files, media, screenshots, `__pycache__`, or `.pyc` files.
