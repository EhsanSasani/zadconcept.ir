# اتصال تلگرام به ارسال روز ZAD

مبنای پچ: `main` در commit `a9e7804526f50992dba5cee622e8a6d043bf48fc`.
این پچ روی همین نسخه ساخته شده؛ قبل از اعمال روی Local و VPS، `git apply --check` باید موفق باشد.
فایل‌های UI عمومی تغییر نمی‌کنند. commit یا push و استقرار production انجام نشده است.

## رفتار پیاده‌سازی

- عکس تکی + یک خط قیمت → همان `Product` با `catalog_scope=same_day` و قیمت ثابت به تومان.
- قیمت در `Product.price` موجود ذخیره می‌شود؛ parser عدد صحیح برمی‌گرداند.
- `Product.status` برابر `AVAILABLE` یا `SOLD` است. محصولات قبلی مقدار پیش‌فرض AVAILABLE می‌گیرند؛ وضعیت موجودی/انتشار و تصاویر قبلی حفظ می‌شوند.
- شناسه‌ها و وضعیت پردازش در `TelegramSameDayPost` با رابطهٔ OneToOne به Product ذخیره می‌شوند. این جدول کاتالوگ موازی نیست؛ حتی وقتی قیمت نامعتبر است یا پیام فروش زودتر می‌رسد، هویت پست را نگه می‌دارد.
- یکتایی `(telegram_chat_id, telegram_message_id)` در دیتابیس enforce شده است.
- `TelegramDiscussionMessage` شناسهٔ پیام‌های گروه را به هویت پست اصلی متصل می‌کند. caption، نام و تشابه عکس در matching نقشی ندارند.
- SOLD از query مشترک انتشار ارسال روز حذف می‌شود؛ صفحهٔ ارسال روز، انتخاب ارسال روز صفحهٔ اصلی، محصولات مرتبط و sitemap آن را نمایش نمی‌دهند. صفحهٔ عمومی جزئیات آن نیز 404 می‌شود. رکورد و تصویر باقی می‌مانند.
- قیمت نامعتبر در پست جدید، محصول ایجاد نمی‌کند. قیمت نامعتبر در ویرایش، محصول موجود را draft می‌کند؛ ویرایش معتبر بعدی دوباره آن را منتشر می‌کند، اما SOLD را AVAILABLE نمی‌کند و `is_active=False` دستی را تغییر نمی‌دهد.
- عکس از Bot API دریافت و با image pipeline فعلی به WebP تبدیل می‌شود. ذخیره در `Product.cover_image` و storage فعلی Django است؛ URL تلگرام در frontend استفاده نمی‌شود.
- تکرار update و ویرایش صرف قیمت باعث دانلود مجدد عکس نمی‌شوند. تغییر واقعی `file_id` تصویر را به‌روز می‌کند.
- قفل رکورد در transaction، یکتایی دیتابیس و cursor زمان/شناسهٔ update مانع duplicate و عقب‌رفتن قیمت با update قدیمی می‌شوند. خطای موقت دانلود/دیتابیس 503 می‌دهد و update مصرف نمی‌شود.
- هیچ polling، Celery یا dependency جدیدی اضافه نشده است. دانلود در همان درخواست محدودشده انجام می‌شود؛ `max_connections=1` برای حجم معمول ارسال روز تنظیم می‌شود.

## مدل و migration

تنها migration جدید: `main/migrations/0032_telegram_same_day_sync.py`، وابسته به `0031_editorial_content_system`.

1. `Product.status` با default AVAILABLE.
2. `TelegramBotUser.can_manage_same_day` با default False.
3. `TelegramSameDayPost`: شناسهٔ کانال/پست، اتصال محصول، file_id، زمان پست، cursor آخرین ویرایش، `sold_at` و کد خطای آخر.
4. `TelegramDiscussionMessage`: mapping پیام گروه به پست با unique constraint.

