"""Django settings for config project."""

import os
from pathlib import Path

from dotenv import load_dotenv

# --- بارگذاری متغیرهای محیطی و مسیر پایه پروژه ---
load_dotenv()

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
# --- حالت اجرا و تنظیمات امنیتی پایه ---
ENV = os.getenv("ENV", "dev").lower()
DEBUG_RAW = os.getenv("DEBUG")
if DEBUG_RAW is None:
    DEBUG = ENV == "dev"
else:
    debug_value = DEBUG_RAW.strip().lower()
    if debug_value in {"1", "true", "yes", "on"}:
        DEBUG = True
    elif debug_value in {"0", "false", "no", "off"}:
        DEBUG = False
    else:
        DEBUG = ENV == "dev"
SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")
ALLOWED_HOSTS = [
    h.strip()
    for h in os.getenv("ALLOWED_HOSTS", "127.0.0.1,localhost").split(",")
    if h.strip()
]
CSRF_TRUSTED_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CSRF_TRUSTED_ORIGINS", "").split(",")
    if origin.strip()
]
# --- تعریف اپ‌ها و میان‌افزارها ---
INSTALLED_APPS = [
    "jazzmin",

    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.sitemaps",
    "django.contrib.staticfiles",
    "main.apps.MainConfig",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

# --- تنظیم موتور قالب و context processorها ---
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "main.context_processors.site_defaults",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- دیتابیس (توسعه/تولید) ---
if ENV == "prod":
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": os.getenv("PGDATABASE"),
            "USER": os.getenv("PGUSER"),
            "PASSWORD": os.getenv("PGPASSWORD"),
            "HOST": os.getenv("PGHOST"),
            "PORT": os.getenv("PGPORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- ذخیره‌سازی فایل‌ها و مدیا (لوکال/S3) ---
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

# --- اعتبارسنجی رمز عبور ---
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- بومی‌سازی و منطقه زمانی ---
LANGUAGE_CODE = "fa"
TIME_ZONE = "Asia/Tehran"
USE_I18N = True
USE_TZ = True

# --- پیش‌فرض کلید اصلی مدل‌ها ---
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- اطلاعات پایه کسب‌وکار برای SEO/CTA ---
zad_SITE_URL = os.getenv("zad_SITE_URL", "https://zadconcept.ir")
zad_PHONE_DISPLAY = os.getenv("zad_PHONE_DISPLAY", "09154203569")
zad_PHONE_E164 = os.getenv("zad_PHONE_E164", "+989154203569")
zad_TELEGRAM_URL = os.getenv("zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv")
zad_TELEGRAM_DISPLAY = os.getenv("zad_TELEGRAM_DISPLAY", "@Flowerhouse_pv")
zad_EMAIL = os.getenv("zad_EMAIL", "")
zad_INSTAGRAM_URL = os.getenv("zad_INSTAGRAM_URL", "https://www.instagram.com/zad_concept/")
zad_OPENING_HOURS_TEXT = os.getenv("zad_OPENING_HOURS_TEXT", "هر روز ۱۰:۰۰ تا ۲۲:۰۰")
zad_RESPONSE_TIME_TEXT = os.getenv("zad_RESPONSE_TIME_TEXT", "زمان متوسط پاسخ‌گویی: حدود ۱۵ دقیقه")
zad_ADDRESS_STREET = os.getenv("zad_ADDRESS_STREET", "بلوار وکیل اباد - نبش فارغ التحصیلان 6 - کانسپت زاد")
zad_ADDRESS_LOCALITY = os.getenv("zad_ADDRESS_LOCALITY", "مشهد")
zad_ADDRESS_REGION = os.getenv("zad_ADDRESS_REGION", "خراسان رضوی")
zad_ADDRESS_COUNTRY = os.getenv("zad_ADDRESS_COUNTRY", "IR")
zad_ADDRESS_POSTAL_CODE = os.getenv("zad_ADDRESS_POSTAL_CODE", "")


JAZZMIN_SETTINGS = {
    "site_title": "zad Admin",
    "site_header": "zad",
    "site_brand": "zad Admin",
    "welcome_sign": "خوش آمدید به پنل مدیریت زاد",
    "copyright": "zad Concept Store",
    "hide_models": [
            "main.ProductImage",
            "main.NewsPost",
            "main.WorkshopPageContent",
            "main.PageContentBlock",
        ],
    "search_model": [
        "main.Product",
        
    ],
    "topmenu_links": [
        {"name": "سایت", "url": "/", "new_window": True},
        {"model": "auth.User"},
    ],
    "show_sidebar": True,
    "navigation_expanded": True,
    "order_with_respect_to": [
        "main",
        "main.Product",
        "main.Flower",
        "main.BakeryItem",
        "main.GiftItem",
        "main.Category",
        "main.Tag",
        "main.LeadRequest",
        "main.Event",
    ],
    "icons": {
        "auth": "fas fa-users-cog",
        "auth.user": "fas fa-user",
        "auth.Group": "fas fa-users",
        "main.Product": "fas fa-box-open",
        "main.Flower": "fas fa-seedling",
        "main.BakeryItem": "fas fa-birthday-cake",
        "main.GiftItem": "fas fa-gift",
        "main.Category": "fas fa-sitemap",
        "main.Tag": "fas fa-tags",
        "main.LeadRequest": "fas fa-phone-alt",
        "main.Event": "fas fa-calendar-alt",
    },
    
    "default_icon_parents": "fas fa-folder",
    "default_icon_children": "fas fa-circle",
    "related_modal_active": True,
    "changeform_format": "horizontal_tabs",
    "custom_css": "main/css/admin_custom.css",
    "use_google_fonts_cdn": False,
}

JAZZMIN_UI_TWEAKS = {
    "theme": "default",
    "default_theme_mode": "dark",
    "navbar": "navbar-dark",
    "no_navbar_border": True,
    "sidebar": "sidebar-dark-primary",
    "accent": "accent-lightblue",
    "navbar_small_text": False,
    "footer_small_text": False,
    "body_small_text": False,
    "brand_small_text": False,
    "sidebar_nav_small_text": False,
    "sidebar_disable_expand": False,
    "sidebar_nav_child_indent": True,
    "sidebar_nav_compact_style": False,
    "sidebar_nav_legacy_style": False,
    "sidebar_nav_flat_style": False,
    "theme_switcher": False,
}

X_FRAME_OPTIONS = "SAMEORIGIN"
