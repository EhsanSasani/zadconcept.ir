<div align="center">
  <img src="main/static/main/img/favicon.svg" width="84" alt="ZAD logo">

  <h1>ZAD Concept Store</h1>

  <p><strong>Flowers, sweets, gifts, and gatherings &mdash; curated softly in Mashhad.</strong></p>

  <p>
    <a href="https://zadconcept.ir">Live website</a>
    &middot;
    <a href="https://github.com/EhsanSasani/zadconcept.ir/tree/v1.1.0">Version 1.1.0</a>
    &middot;
    Django 6
  </p>
</div>

---

ZAD is a digital home for a physical concept store: a calm, editorial catalog where flowers, bakery pieces, thoughtful gifts, occasions, and workshops live together.

The experience is intentionally closer to a curated lookbook than a conventional e-commerce storefront. Products are discovered visually, then orders are coordinated directly with the ZAD team.

## What lives here

- **Flowers** &mdash; bouquets, boxes, stands, jars, plants, and same-day selections
- **Bakery** &mdash; cakes, cookies, chocolates, and seasonal pieces
- **Gifts** &mdash; curated objects and gift combinations
- **Occasions** &mdash; collections for birthdays, romantic moments, congratulations, sympathy, weddings, and more
- **Workshops** &mdash; public, private, and corporate experiences
- **Journal** &mdash; editorial notes and brand stories
- **Lead coordination** &mdash; contact, Telegram, phone, and structured request forms ([Telegram integration](docs/telegram-integration.md))
- **Content management** &mdash; products, categories, tags, heroes, page copy, events, and inquiries through Django Admin

## Version 1.1.0

Version 1.1.0 is the first production-polished release of the project.

Highlights include:

- Unified responsive catalog experience across Flowers, Bakery, and Gifts
- Server-backed category filtering with resilient no-JavaScript fallbacks
- Same-day flower collection and occasion-based browsing
- Dedicated product, category, occasion, workshop, blog, and local landing pages
- Admin-managed page heroes and editable content blocks
- Persian-first localization with Tehran timezone support
- Structured metadata, breadcrumbs, sitemap, robots, and SEO-focused landing pages
- Responsive WebP media pipeline and optimized static assets
- Production deployment with PostgreSQL, Gunicorn, Nginx, and CDN delivery
- Media library optimization from roughly 293 MB to 27 MB
- Automated view, model, admin, routing, filtering, and content tests

Recommendation surfaces are intentionally paused in this release while a more deliberate relevance system is designed.

## Stack

| Layer | Technology |
| --- | --- |
| Application | Python 3, Django 6 |
| Database | SQLite for development, PostgreSQL for production |
| UI | Django Templates, HTML, CSS, vanilla JavaScript |
| Admin | Django Admin + Jazzmin |
| Images | Pillow, WebP optimization |
| Application server | Gunicorn |
| Reverse proxy | Nginx |
| Delivery | CDN-backed production domain |

## Project structure

```text
config/                     Django settings, URLs, WSGI and ASGI
main/
|-- management/             Custom management commands
|-- migrations/             Database migrations
|-- static/main/            CSS, JavaScript and brand assets
|-- templates/              Pages and reusable template partials
|-- admin.py                Admin configuration
|-- models.py               Catalog and content models
|-- views.py                Page, catalog and lead flows
`-- tests.py                Application test suite
manage.py
requirements.txt
.env.example
```

## Local setup

Clone the canonical repository:

```bash
git clone https://github.com/EhsanSasani/zadconcept.ir.git
cd zadconcept.ir
```

Create and activate a virtual environment.

Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS or Linux:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

Install dependencies and prepare the environment:

```bash
python -m pip install -r requirements.txt
cp .env.example .env
python manage.py migrate
python manage.py runserver
```

On Windows, copy `.env.example` to `.env` manually or run:

```powershell
Copy-Item .env.example .env
```

The development environment uses SQLite by default. Production uses PostgreSQL when `ENV=prod`.

## Environment

Start from [`.env.example`](.env.example). Important production settings include:

- `ENV`
- `SECRET_KEY`
- `DEBUG`
- `ALLOWED_HOSTS`
- `CSRF_TRUSTED_ORIGINS`
- `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `PGHOST`, `PGPORT`
- ZAD site, contact, social, opening-hours, and address values

Never commit `.env`, credentials, production database dumps, or private media archives.

## Tests

Run the full test suite:

```bash
python manage.py test
```

Run Django checks before a production release:

```bash
python manage.py check
python manage.py check --deploy
python manage.py migrate --plan
```

## Static files and media

Collect production static assets with:

```bash
python manage.py collectstatic --noinput
```

The repository does not track uploaded media or generated `staticfiles`. Production data and media must be backed up independently before deployment.

## Release discipline

A safe release keeps three layers separate:

1. **Code** &mdash; versioned in Git
2. **Database** &mdash; preserved and migrated in place
3. **Media** &mdash; synchronized deliberately, never replaced implicitly

The canonical production branch is `main`. The published v1.1.0 baseline is tagged as `v1.1.0`; subsequent fixes continue on `main`.

---

<div align="center">
  <p><strong>ZAD Concept Store</strong></p>
  <p>Made with care for quieter, warmer moments.</p>
</div>
