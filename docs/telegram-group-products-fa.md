# اتصال گروه آماده‌های ارسال به ZAD

این سند ادامهٔ پچ قبلی Telegram Same-Day است. برای گروه موجود بهزاد، این تنظیمات بر دستورالعمل قدیمی کانال اولویت دارند. ساخت کانال یا ربات جدید لازم نیست. تا آماده‌شدن Django و Worker، webhook قبلی را تغییر ندهید.

## رفتار

- عکس تکی از اپراتور مجاز + قیمت در کپشن: محصول همان کاتالوگ ارسال روز منتشر می‌شود.
- عکس بدون قیمت: فقط شناسه و اطلاعات عکس در رکورد همگام‌سازی ذخیره می‌شود. هنوز محصولی روی سایت منتشر و عکسی دانلود نمی‌شود.
- قیمت در reply به عکس: همان عکس منتشر می‌شود. reply به پیام قیمتِ شناخته‌شده نیز به همان محصول متصل است.
- ویرایش کپشن یا متن reply قیمت: قیمت به‌روز می‌شود. تاریخ و update_id از بازگشت قیمت در تحویل تکراری/قدیمی جلوگیری می‌کنند.
- reply «فروخته شد»: SOLD و خروج از نمایش عمومی.
- reply «کشیده شد»: WITHDRAWN و خروج از نمایش عمومی؛ رکورد و عکس برای سابقه باقی می‌مانند. این عملیات حذف فیزیکی دیتابیس نیست.
- ویرایش بعدی قیمت محصول SOLD/WITHDRAWN را دوباره موجود نمی‌کند. WITHDRAWN نسبت به فرمان فروش بعدی اولویت دارد.
- فقط TelegramBotUser فعال با can_manage_same_day می‌تواند عکس/قیمت/فرمان مدیریت ارسال کند. عضویت یا ادمین‌بودن در تلگرام به‌تنهایی مجوز Django نیست.
- پیام ناشناس، پیام از طرف کانال دیگر، ربات و forward دستی پذیرفته نمی‌شود. هویت محصول بر اساس chat_id + message_id است.

## قرارداد قیمت گروه

| متن | مقدار ذخیره‌شده، تومان |
| --- | ---: |
| `2300`، `۲۳۰۰`، `2,300`، `۲/۳۰۰ ت` | 2300000 |
| `2/680 t`، `۲٬۶۸۰` | 2680000 |
| `2,680,000`، `۲/۶۸۰/۰۰۰`، `2 680 000 تومان` | 2680000 |
| `2.68`، `۲/۶۸`، `۲٫۶۸ میلیون تومان`، `2.68m` | 2680000 |
| `2680 هزار تومان`، `2680k` | 2680000 |
| `2300 تومان` یا `2300 تومن` | 2300 |

اعداد فارسی، عربی و انگلیسی پشتیبانی می‌شوند. عدد صحیح بدون واحد یا با `t`/`ت` اگر کمتر از 100000 باشد، طبق قرارداد این گروه هزار تومان است؛ از 100000 به بالا مبلغ کامل تومان است. اعشار بدون واحد به میلیون تومان تعبیر می‌شود. «تومان/تومن» صریح همیشه مقدار واقعی تومان است. برای جلوگیری از ابهام، مبلغ کامل با «تومان» بهترین شکل ورود است.

قیمت می‌تواند خط جدا یا پس از برچسب «قیمت» در توضیح محصول باشد. نوشتار دلخواه نامحدود، حروفی مثل «دو و خورده‌ای»، چند قیمت/قیمت تخفیف و قیمت توافقی حدس زده نمی‌شوند. در صورت خطای قیمت محصول منتشر نمی‌شود؛ ویرایش نامعتبر قیمتِ محصول موجود آن را draft می‌کند تا اصلاح شود. log دارای chat_id و message_id است و متن خصوصی یا token را چاپ نمی‌کند.

این نسخه عکس تکی Telegram Photo را می‌پذیرد؛ آلبوم، فایل document و واردکردن تاریخچه قدیمی به‌صورت خودکار پشتیبانی نمی‌شود. گروه قدیمی قبل از migration شناسه متفاوتی دارد؛ فقط شناسه گروه جدید را تنظیم کنید. برای محصول قدیمی، عکس را به‌صورت پست تازه توسط اپراتور مجاز بفرستید.

## فایل و migration