هیچ data migration حذف‌کننده و هیچ تغییری در قیمت/رسانهٔ محصولات قبلی وجود ندارد. حذف محصول متصل به تلگرام به‌واسطهٔ `PROTECT` ممنوع است تا سابقه از دست نرود. برای خارج‌کردن آن از نمایش از SOLD یا غیرفعال‌سازی استفاده کنید.

## انتخاب مسیر مناسب برای ZAD

در پروژهٔ فعلی ربات فرم‌ها و جست‌وجوی محصول از Worker استفاده می‌کند، چون اتصال مستقیم VPS به Telegram قابل اتکا نبوده است.

**برای همین ربات، مسیر Worker را استفاده کنید:**

Telegram → Worker `/telegram-webhook` → Django `/api/telegram/webhook/` → Product.
Django → Worker `/same-day-file` → Telegram getFile → رسانهٔ سایت.

Worker همان پیام‌های خصوصی قبلی را پردازش می‌کند. فقط رویدادهای کانال/گروه تنظیم‌شده به endpoint جدید فرستاده می‌شوند. مجوز اشخاص همچنان در Django تعیین می‌شود.

**حالت مستقیم** نیز پیاده‌سازی شده است: برای یک ربات جداگانه و سروری با دسترسی مستقیم به Telegram، webhook را مستقیماً به Django بدهید و `TELEGRAM_BOT_TOKEN` را روی آن سرور تنظیم کنید.
هر ربات یک webhook دارد؛ ثبت آدرس مستقیم Django برای ربات فعلی، مسیر پیام‌های خصوصی Worker آن ربات را جایگزین می‌کند. برای ربات فعلی همان آدرس Worker را نگه دارید.

## Environment variables

| متغیر Django | مقدار/کاربرد |
| --- | --- |
| `TELEGRAM_WEBHOOK_SECRET` | secret تصادفی مشترک با تنظیم setWebhook؛ در حالت Worker عین secret همان Worker |
| `TELEGRAM_CHANNEL_ID` | شناسهٔ عددی منفی کانال؛ نه username |
| `TELEGRAM_DISCUSSION_GROUP_ID` | شناسهٔ عددی منفی گروه متصل؛ اختیاری فقط اگر کامنت گروه استفاده نمی‌شود |
| `TELEGRAM_SAME_DAY_CATEGORY_ID` | PK یک دستهٔ فعال موجود در بخش flowers و خارج از عروسی؛ همهٔ پست‌های این کانال ابتدا در همین دسته ساخته می‌شوند |
| `TELEGRAM_BOT_TOKEN` | فقط دانلود مستقیم و اجرای فرمان ثبت/بررسی webhook؛ روی VPS در حالت Worker خالی می‌ماند |
| `TELEGRAM_SAME_DAY_RELAY_URL` | حالت Worker: آدرس پایهٔ Worker، مثلاً `https://your-worker.workers.dev`؛ حالت مستقیم: خالی |
| `TELEGRAM_LEAD_RELAY_SECRET` | secret فعلی relay؛ در حالت Worker لازم است و با `RELAY_SECRET` یکسان است |
| `TELEGRAM_SAME_DAY_TIMEOUT_SECONDS` | پیش‌فرض 8 ثانیه برای هر درخواست خروجی Django |

تنظیمات فعلی `TELEGRAM_LEAD_RELAY_URL` و مجوزهای دریافت فرم/جست‌وجوی محصول را حفظ کنید.

متغیرهای Worker در مسیر موجود:

```text
TELEGRAM_BOT_TOKEN=<توکن همان ربات فعلی، به‌صورت Secret>
RELAY_SECRET=<secret فعلی relay، به‌صورت Secret>
TELEGRAM_WEBHOOK_SECRET=<secret مشترک webhook، به‌صورت Secret>
TELEGRAM_CHANNEL_ID=<شناسه کانال>
TELEGRAM_DISCUSSION_GROUP_ID=<شناسه گروه متصل>
SAME_DAY_WEBHOOK_URL=https://www.zadconcept.ir/api/telegram/webhook/
```

