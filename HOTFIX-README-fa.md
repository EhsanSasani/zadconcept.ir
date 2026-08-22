# هات‌فیکس ZAD ـ نسخهٔ ۲ ـ ۳۰ ژوئیهٔ ۲۰۲۶

این بسته فقط فایل‌های لازم برای هات‌فیکس را دارد و به دیتابیس، فایل `.env` و
پوشهٔ `media` دست نمی‌زند. migration جدیدی نیز در آن وجود ندارد.

## تغییرات

- ریسپانسیو کامل‌تر پنل Jazzmin/Django Admin برای موبایل و تبلت
- Sidebar موبایل به‌صورت پیش‌فرض کاملاً بسته است، محتوای اصلی تمام عرض را
  می‌گیرد و منو فقط به‌شکل Overlay باز می‌شود.
- دستهٔ والد، محصولات مستقیم خودش و محصولات زیردسته‌های فعال را با هم نمایش
  می‌دهد؛ صفحهٔ هر زیردسته فقط محصولات همان زیردسته را نشان می‌دهد.
- محصولات مستقیم دستهٔ والد بعد از ساخت اولین زیردسته همچنان در ادمین قابل
  انتخاب و ویرایش‌اند.
- جست‌وجوی محصول با نام یا کد، با پشتیبانی از رقم فارسی، عربی و انگلیسی
- نمایش آدرس عمومی با پیشوند `مشهد،` در Footer و Contact
- تغییر عبارت عمومی «گل‌های زاد» و شکل‌های مشابه آن به «استودیو گل زاد»
- یک‌دست‌شدن Wedding:
  - `عروسی` دستهٔ والد مجموعه‌های Wedding است.
  - `ماشین عروس` و `دسته‌گل عروس` زیردسته‌های محصول‌اند.
  - صفحهٔ `عروسی` محصولات مستقیم و محصولات این دو زیردسته را یکجا نشان می‌دهد.
  - عروسی دیگر تگ مناسبتی نیست.
  - URLهای قدیمی Wedding با 301 به `/flowers/wedding/` می‌روند.

## فایل‌های برنامه

- `main/admin.py`
- `main/context_processors.py`
- `main/models.py`
- `main/sitemaps.py`
- `main/views.py`
- `main/static/main/css/admin_custom.css`
- `main/static/main/admin/fonts/Vazirmatn-Regular.woff2`
- `main/static/main/admin/fonts/Vazirmatn-Bold.woff2`
- `main/templates/category.html`
- `main/templates/flowers_landing.html`
- `main/templates/index.html`
- `main/templates/subcategory.html`
- `main/tests/test_regressions.py`

## روش مطمئن نصب روی سرور

ابتدا فایل ZIP را در `/tmp` سرور آپلود کن. سپس این دستورات را به‌ترتیب اجرا کن.

```bash
PATCH_ZIP=/tmp/zad-hotfix-20260730-v2.zip
PATCH_DIR=$(mktemp -d /tmp/zad-hotfix.XXXXXX)
unzip -q "$PATCH_ZIP" -d "$PATCH_DIR"
find "$PATCH_DIR" -type f -printf '%P\n' | sort
```

خروجی `find` را با فهرست فایل‌های بالا تطبیق بده. بعد یک بکاپ فقط از فایل‌های
جایگزین‌شونده بساز و پچ را اعمال کن:

```bash
BACKUP_DIR="/var/www/zad/backups/hotfix-$(date +%Y%m%d-%H%M%S)"
sudo mkdir -p "$BACKUP_DIR"
sudo rsync -a --backup --backup-dir="$BACKUP_DIR" "$PATCH_DIR/main/" /var/www/zad/app/main/
```

مفسر Python همان venv فعلی پروژه را به‌صورت خودکار انتخاب کن:

```bash
if [ -x /var/www/zad/app/.venv/bin/python ]; then ZAD_PY=/var/www/zad/app/.venv/bin/python; else ZAD_PY=/var/www/zad/venv/bin/python; fi
test -x "$ZAD_PY" && "$ZAD_PY" --version
```

گیت‌های قبل از Restart:

```bash
cd /var/www/zad/app
"$ZAD_PY" manage.py check
"$ZAD_PY" manage.py migrate --plan
"$ZAD_PY" manage.py test main.tests.test_regressions --verbosity 2
"$ZAD_PY" manage.py collectstatic --noinput
```

`migrate --plan` باید نشان دهد migration اجرا‌نشده‌ای وجود ندارد. چون این بسته
migration جدید ندارد، دستور `migrate` لازم نیست.

سرویس و Smoke Test:

```bash
sudo systemctl restart zad.service
sudo systemctl is-active zad.service
sudo systemctl status zad.service --no-pager
curl --unix-socket /var/www/zad/zad.sock -I -H 'Host: www.zadconcept.ir' http://localhost/
curl -I https://www.zadconcept.ir/
curl -I https://www.zadconcept.ir/admin/login/
```

بعد از ورود به Admin، در عرض موبایل این موارد را دستی چک کن:

1. لیست محصولات گل و اسکرول داخلی جدول
2. جست‌وجوی نام محصول و یک کد با رقم فارسی
3. فرم افزودن/ویرایش محصول و دکمه‌های ذخیره
4. باز و بسته‌شدن Sidebar
5. یک دستهٔ والد دارای زیردسته: نمایش محصولات مستقیم والد و محصولات زیردسته
6. صفحهٔ همان زیردسته: نمایش‌ندادن محصولات مستقیم والد

## Rollback

اگر Check، تست یا Smoke Test شکست خورد، فایل‌های قبلی را برگردان:

```bash
sudo rsync -a "$BACKUP_DIR/" /var/www/zad/app/main/
sudo systemctl restart zad.service
sudo systemctl status zad.service --no-pager
```

فایل `main/tests/test_regressions.py` در نسخهٔ قبلی وجود نداشته و باقی‌ماندنش روی عملکرد
سایت اثری ندارد؛ در صورت Rollback کامل می‌توان آن را جداگانه حذف کرد.