پچ تکمیلی `zad-telegram-group-addon.patch` روی نسخه‌ای اعمال می‌شود که پچ `zad-telegram-same-day-a9e7804.patch` را قبلاً گرفته است. پچ قبلی را دوباره روی Local اعمال نکنید.

فایل‌های اصلاح‌شده: `.env.example`، `config/settings.py`، `main/models.py`، `main/telegram_same_day/price.py`، `main/telegram_same_day/service.py`، `main/management/commands/telegram_same_day_webhook.py`، Worker و تست Worker، و دو سند قبلی تلگرام.

فایل‌های جدید: `main/telegram_same_day/group.py`، `main/tests/test_telegram_group_products.py`، `main/migrations/0033_telegram_group_products.py` و همین سند.

Migration 0033 فقط source_photo و withdrawn_at را به رکورد همگام‌سازی اضافه می‌کند و گزینه WITHDRAWN را به status محصول می‌افزاید. جدول محصولات جدید ساخته نمی‌شود؛ 0032 تغییر نکرده است.

## Local — PowerShell

در پوشه پروژه فعلی با venv فعال، ابتدا:

```powershell
git apply --check .\zad-telegram-group-addon.patch
```

اگر بدون خطا بود، از پوشه کد فعلی (شامل تغییرات commitنشده پچ قبلی) و db.sqlite3 بکاپ بگیرید؛ هنگام کپی SQLite سرور محلی متوقف باشد. سپس:

```powershell
git apply .\zad-telegram-group-addon.patch
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate
python manage.py test main.tests.test_telegram_group_products main.tests.test_telegram_same_day
node --test ops/cloudflare/zad-telegram-relay-worker.test.mjs
```

در فایل واقعی `.env`، کلید جدید `TELEGRAM_SAME_DAY_GROUP_ID` را با شناسه منفی گروه جدید پر کنید. در حالت فقط گروه، `TELEGRAM_CHANNEL_ID` و `TELEGRAM_DISCUSSION_GROUP_ID` خالی باشند. توکن/secret موجود را در فایل نمونه یا Git نگذارید. دستهٔ انتخاب‌شده Local شماره 1 بوده است؛ در VPS وجود و مناسب‌بودن همان دسته را مستقل بررسی کنید.

تنظیمات Django موردنیاز:

- TELEGRAM_WEBHOOK_SECRET: secret معتبر و یکسان با Worker و ثبت webhook.
- TELEGRAM_SAME_DAY_GROUP_ID: شناسه عددی منفی گروه جدید؛ با channel یا discussion مشترک نباشد.
- TELEGRAM_SAME_DAY_CATEGORY_ID: دسته فعال عمومی گل.
- حالت Worker موجود: TELEGRAM_SAME_DAY_RELAY_URL برابر ریشه HTTPS Worker و TELEGRAM_LEAD_RELAY_SECRET برابر RELAY_SECRET همان Worker. توکن در Cloudflare می‌ماند.
- فقط برای حالت مستقیم: TELEGRAM_BOT_TOKEN؛ relay URL خالی.
- TELEGRAM_SAME_DAY_TIMEOUT_SECONDS: مقدار پیش‌فرض 8 ثانیه.

بعد از تکمیل تنظیمات:

```powershell
python manage.py telegram_same_day_webhook check
```

## Telegram و Worker

همان ربات موجود را در گروه جدید Admin کنید تا پیام‌های عادی عکس/قیمت گروه را دریافت کند. برای این integration اجازه حذف پیام یا افزودن اعضا نیاز نیست؛ کمترین دسترسی ممکن را بدهید. Privacy Mode ربات ادمین مانع دریافت پیام‌های گروه نمی‌شود: [Telegram FAQ](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get).

در Django Admin برای بهزاد و سایر ارسال‌کنندگان مجاز، TelegramBotUser با شناسه عددی شخصی و is_active و can_manage_same_day فعال کنید. ادمین‌ها با حساب شخصی و بدون حالت anonymous پست بفرستند.

در Worker همان متغیرهای فعلی را حفظ کنید و TELEGRAM_SAME_DAY_GROUP_ID را اضافه کنید. SAME_DAY_WEBHOOK_URL باید `https://www.zadconcept.ir/api/telegram/webhook/` باشد. TELEGRAM_WEBHOOK_SECRET باید با Django برابر باشد. TELEGRAM_BOT_TOKEN و RELAY_SECRET موجود را عوض نکنید مگر آگاهانه همه مصرف‌کننده‌ها را هماهنگ کنید. برای این گروه نیازی به Linked Discussion نیست؛ حالت قبلی کانال + discussion همچنان پشتیبانی می‌شود.