برای تولید secret جدید، اگر ربات تازه می‌سازید:

```powershell
python -c "import secrets; print(secrets.token_hex(32))"
```

برای ربات فعلی اگر secret را عوض می‌کنید، Django و Worker و setWebhook را با هم به‌روز کنید. توکن را در command line، commit، screenshot یا متن پچ نگذارید؛ فقط `.env` محلی/سرور و Secretهای Worker.

## Telegram و BotFather

1. برای ربات موجود همان توکن فعلی را نگه دارید؛ برای ربات جدا از BotFather با `/newbot` بسازید.
2. ربات را به کانال اضافه کنید؛ در UI تلگرام معمولاً به‌صورت Administrator اضافه می‌شود. این integration فقط خواندن پست لازم دارد؛ مجوز ارسال/ویرایش/حذف پست، افزودن ادمین یا دعوت عضو لازم نیست. کمترین دسترسی قابل انتخاب را بدهید.
3. در تنظیمات کانال، Discussion را به گروه موردنظر متصل کنید. فوروارد دستی پست به یک گروه جایگزین Linked Discussion نیست.
4. ربات را در گروه نیز Administrator کنید تا پیام‌های بحث و کامنت‌ها را دریافت کند؛ حذف پیام/مسدودسازی/افزودن ادمین لازم نیست. اگر ربات admin است، برای این کار نیازی به خاموش‌کردن privacy mode نیست. مسیر جایگزین برای دریافت پیام‌های گروه، `/setprivacy` → Disable است؛ مسیر تست‌شدهٔ عملی موردنظر، bot admin در گروه است.
5. اپراتور با حساب شخصی خود کامنت بگذارد؛ حالت anonymous admin یا Send as Channel برای فرمان فروش عمداً پذیرفته نمی‌شود.
6. در Django Admin → «کاربران ربات تلگرام»، کاربر را با numeric User ID ثبت کنید، `is_active` و گزینهٔ «محصول ارسال روز را فروخته‌شده اعلام کند؟» را فعال کنید. این مجوز از مجوز جست‌وجو و دریافت فرم مستقل است.
7. با ربات فعلی اپراتور `/id` را در private chat می‌فرستد تا شناسه‌اش را ببیند. ربات مستقیمِ جداگانه این فرمان private را پیاده‌سازی نمی‌کند؛ شناسهٔ اپراتور را هنگام راه‌اندازی از اطلاعات معتبر تلگرام بگیرید.

برای دریافت شناسهٔ کانال عمومی و گروه لینک‌شده، روی Local با توکن داخل `.env`:

```powershell
python manage.py shell -c "from main.telegram_same_day.client import bot_api; c=bot_api('getChat', {'chat_id':'@YOUR_CHANNEL'}); print('channel_id=', c['id']); print('discussion_group_id=', c.get('linked_chat_id'))"
```

برای کانال خصوصی numeric ID باید از اطلاعات معتبر کانال/رویداد دریافت شود؛ username جعلی یا نام نمایشی را جایگزین ID نکنید. از `getUpdates` هم‌زمان با webhook موجود استفاده نکنید.

## شیوهٔ انتشار و فروش

یک عکس را به‌صورت Photo، نه Document و نه Album، با caption زیر ارسال کنید:

```text
دسته گل آمادهٔ امروز
قیمت: ۲,۸۵۰,۰۰۰ تومان
```

قیمت را در یک خط مستقل بگذارید. ارقام فارسی/عربی/لاتین و جداکننده‌های `,`، `٬`، `،` و `/` پذیرفته می‌شوند. عدد بدون برچسب نیز در خط مستقل مجاز است. چند قیمت، عبارت «میلیون»، اعشار، ریال، صفر، مقدار منفی و رقم بیش از ۱۲ رقم پذیرفته نمی‌شود.

