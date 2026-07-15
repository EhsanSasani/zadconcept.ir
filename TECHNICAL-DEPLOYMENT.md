# تحویل فنی ZAD v1.1.3

این نسخه بدون بازطراحی UI، لایه‌های Crawl/Index، Metadata، Structured Data، Trust، International SEO، Performance، Security و CI را تکمیل می‌کند.

## پیش از انتشار

1. از PostgreSQL و پوشه `media` پشتیبان بگیرید.
2. فایل `.env.example` را با مقادیر واقعی Production تکمیل کنید.
3. مطمئن شوید `ZAD_SITE_URL` دقیقاً Origin مرجع است:

```text
https://www.zadconcept.ir
```

4. دستورات زیر را اجرا کنید:

```bash
python -m pip install -r requirements.txt
python manage.py check
python manage.py check --deploy
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate --noinput
python manage.py test --verbosity 2
python manage.py audit_seo --fail-on-error
python manage.py collectstatic --noinput
```

## انتشار روی سرور

```bash
sudo systemctl restart gunicorn
sudo nginx -t
sudo systemctl reload nginx
sudo systemctl status gunicorn --no-pager
sudo systemctl status nginx --no-pager
```

نمونهٔ Nginx در `deploy/nginx/zadconcept.conf` شامل `limit_req_zone` است و باید داخل context اصلی `http {}` include شود. مسیر socket، static، media و certificate را با سرور واقعی تطبیق دهید.

## کنترل Smoke پس از انتشار

این مسیرها باید پاسخ مستقیم `200`، canonical صحیح و HTML کامل داشته باشند:

```text
/
/flowers/
/flowers/all/
/flowers/same-day/
/bakery/
/gifts/
/occasions/
/workshops/
/mashhad/
/international-orders/
/en/international-orders/
/privacy/
/robots.txt
/sitemap.xml
```

همچنین یک محصول قیمت‌دار، یک محصول استعلامی، یک رویداد آینده و صفحه FAQ را بررسی کنید.

## Search و Indexing

- Google Search Console: Domain Property را تأیید و `/sitemap.xml` را ثبت کنید.
- Bing Webmaster Tools: سایت را تأیید و همان Sitemap را ثبت کنید.
- IndexNow: مقدار `INDEXNOW_KEY` را تنظیم و بار اول اجرا کنید:

```bash
python manage.py submit_indexnow --all
```

- اجرای‌های بعدی را با timer موجود فعال کنید.

## Analytics و Web Vitals

- `GOOGLE_TAG_ID` را فقط با شناسه معتبر تنظیم کنید.
- رویدادهای تماس، تلگرام، فرم، لید موفق، مشاهده محصول و Web Vitals را بررسی کنید.
- دادهٔ واقعی LCP، INP و CLS را از Search Console و ابزارهای میدانی مبنا قرار دهید، نه فقط Lighthouse آزمایشگاهی.

## امنیت

- `X_FRAME_OPTIONS` برابر `DENY` است.
- CSP ابتدا با `CSP_ENFORCE=False` در حالت Report-Only اجرا شود.
- پس از رفع violationهای واقعی، `CSP_ENFORCE=True` شود.
- HSTS یک‌ساله در Production فعال است.
- `SECURE_HSTS_INCLUDE_SUBDOMAINS` و `SECURE_HSTS_PRELOAD` فقط پس از تأیید HTTPS تمام subdomainها فعال شوند.
- Rate limit فرم لید هم در Django و هم در Nginx وجود دارد.

## CDN

- `/static/`: کش بلندمدت و immutable.
- `/media/`: کش ۳۰روزه با revalidation.
- HTML، Admin، فرم‌ها و پاسخ‌های sessionدار public cache نشوند.
- Bot/WAF rules برای Googlebot، Bingbot، OAI-SearchBot، Claude-SearchBot و PerplexityBot بازبینی شوند.
- GPTBot، ClaudeBot و Google-Extended مطابق سیاست فعلی training مسدودند.

## Timerها

```bash
sudo install -d -o cloud-admin -g www-data -m 0750 /var/lib/zad
sudo systemctl daemon-reload
sudo systemctl enable --now zad-indexnow.timer zad-seo-audit.timer
systemctl list-timers 'zad-*'
```

## تصاویر

فایل‌های تصویری اصلی پروژه در این اصلاحات جایگزین یا حذف نشده‌اند. Templateها اکنون ابعاد رزروشده، alt و lazy-loading مناسب دارند. در زمان ادغام با نسخهٔ اصلی Repository، پوشه‌های تصویر موجود همان پروژه حفظ شوند.

## HSTS preload

برای صفرشدن هشدار `check --deploy` می‌توان preload و includeSubDomains را موقتاً در محیط کنترل‌شده فعال کرد، اما در Production فقط زمانی فعال شوند که همهٔ subdomainها برای همیشه HTTPS باشند؛ این تصمیم نباید صرفاً برای حذف هشدار انجام شود.