## VPS — ترتیب امن

قبل از دست‌زدن به فایل‌ها، از کد فعلی، env، media و PostgreSQL با روش بکاپ فعلی پروژه نسخه سالم بگیرید. pg_dump را با کاربر/تنظیمات واقعی دیتابیس اجرا کنید؛ `.env` را به عنوان اسکریپت shell اجرا نکنید.

فایل‌های patch را به `/home/cloud-admin/` منتقل کنید. در `/var/www/zad/app` ابتدا `git status --short` و `git rev-parse HEAD` را بررسی کنید. اگر پچ قبلی روی VPS نیست، اول `git apply --check` پچ قبلی و سپس اعمال آن؛ اگر قبلاً اعمال شده دوباره اعمال نکنید. بعد پچ تکمیلی:

```bash
cd /var/www/zad/app
git apply --check /home/cloud-admin/zad-telegram-group-addon.patch
git apply /home/cloud-admin/zad-telegram-group-addon.patch
ZAD_PY=/var/www/zad/venv/bin/python
"$ZAD_PY" manage.py check
"$ZAD_PY" manage.py makemigrations --check --dry-run
"$ZAD_PY" manage.py migrate --plan
"$ZAD_PY" manage.py migrate
"$ZAD_PY" manage.py telegram_same_day_webhook check
sudo systemctl restart zad.service
sudo systemctl is-active zad.service
curl -I https://www.zadconcept.ir/
```

env مربوط به گروه و اشخاص مجاز را قبل از check آخر تکمیل کنید. تغییر static نداریم. تغییرات Worker را فقط پس از آماده‌شدن Django منتشر کنید. تست‌ها با دیتابیس تست جدا اجرا شوند؛ به دیتابیس واقعی production اشاره نکنند.

اگر webhook از قبل روی Worker همین ربات است، URL آن را به Django تغییر ندهید؛ رفتار قدیمی اعلان فرم و lookup خصوصی باید حفظ شود. برای ثبت/اصلاح allowed_updates، فرمان موجود با توکن محلی همان ربات و URL واقعی HTTPS Worker اجرا می‌شود:

```powershell
python manage.py telegram_same_day_webhook register --url https://YOUR-WORKER-HOST/telegram-webhook
python manage.py telegram_same_day_webhook info
```

`YOUR-WORKER-HOST` placeholder است و باید با دامنه واقعی جایگزین شود. توکن را در command line نگذارید. ثبت webhook حالت message/edited_message و channel_post/edited_channel_post را حفظ می‌کند و pending updates را حذف نمی‌کند. اگر secret جدید استفاده می‌کنید، ثبت Telegram و Django و Worker باید همزمان هماهنگ شوند.

## آزمون واقعی پس از استقرار

1. اپراتور مجاز عکس تازه با `2300` بفرستد: قیمت سایت 2300000.
2. عکس دوم بدون کپشن: روی سایت نباشد؛ قیمت `2/680 t` را reply کند: قیمت سایت 2680000.
3. متن همان reply را به `3000` ویرایش کند: همان محصول 3000000.
4. reply «فروخته شد»: محصول اول از سایت خارج، در Admin SOLD.
5. reply «کشیده شد»: محصول دوم از سایت خارج، در Admin WITHDRAWN.
6. ویرایش قیمت هیچ‌کدام را دوباره موجود نکند؛ محصول Admin دستی و lookup خصوصی و اعلان فرم نیز همچنان کار کنند.

وبهوک تست زنده و استقرار روی حساب‌های واقعی در محیط ساخت پچ اجرا نشده‌اند؛ باید پس از تنظیم شناسه‌ها و دسترسی‌ها انجام شوند. تست قفل همزمان PostgreSQL فقط در محیط PostgreSQL قابل اجراست و در SQLite skip می‌شود.

نتیجه بررسی نسخه تکمیلی: 381 تست Django، 380 موفق و 1 مورد PostgreSQL skip؛ 17 تست Worker همگی موفق؛ Django check، بررسی تغییرات migration، compileall و git diff --check موفق. migration جدید روی دیتابیس محلی آزمایشی اعمال شد و پچ تکمیلی روی نسخه دارای پچ قبلی بدون خطا اعمال شد.