در Comments همان پست، اپراتور مجاز دقیقاً `فروخته شد` بنویسد. فاصله‌های اضافه و نیم‌فاصله تحمل می‌شوند. Reply مستقیم روی پست کانال نیز پشتیبانی می‌شود؛ مسیر معمول UI همان Comments است.

کامنت مستقیم روی فوروارد خودکار با `forward_origin.chat.id + forward_origin.message_id` متصل می‌شود. پاسخ به کامنت‌های بعدی از mapping ذخیره‌شده یا `message_thread_id` مربوط به یک root شناخته‌شده استفاده می‌کند. پاسخ ناشناس یا قدیمی بدون هویت قابل اثبات حدس زده نمی‌شود؛ اپراتور روی root اصلی مجدداً کامنت بگذارد.

ویرایش caption، قیمت همان محصول را عوض می‌کند؛ SOLD برگشت‌پذیر خودکار نیست. حذف پست تلگرام محصول را حذف نمی‌کند؛ Bot API رویداد عمومی قابل اتکایی برای این جریان حذف ارائه نمی‌کند. محصولات قدیمی کانال به‌صورت خودکار backfill نمی‌شوند؛ webhook برای پیام‌های دریافتی از زمان اتصال است.

## نصب روی Local (PowerShell)

دستورات در ریشهٔ پروژه با virtualenv فعال اجرا شوند. پچ دانلودشده را آنجا بگذارید. ابتدا وضعیت و نسخه را ببینید:

```powershell
cd 'D:\01 -- Clients\Behzad_Ramezani\Project\zad-website_v1.6'
git status --short
git rev-parse HEAD
git apply --check .\zad-telegram-same-day-a9e7804.patch
```

اگر check ناموفق بود، پچ را force نکنید؛ اختلاف نسخه باید تطبیق داده شود. برای نگه‌داشتن وضعیت فعلی:

```powershell
$ZadBackup = '..\zad-before-telegram-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
New-Item -ItemType Directory -Path $ZadBackup
git archive --format=zip --output="$ZadBackup\tracked-head.zip" HEAD
git diff HEAD --binary --output="$ZadBackup\local-changes.patch"
if (Test-Path .\db.sqlite3) { Copy-Item .\db.sqlite3 "$ZadBackup\db.sqlite3" }
```

archive و diff شامل فایل‌های untracked نیستند؛ در صورت وجود، نسخهٔ آن فایل‌ها را هم نگه دارید. سپس:

```powershell
git apply .\zad-telegram-same-day-a9e7804.patch
git diff --check
python manage.py check
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py migrate
python manage.py test
node --test ops/cloudflare/zad-telegram-relay-worker.test.mjs
```

دسته‌های موجود برای انتخاب ID:

```powershell
python manage.py shell -c "from main.models import Category; print(list(Category.objects.for_general_catalog().filter(section='flowers', is_active=True).values_list('pk','name')))"
```

متغیرهای مناسب را در `.env` قرار دهید، سپس:

```powershell
python manage.py telegram_same_day_webhook check
python manage.py runserver
```

تست‌های خودکار بدون توکن واقعی کار می‌کنند. برای تست زندهٔ Local باید یک endpoint عمومی HTTPS که به runserver می‌رسد داشته باشید؛ localhost برای Telegram قابل دسترسی نیست. برای تست زندهٔ محلی از ربات/کانال آزمایشی استفاده کنید تا webhook ربات production جابه‌جا نشود.

## نصب روی VPS

فایل پچ را مثلاً در `/home/cloud-admin/zad-telegram-same-day-a9e7804.patch` بگذارید.

```bash
cd /var/www/zad/app
ZAD_PY=/var/www/zad/venv/bin/python
git status --short
git rev-parse HEAD
git apply --check /home/cloud-admin/zad-telegram-same-day-a9e7804.patch
```

