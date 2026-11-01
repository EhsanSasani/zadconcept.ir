# نهایی‌سازی نسخهٔ ۲ پیش از توسعهٔ فروش آنلاین

وضعیت: اجرا نشده؛ نیازمند دسترسی به checkout لوکال و VPS.
این سند چک‌لیست عملیاتی است، نه گزارش انجام عملیات.

## علت
main گیت‌هاب مشاهده‌شده در ۱۲ اکتبر متوقف است؛ codex/product-identity مشاهده‌شده تا ۲۱ اکتبر تغییر دارد. برابری هیچ‌یک با لوکال یا production ثابت نشده است. VERSION مشاهده‌شده در main برابر 1.1.3 است؛ نام‌گذاری‌های refactor-v2 یا source-layout-v3 به معنی نسخهٔ محصول درخواست‌شده در این کار نیستند.

## ثبت وضعیت بدون تغییر
در ریشهٔ واقعی پروژهٔ لوکال و ریشهٔ واقعی source سرور، جداگانه ثبت شود:
- branch و HEAD کامل.
- git status --short و diff خلاصهٔ tracked/untracked.
- remoteهای واقعی و upstream.
- تاریخچهٔ مختصر آخرین commitها و migrationهای کد.
- نسخهٔ Python/Django، تنظیمات محیطِ بدون مقادیر محرمانه، وضعیت migration دیتابیس و static/deployment.
- آیا source سرور checkout Git دارد یا فقط patch دریافت کرده است.

مسیر /var/www/zad/app در تنظیمات systemd کاندید بررسی‌شده دیده شده، اما در این کار به آن وصل نشده‌ایم. مسیر واقعی و روش انتقال باید در محیط اجرا تأیید شوند.

## جمع‌آوری تغییرات
- فایل‌های هر دو محیط با هم و با GitHub مقایسه شوند؛ تفاوت لوکال/VPS خودکار با overwrite، reset یا pull اجباری حل نشود.
- هر تغییر آگاهانه و مرتبط مرور، منشأ آن مشخص و در کاندید نسخهٔ ۲ جمع شود. تغییرات متفاوت یک فایل بدون حذف کار کاربر ادغام شوند.
- staging فقط با فهرست فایل‌های مشخص؛ git add . و git add -A استفاده نشوند.
- .env، کلیدها، tokenها، پایگاه داده، backup/dump، media کاربران، venv و staticfiles وارد commit نشوند.
- backup معتبر دیتابیس/media و نقطهٔ بازگشت deployment در محل runtime مستقل از source نگه داشته شوند.
- هیچ خروجی قدیمی PASS در اسناد پروژه، نتیجهٔ تست این release تلقی نشود.

## معیار نهایی شدن
در checkout تجمیع‌شده:
- python manage.py check
- python manage.py test
- python manage.py makemigrations --check --dry-run
- python manage.py migrate --plan
- node --test ops/cloudflare/zad-telegram-relay-worker.test.mjs
- آزمون‌های JS مرتبط و git diff --check
- smoke test سایت عمومی، مسیرهای Studio/Team/Sales و صفحات مهم در موبایل/دسکتاپ
- بررسی اینکه schema و کد deployed سازگارند؛ محیط سرور و runtime بدون نشت اطلاعات ثبت شوند.

تست و اجرای schema change روی production صرفاً با migration plan و روش deployment/rollback واقعی انجام شود. بازگشت کد جایگزین بازگشت امن schema نیست.

## ثبت release و شاخهٔ جدید
پس از عبور از معیارها:
1. تغییرات باقی‌ماندهٔ نسخهٔ ۲ به یک یا چند commit قابل‌بررسی تبدیل شوند.
2. SHA واحد مبنای release ثبت و نام/tag نسخهٔ ۲ با سیاست موجود مخزن سازگار انتخاب شود؛ tag موجود بازنویسی نشود.
3. از همان SHA شاخهٔ feature/v3-commerce ساخته شود؛ نه از main قدیمی صرفاً به دلیل default بودن آن.
4. شاخهٔ planning/v3-commerce فقط قرارداد طراحی دارد. اسناد آن پس از تطبیق به feature branch منتقل شوند؛ تاریخچهٔ نامرتبط یا مبنای تأییدنشده به زور ادغام نشود.
5. جدول زیر با شواهد واقعی تکمیل شود.

| مورد | وضعیت فعلی این گفتگو | مدرک لازم |
|---|---|---|
| HEAD و تغییرات لوکال | نامعلوم | خروجی واقعی Git |
| HEAD و تغییرات VPS | نامعلوم | خروجی واقعی Git/مقایسهٔ source |
| backup و rollback | بررسی نشده | محل، زمان و قابلیت بازیابی |
| tests و migration gates | اجرا نشده | خروجی اجرای همین release |
| v2 final commit/tag | ایجاد نشده | SHA و tag تأییدشده |
| feature/v3-commerce از v2 | ایجاد نشده | parent برابر مبنای نهایی |
| اسناد طراحی روی planning branch | در این کار آماده می‌شود | commit اسناد و لینک فایل‌ها |
