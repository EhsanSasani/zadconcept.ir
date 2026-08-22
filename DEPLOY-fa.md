# استقرار پچ نهایی آپلود تصویر ZAD

این بسته مشکل آپلود عکس‌های روزانه فروشندگان را در مرز خود فرم ادمین حل
می‌کند. هیچ Migration، تغییر دیتابیس، فایل Static یا تغییر Nginx ندارد.

## فایل‌های پچ

```text
main/admin.py
main/image_pipeline.py
main/tests/test_images.py
requirements-image-upload.txt
QA-fa.md
```

## رفتار نهایی

- نام فایل و MIME مرورگر معیار اعتماد نیست؛ محتوای واقعی Decode و بررسی می‌شود.
- JPG، JPEG، JPE، JFIF و JPEGهای موبایلی از نوع MPO پذیرفته می‌شوند.
- HEIC، HEIF، HEICS، HEIFS و HIF با `pillow-heif==1.5.0` پذیرفته می‌شوند.
- PNG، WebP، AVIF، TIFF، BMP و GIF ثابت نیز پشتیبانی می‌شوند.
- خروجی همیشه یک WebP سالم و ثابت با حداکثر ضلع ۳۲۰۰ پیکسل است.
- چرخش EXIF اصلاح، ICC معتبر حفظ و EXIF/XMP/GPS حذف می‌شود.
- فایل خراب، تصویر متحرک، فایل بیش از ۲۰٬۰۰۰٬۰۰۰ بایت و تصویر بیش از
  ۶۰ مگاپیکسل با خطای قابل‌فهم رد می‌شود.
- ویرایش رکورد بدون انتخاب عکس جدید، فایل قبلی را نمی‌خواند و Encode نمی‌کند.
- گزینهٔ حذف عکس همچنان کار می‌کند.
- `manage.py check` نبودن WebP encoder یا `pillow-heif` را خطای Deploy اعلام
  می‌کند.

## ترتیب امن استقرار

روی سرور:

```bash
package=/home/cloud-admin/zad-admin-image-upload-final-v3.zip
app_root=/var/www/zad/app
run_root="$(mktemp -d /tmp/zad-image-v3.XXXXXX)"

unzip -q "$package" -d "$run_root"
find "$run_root" -type f -printf '%P\n' | sort
```

خروجی باید فقط فایل‌های فهرست‌شده در ابتدای این سند را نشان دهد.

### ۱. بکاپ فایل‌های فعلی

```bash
backup_file="/home/cloud-admin/zad-image-pre-v3-$(date +%Y%m%d-%H%M%S).tar.gz"

sudo tar -C "$app_root" -czf "$backup_file" \
  main/admin.py \
  main/image_pipeline.py \
  main/tests/test_images.py

sudo chown cloud-admin:cloud-admin "$backup_file"
tar -tzf "$backup_file"
sha256sum "$backup_file"
```

### ۲. تثبیت وابستگی

```bash
/var/www/zad/venv/bin/python -m pip install --no-cache-dir \
  -r "$run_root/requirements-image-upload.txt"

/var/www/zad/venv/bin/python -c "from importlib.metadata import version; from PIL import features; import pillow_heif; print('pillow-heif:', version('pillow-heif')); print('WebP:', features.check('webp')); assert features.check('webp')"
```

همین خط وابستگی باید در فایل requirements اصلی مخزن GitHub نیز ثبت شود:

```text
pillow-heif==1.5.0
```

### ۳. نصب سه فایل کد

```bash
sudo install -o cloud-admin -g cloud-admin -m 0644 \
  "$run_root/main/admin.py" \
  "$app_root/main/admin.py"

sudo install -o cloud-admin -g cloud-admin -m 0644 \
  "$run_root/main/image_pipeline.py" \
  "$app_root/main/image_pipeline.py"

sudo install -o cloud-admin -g cloud-admin -m 0644 \
  "$run_root/main/tests/test_images.py" \
  "$app_root/main/tests/test_images.py"

stat -c '%U:%G %a %n' \
  "$app_root/main/admin.py" \
  "$app_root/main/image_pipeline.py" \
  "$app_root/main/tests/test_images.py"
```

### ۴. بررسی قبل از Restart

```bash
cd /var/www/zad/app

/var/www/zad/venv/bin/python manage.py check
/var/www/zad/venv/bin/python manage.py makemigrations --check --dry-run
/var/www/zad/venv/bin/python manage.py test \
  main.tests.test_images.ResponsiveImageTests \
  --verbosity 2

sudo nginx -T 2>/dev/null | grep -n "client_max_body_size"
```

نتیجهٔ مورد انتظار:

```text
System check identified no issues
No changes detected
client_max_body_size 20M;
```

تست کامل فرم ادمین در CI/local از دیتابیس تست استفاده می‌کند؛ روی Production
همان کلاس `ResponsiveImageTests` را اجرا کنید تا دیتابیس تست ساخته نشود.

### ۵. Restart و Smoke Test

```bash
sudo systemctl restart zad.service
sudo systemctl is-active zad.service

curl -I --unix-socket /var/www/zad/zad.sock \
  -H 'Host: zadconcept.ir' \
  http://localhost/

curl -I https://www.zadconcept.ir/
sudo journalctl -u zad.service --since "5 minutes ago" --no-pager
```

`is-active` باید `active` باشد. پاسخ Unix socket می‌تواند Redirect قانونی به
دامنهٔ canonical باشد و پاسخ عمومی باید سالم باشد.

## تست نهایی در پنل واقعی

در «مدیریت ارسال روز» این سناریوها را روی رکوردهای تست انجام دهید:

1. یک JPG واقعی دوربین را ذخیره کنید.
2. یک فایل با پسوند `.jpeg` را ذخیره کنید.
3. یک HEIC واقعی آیفون را ذخیره کنید.
4. یک HEIF واقعی را ذخیره کنید.
5. همان رکورد را بدون انتخاب عکس جدید ذخیره کنید؛ مسیر عکس نباید تغییر کند.
6. عکس همان رکورد را با فایل جدید جایگزین کنید؛ خروجی جدید باید `.webp` باشد.
7. یک فایل خراب/غیرتصویری را انتخاب کنید؛ باید پیام فرم نمایش داده شود، نه 500.

Nginx روی `20M` باقی می‌ماند. حد برنامه ۲۰٬۰۰۰٬۰۰۰ بایت است تا سربار فرم
multipart نیز داخل سقف ۲۰ MiB وب‌سرور جا شود.

## Rollback

اگر هر بررسی قبل یا بعد از Restart شکست خورد:

```bash
app_root=/var/www/zad/app
backup_file=/home/cloud-admin/نام-دقیق-بکاپ.tar.gz

sudo tar -C "$app_root" -xzf "$backup_file"
sudo chown cloud-admin:cloud-admin \
  "$app_root/main/admin.py" \
  "$app_root/main/image_pipeline.py" \
  "$app_root/main/tests/test_images.py"

sudo systemctl restart zad.service
sudo systemctl is-active zad.service
```

این Rollback فقط سه فایل همین پچ را برمی‌گرداند و به دیتابیس و Media دست
نمی‌زند.