از source، `.env`، database و media طبق روال پشتیبان‌گیری فعلی نسخه بگیرید. نمونهٔ پشتیبان کد و media؛ تنظیمات محرمانه داخل این backup خصوصی باقی می‌مانند:

```bash
ZAD_BACKUP="/var/www/zad/backups/pre-telegram-same-day-$(date +%Y%m%d-%H%M%S)"
mkdir -p "$ZAD_BACKUP"
chmod 700 "$ZAD_BACKUP"
tar --exclude='./.git' --exclude='./staticfiles' --exclude='./.venv' --exclude='./media' -czf "$ZAD_BACKUP/app.tar.gz" .
tar -czf "$ZAD_BACKUP/media.tar.gz" media
export ZAD_BACKUP
"$ZAD_PY" - <<'PY'
import os, subprocess
from pathlib import Path
from dotenv import load_dotenv
load_dotenv('/var/www/zad/app/.env')
required = ('PGDATABASE', 'PGUSER', 'PGPASSWORD', 'PGHOST')
if not all(os.environ.get(k) for k in required):
    raise SystemExit('Missing PostgreSQL backup configuration')
output = Path(os.environ['ZAD_BACKUP']) / 'database.dump'
subprocess.run(['pg_dump', '-Fc', '--file', str(output)], check=True)
subprocess.run(['pg_restore', '-l', str(output)], check=True, stdout=subprocess.DEVNULL)
print('Database backup verified')
PY
```

در صورت موفق‌بودن backup و check پچ:

```bash
git apply /home/cloud-admin/zad-telegram-same-day-a9e7804.patch
git diff --check
"$ZAD_PY" manage.py check
"$ZAD_PY" manage.py makemigrations --check --dry-run
"$ZAD_PY" manage.py migrate --plan
"$ZAD_PY" manage.py migrate
```

تنظیم `.env` مسیر Worker و فعال‌کردن اپراتورها در Admin را انجام دهید. سپس:

```bash
"$ZAD_PY" manage.py telegram_same_day_webhook check
sudo systemctl restart zad.service
sudo systemctl is-active zad.service
curl -I https://www.zadconcept.ir/
curl -i -X POST https://www.zadconcept.ir/api/telegram/webhook/ -H 'Content-Type: application/json' --data '{}'
```

درخواست آخر عمداً secret ندارد و باید **403** بدهد. endpoint باید بدون redirect و بدون challenge تعاملی Cloudflare در دسترس باشد؛ استثنای احتمالی WAF را فقط به همین مسیر محدود کنید. webhook نباید cache شود. فایل static تغییر نکرده؛ collectstatic برای این پچ لازم نیست.

تست PostgreSQL را روی staging یا database آزمایشی با کاربری که مجوز ساخت test database دارد اجرا کنید، نه با تغییر داده‌های production:

```bash
"$ZAD_PY" manage.py test main.tests.test_telegram_same_day main.tests.test_same_day_catalog main.tests.test_same_day_admin main.tests.test_telegram_product_lookup main.tests.test_telegram_lead_notifications main.tests.test_telegram_relay --verbosity 1
```

Django test runner دیتابیس آزمایشی مستقل می‌سازد. برای کاربر محدود production، تست را با تنظیمات staging و PostgreSQL جدا انجام دهید؛ به کاربر production صرفاً برای این تست مجوز اضافه ندهید.

## انتشار Worker و ثبت webhook

پس از آماده‌شدن Django، فایل `ops/cloudflare/zad-telegram-relay-worker.js` را در همان Worker موجود deploy کنید و متغیرهای جدول بالا را تنظیم کنید. توکن و secretهای قبلی را بی‌دلیل عوض نکنید.

ثبت webhook را از Local دارای دسترسی Telegram و توکن همان ربات در `.env` انجام دهید:

