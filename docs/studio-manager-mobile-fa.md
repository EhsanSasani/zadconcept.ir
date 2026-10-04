# پنل مدیریت — ویترین و جزئیات آمار

مبنا: سورس تأییدشده پس از پچ event-statistics (معادل انتشار VPS a6ad8e9).
این پچ فقط پنل مدیریت را تغییر می‌دهد؛ مدل، دیتابیس، Worker، ارسال تلگرام و پنل فلوریست تغییر نمی‌کنند.

- میانگین زمان فروش در صفحه اصلی با ارزش فروش جایگزین شده است.
- شش کارت آماری لینک گزارش مستقل با همان بازه دارند.
- فروش و خروج با تاریخ رویداد، تولید با تاریخ تولید محاسبه می‌شوند.
- موجودی و ویترین تمام محصولات DAILY/AVAILABLE را مستقل از بازه نشان می‌دهند؛ سفارشی، حذف‌شده و فروخته‌شده وارد ویترین نمی‌شوند.
- نمودار روزانه همه روزهای بازه و نمودار سهم فلوریست‌ها در گزارش نمایش داده می‌شود. موجودی چون عکس وضعیت فعلی است فقط نمودار سهم فلوریست‌ها دارد.
- جدول گزارش مرتب‌سازی و صفحه‌بندی دارد. جدول عریض روی موبایل در ناحیه خود قابل پیمایش است.
- ویترین دو ستونه روی گوشی و چهار ستونه روی دسکتاپ، عکس قابل بزرگنمایی، قیمت، نام فلوریست و فاکتور دارد.
- روند تولید/فروش، ترکیب تولید و جدول آخرین فعالیت از صفحه اصلی برداشته شده‌اند؛ عملکرد فلوریست‌ها زیر ویترین قرار دارد.
- مبلغ فروش مطابق منطق فعلی سیستم از قیمت فعلی محصول محاسبه می‌شود؛ این پچ مدل مبلغ قطعی هنگام فروش ایجاد نمی‌کند.
- ویترین پس از بازکردن/تازه‌سازی صفحه به‌روز می‌شود؛ این نسخه polling خودکار ندارد.

## اجرای محلی در PowerShell

ابتدا git status --short را بررسی کنید. تغییرات کاری خود را ذخیره کنید.

```powershell
git switch -c feature/manager-mobile
git apply --check .\zad-studio-manager-mobile.patch
git apply .\zad-studio-manager-mobile.patch
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py test main.tests.test_studio_manager_overview main.tests.test_studio_ui main.tests.test_studio_event_statistics main.tests.test_studio_operations
git diff --check
python manage.py runserver
```

صفحه /studio/ و لینک هر شش کارت را با گوشی بررسی کنید.
اگر apply --check خطا داد، پچ را به زور یا با جایگزینی فایل‌ها اعمال نکنید؛ اختلاف مبنا باید بررسی شود.

## VPS پس از بررسی محلی

پچ را به سرور منتقل کنید. working tree باید تمیز باشد؛ از نسخه و تنظیمات جاری بکاپ بگیرید.

```bash
cd /var/www/zad/app
git status --short
git apply --check /home/cloud-admin/zad-studio-manager-mobile.patch
git switch -c deploy/manager-mobile
git apply --index /home/cloud-admin/zad-studio-manager-mobile.patch
git diff --cached --check
/var/www/zad/venv/bin/python manage.py check
/var/www/zad/venv/bin/python manage.py collectstatic --noinput
sudo systemctl restart zad.service
sudo systemctl is-active zad.service
```

نیازی به migrate یا restart سرویس delivery یا deploy Worker نیست.
پس از بررسی صفحه و گزارش‌ها، تغییر را commit کنید.