```powershell
python manage.py telegram_same_day_webhook register --url 'https://YOUR-WORKER.workers.dev/telegram-webhook'
python manage.py telegram_same_day_webhook info
```

برای ربات جداگانه با مسیر مستقیم:

```powershell
python manage.py telegram_same_day_webhook register --url 'https://www.zadconcept.ir/api/telegram/webhook/'
```

فرمان ثبت از Bot API `setWebhook` استفاده می‌کند، secret را از env می‌خواند، `allowed_updates` را روی `channel_post`, `edited_channel_post`, `message`, `edited_message` می‌گذارد و pending updates را پاک نمی‌کند. `info` صرفاً فعال‌بودن، تعداد pending و زمان آخرین خطا را چاپ می‌کند تا secret یا URL حساس وارد خروجی نشود.

## تأیید زنده پس از نصب

1. یک پست عکس تکی با قیمت مشخص ایجاد کنید؛ کد محصول جدید و عکس را در ارسال روز و Admin ببینید.
2. قیمت caption را عوض کنید؛ قیمت همان محصول باید تغییر کند و محصول دوم ساخته نشود.
3. با کاربر عادی بنویسید «فروخته شد»؛ محصول باید موجود بماند.
4. با اپراتور مجاز روی همان پست کامنت «فروخته شد» بگذارید؛ محصول باید SOLD و از لیست ارسال روز حذف شود.
5. caption را دوباره ویرایش کنید؛ محصول نباید موجود شود.
6. یک محصول قدیمی ساخته‌شده از Admin را بررسی کنید.
7. برای ربات موجود یک جست‌وجوی کد محصول و یک فرم سایت را تست کنید تا مسیرهای قبلی هم تأیید شوند.

لاگ‌ها:

```bash
sudo journalctl -u zad.service --since '15 minutes ago' --no-pager
```

رویدادها با update_id یا chat_id/message_id/product_id ثبت می‌شوند؛ caption، بدنهٔ درخواست، token و secret لاگ نمی‌شوند. `last_error` آخرین خطای دائمی پست در دیتابیس است. خطای 503 یعنی تنظیمات یا ارتباط/ذخیره‌سازی نیازمند رسیدگی است؛ در این حالت Telegram درخواست را دوباره می‌فرستد. بعد از قطعی طولانی، وضعیت pending را بررسی و در صورت از دست رفتن update، caption همان پست را دوباره ویرایش کنید.

## حدود پشتیبانی و rollback

- هر پست یک عکس Photo و یک محصول؛ Album، ویدئو و Document در این نسخه وارد کاتالوگ نمی‌شوند.
- لینک عکس قبلی هنگام جایگزینی حفظ می‌شود؛ پاک‌سازی media قدیمی را مستقل از این integration انجام دهید.
- دستور فروش صرفاً SOLD می‌کند؛ دستور خودکار موجودسازی مجدد یا حذف دیتابیس ندارد.
- برای توقف موقت با ربات مشترک، `SAME_DAY_WEBHOOK_URL` را از Worker حذف کنید؛ مسیرهای قبلی باقی می‌مانند. برای rollback کامل، کد Django و Worker را با هم از backup برگردانید. جدول‌های جدید را برای حفظ سوابق نگه دارید؛ downgrade migration پس از ثبت فروش، سوابق integration را حذف می‌کند و راه‌حل پیشنهادی نیست.
- اجرای زنده روی Telegram/VPS نیازمند تنظیم واقعی توکن، IDs، اپراتورها و deploy توسط شماست؛ تست‌های تحویلی API تلگرام را mock می‌کنند.

## منابع رسمی

- [Telegram Bot API: Message و forward_origin](https://core.telegram.org/bots/api#message)
- [MessageOriginChannel](https://core.telegram.org/bots/api#messageoriginchannel)
- [setWebhook و secret_token](https://core.telegram.org/bots/api#setwebhook)
- [getFile](https://core.telegram.org/bots/api#getfile)
- [پیام‌های قابل دریافت توسط ربات و privacy mode](https://core.telegram.org/bots/faq#what-messages-will-my-bot-get)

## گزارش تغییرات و اعتبارسنجی تحویل

فایل‌های تغییرکرده یا اضافه‌شده:

| فایل | تغییر |
| --- | --- |
| `.env.example` | نام تنظیمات جدید بدون secret |
| `config/settings.py` | envها و logger |
| `main/models.py` | status، مجوز اپراتور و دو مدل هویت پیام |
| `main/admin.py` | نمایش وضعیت ارسال روز و مجوز مستقل فروش؛ سازگاری فرم‌های قدیمی |
| `main/urls.py` | endpoint اختصاصی webhook |
| `main/migrations/0032_telegram_same_day_sync.py` | migration افزایشی |
| `main/telegram_same_day/__init__.py` | بستهٔ integration |
| `main/telegram_same_day/price.py` | parser قیمت |
| `main/telegram_same_day/client.py` | دانلود محدودشدهٔ Bot API و مسیر Worker |
| `main/telegram_same_day/validation.py` | اعتبارسنجی update |
| `main/telegram_same_day/service.py` | business logic و mapping و تراکنش |
| `main/telegram_same_day/webhook.py` | secret و HTTP handling |
| `main/management/commands/telegram_same_day_webhook.py` | check/register/info |
| `main/tests/test_telegram_same_day.py` | ۳۸ تست جدید |
| `ops/cloudflare/zad-telegram-relay-worker.js` | forward رویدادها و relay محدود دریافت فایل |
| `ops/cloudflare/zad-telegram-relay-worker.test.mjs` | تست‌های Worker جدید در کنار قبلی‌ها |
| `docs/telegram-integration.md` | ارجاع معماری قبلی به قابلیت جدید |
| `docs/telegram-same-day-fa.md` | راهنمای حاضر |

نتایج واقعی روی Python 3.13.15، Django 6.0.2 و SQLite:

- اجرای مجموعهٔ کامل: ۳۶۵ تست؛ ۳۶۴ پاس، یک skip مربوط به PostgreSQL، بدون failure/error.
- پس از افزودن تست rollback رسانه و اصلاح متن logging، مجموعهٔ اختصاصی نهایی: ۳۸ تست؛ ۳۷ پاس، همان یک skip. بنابراین فایل تحویل نسبت به اجرای کامل قبلی یک تست بیشتر دارد.
- Worker: هر ۱۶ تست پاس، شامل ۹ تست قبلی و ۷ تست جدید.
- `manage.py check`: بدون ایراد.
- `makemigrations --check --dry-run`: No changes detected.
- migration plan بررسی شد و migrationها تا 0032 در دیتابیس خالی آزمایشی واقعاً اجرا شدند.
- Python compileall، Node syntax check و `git diff --check` موفق.
- تست هم‌زمانی PostgreSQL نوشته شده، ولی در این محیط اجرا نشده: PostgreSQL نصب نبود و نصب سیستمی با محدودیت دسترسی سیستم متوقف شد. این مورد باید روی staging PostgreSQL اجرا شود.
- تماس زنده با Bot API، ثبت webhook واقعی و deploy روی VPS/Worker انجام نشده‌اند؛ token و IDs عملیاتی در اختیار این اجرا نبودند. تست جریان عکس→محصول→ویرایش→کامنت فروش→عدم نمایش، با درخواست HTTP Django و mock فقط در مرز دانلود Telegram انجام شده است.
# به‌روزرسانی گروه موجود

برای گروه آماده‌های ارسال بهزاد و قیمت در reply، [راهنمای گروه](telegram-group-products-fa.md) و پچ تکمیلی را بخوانید. تنظیم TELEGRAM_SAME_DAY_GROUP_ID جایگزین الزام کانال در این حالت است. مطالب زیر راهنمای حالت کانال اولیه هستند.
