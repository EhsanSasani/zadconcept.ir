"""Django settings for config project."""

import os
from pathlib import Path
from urllib.parse import urlsplit

from django.core.exceptions import ImproperlyConfigured
from django.utils.csp import CSP
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name, default=False):
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [item.strip() for item in os.getenv(name, default).split(",") if item.strip()]


def required_env(name):
    value = os.getenv(name)
    if not value:
        raise ImproperlyConfigured(f"Missing required production setting: {name}")
    return value


STATIC_URL = "/static/"
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles"))
# --- حالت اجرا و تنظیمات امنیتی پایه ---
_raw_env = os.getenv("ENV", "dev").strip().lower()
ENV = {"production": "prod", "development": "dev"}.get(_raw_env, _raw_env)
if ENV not in {"dev", "test", "prod"}:
    raise ImproperlyConfigured(
        "ENV must be one of dev, test, or prod (production is accepted as prod)."
    )
IS_PRODUCTION = ENV == "prod"
DEBUG_RAW = os.getenv("DEBUG")
if DEBUG_RAW is None:
    DEBUG = not IS_PRODUCTION
else:
    DEBUG = env_bool("DEBUG", default=not IS_PRODUCTION)

if IS_PRODUCTION:
    SECRET_KEY = required_env("SECRET_KEY")
else:
    SECRET_KEY = os.getenv("SECRET_KEY", "dev-insecure-key-change-me")

ALLOWED_HOSTS = env_list(
    "ALLOWED_HOSTS",
    "www.zadconcept.ir,zadconcept.ir" if IS_PRODUCTION else "127.0.0.1,localhost,testserver",
)
CSRF_TRUSTED_ORIGINS = env_list(
    "CSRF_TRUSTED_ORIGINS",
    "https://www.zadconcept.ir,https://zadconcept.ir" if IS_PRODUCTION else "",
)

if IS_PRODUCTION and (DEBUG or not ALLOWED_HOSTS or not CSRF_TRUSTED_ORIGINS):
    raise ImproperlyConfigured(
        "Production requires DEBUG=False, ALLOWED_HOSTS, and CSRF_TRUSTED_ORIGINS."
    )
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
    "django.middleware.http.ConditionalGetMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
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
                "django.template.context_processors.csp",
                "main.context_processors.site_defaults",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# --- دیتابیس (توسعه/تولید) ---
if IS_PRODUCTION:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.postgresql",
            "NAME": required_env("PGDATABASE"),
            "USER": required_env("PGUSER"),
            "PASSWORD": required_env("PGPASSWORD"),
            "HOST": required_env("PGHOST"),
            "PORT": os.getenv("PGPORT", "5432"),
            "CONN_MAX_AGE": int(os.getenv("PG_CONN_MAX_AGE", "60")),
        }
    }
    if os.getenv("PGSSLMODE"):
        DATABASES["default"]["OPTIONS"] = {"sslmode": os.getenv("PGSSLMODE")}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": Path(os.getenv("SQLITE_PATH", BASE_DIR / "db.sqlite3")),
        }
    }

# --- ذخیره‌سازی فایل‌ها و مدیا (لوکال/S3) ---
MEDIA_URL = "/media/"
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media"))

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": (
            "main.storage.ResilientManifestStaticFilesStorage"
            if IS_PRODUCTION and env_bool("USE_MANIFEST_STATIC", True)
            else "django.contrib.staticfiles.storage.StaticFilesStorage"
        )
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "zad-default-cache",
    }
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
ZAD_SITE_URL = os.getenv(
    "ZAD_SITE_URL",
    os.getenv("zad_SITE_URL", "https://www.zadconcept.ir"),
).rstrip("/")
_site_parts = urlsplit(ZAD_SITE_URL)
if (
    _site_parts.scheme != "https"
    or not _site_parts.hostname
    or _site_parts.path
    or _site_parts.query
    or _site_parts.fragment
    or _site_parts.username
    or _site_parts.password
):
    raise ImproperlyConfigured(
        "ZAD_SITE_URL must be an HTTPS origin without a path, for example "
        "https://www.zadconcept.ir"
    )

ZAD_CANONICAL_HOST = _site_parts.netloc
if IS_PRODUCTION and ZAD_CANONICAL_HOST not in ALLOWED_HOSTS and "*" not in ALLOWED_HOSTS:
    raise ImproperlyConfigured(
        "The canonical host from ZAD_SITE_URL must be present in ALLOWED_HOSTS."
    )
ZAD_PHONE_DISPLAY = os.getenv("ZAD_PHONE_DISPLAY", os.getenv("zad_PHONE_DISPLAY", "09154203569"))
ZAD_PHONE_E164 = os.getenv("ZAD_PHONE_E164", os.getenv("zad_PHONE_E164", "+989154203569"))
ZAD_TELEGRAM_URL = os.getenv("ZAD_TELEGRAM_URL", os.getenv("zad_TELEGRAM_URL", "https://t.me/Flowerhouse_pv"))
ZAD_TELEGRAM_DISPLAY = os.getenv("ZAD_TELEGRAM_DISPLAY", os.getenv("zad_TELEGRAM_DISPLAY", "@Flowerhouse_pv"))
ZAD_BALE_URL = os.getenv(
    "ZAD_BALE_URL",
    os.getenv("zad_BALE_URL", "https://ble.ir/flowerhouse_pv"),
)
ZAD_BALE_DISPLAY = os.getenv(
    "ZAD_BALE_DISPLAY",
    os.getenv("zad_BALE_DISPLAY", "@flowerhouse_pv"),
)
ZAD_EMAIL = os.getenv("ZAD_EMAIL", os.getenv("zad_EMAIL", ""))
ZAD_INSTAGRAM_URL = os.getenv("ZAD_INSTAGRAM_URL", os.getenv("zad_INSTAGRAM_URL", "https://www.instagram.com/zad_concept/"))
ZAD_OPENING_HOURS_TEXT = os.getenv("ZAD_OPENING_HOURS_TEXT", os.getenv("zad_OPENING_HOURS_TEXT", "هر روز ۱۰:۰۰ تا ۲۲:۰۰"))
ZAD_RESPONSE_TIME_TEXT = os.getenv("ZAD_RESPONSE_TIME_TEXT", os.getenv("zad_RESPONSE_TIME_TEXT", "زمان متوسط پاسخ‌گویی: حدود ۱۵ دقیقه"))
ZAD_ADDRESS_STREET = os.getenv("ZAD_ADDRESS_STREET", os.getenv("zad_ADDRESS_STREET", "بلوار وکیل اباد - نبش فارغ التحصیلان 6 - کانسپت زاد"))
ZAD_ADDRESS_LOCALITY = os.getenv("ZAD_ADDRESS_LOCALITY", os.getenv("zad_ADDRESS_LOCALITY", "مشهد"))
ZAD_ADDRESS_REGION = os.getenv("ZAD_ADDRESS_REGION", os.getenv("zad_ADDRESS_REGION", "خراسان رضوی"))
ZAD_ADDRESS_COUNTRY = os.getenv("ZAD_ADDRESS_COUNTRY", os.getenv("zad_ADDRESS_COUNTRY", "IR"))
ZAD_ADDRESS_POSTAL_CODE = os.getenv("ZAD_ADDRESS_POSTAL_CODE", os.getenv("zad_ADDRESS_POSTAL_CODE", ""))
ZAD_DEFAULT_SOCIAL_IMAGE = os.getenv(
    "ZAD_DEFAULT_SOCIAL_IMAGE",
    f"{ZAD_SITE_URL}{STATIC_URL}main/img/hero-1.webp",
)
ZAD_DEFAULT_SOCIAL_IMAGE_WIDTH = int(
    os.getenv("ZAD_DEFAULT_SOCIAL_IMAGE_WIDTH", "1920")
)
ZAD_DEFAULT_SOCIAL_IMAGE_HEIGHT = int(
    os.getenv("ZAD_DEFAULT_SOCIAL_IMAGE_HEIGHT", "1080")
)
ZAD_LOGO_URL = os.getenv(
    "ZAD_LOGO_URL",
    f"{ZAD_SITE_URL}{STATIC_URL}main/img/favicon.svg",
)
ZAD_LOGO_WIDTH = int(os.getenv("ZAD_LOGO_WIDTH", "512"))
ZAD_LOGO_HEIGHT = int(os.getenv("ZAD_LOGO_HEIGHT", "512"))

# Backwards-compatible aliases for the current code and older server .env files.
zad_SITE_URL = ZAD_SITE_URL
zad_PHONE_DISPLAY = ZAD_PHONE_DISPLAY
zad_PHONE_E164 = ZAD_PHONE_E164
zad_TELEGRAM_URL = ZAD_TELEGRAM_URL
zad_TELEGRAM_DISPLAY = ZAD_TELEGRAM_DISPLAY
zad_BALE_URL = ZAD_BALE_URL
zad_BALE_DISPLAY = ZAD_BALE_DISPLAY
zad_EMAIL = ZAD_EMAIL
zad_INSTAGRAM_URL = ZAD_INSTAGRAM_URL
zad_OPENING_HOURS_TEXT = ZAD_OPENING_HOURS_TEXT
zad_RESPONSE_TIME_TEXT = ZAD_RESPONSE_TIME_TEXT
zad_ADDRESS_STREET = ZAD_ADDRESS_STREET
zad_ADDRESS_LOCALITY = ZAD_ADDRESS_LOCALITY
zad_ADDRESS_REGION = ZAD_ADDRESS_REGION
zad_ADDRESS_COUNTRY = ZAD_ADDRESS_COUNTRY
zad_ADDRESS_POSTAL_CODE = ZAD_ADDRESS_POSTAL_CODE

# Search verification and analytics are enabled only after real IDs are supplied.
GOOGLE_SITE_VERIFICATION = os.getenv("GOOGLE_SITE_VERIFICATION", "")
BING_SITE_VERIFICATION = os.getenv("BING_SITE_VERIFICATION", "")
GOOGLE_TAG_ID = os.getenv("GOOGLE_TAG_ID", "")

# IndexNow keeps network activity outside user requests; use the management command/timer.
INDEXNOW_KEY = os.getenv("INDEXNOW_KEY", "")
INDEXNOW_ENDPOINT = os.getenv("INDEXNOW_ENDPOINT", "https://api.indexnow.org/indexnow")
INDEXNOW_STATE_FILE = Path(
    os.getenv("INDEXNOW_STATE_FILE", BASE_DIR / "var" / "indexnow-state.json")
)

LEAD_RATE_LIMIT_COUNT = int(os.getenv("LEAD_RATE_LIMIT_COUNT", "5"))
LEAD_RATE_LIMIT_WINDOW = int(os.getenv("LEAD_RATE_LIMIT_WINDOW", "300"))

# --- Production transport and browser security ---
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https") if IS_PRODUCTION else None
SECURE_SSL_REDIRECT = IS_PRODUCTION
SECURE_SSL_HOST = ZAD_CANONICAL_HOST if IS_PRODUCTION else None
PREPEND_WWW = IS_PRODUCTION and ZAD_CANONICAL_HOST.startswith("www.")
USE_X_FORWARDED_HOST = IS_PRODUCTION
CSRF_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_SECURE = IS_PRODUCTION
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "31536000" if IS_PRODUCTION else "0"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

_csp_policy = {
    "default-src": [CSP.SELF],
    "base-uri": [CSP.SELF],
    "connect-src": [
        CSP.SELF,
        "https://*.google-analytics.com",
        "https://*.analytics.google.com",
        "https://*.googletagmanager.com",
    ],
    "font-src": [CSP.SELF, "data:"],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
    "frame-src": [CSP.NONE],
    "img-src": [CSP.SELF, "data:", "https://*.google-analytics.com"],
    "object-src": [CSP.NONE],
    "script-src": [CSP.SELF, CSP.NONCE, "https://www.googletagmanager.com"],
    "style-src": [CSP.SELF],
    "report-uri": ["/csp-report/"],
}

if IS_PRODUCTION and env_bool("CSP_ENFORCE", False):
    SECURE_CSP = _csp_policy
    SECURE_CSP_REPORT_ONLY = {}
elif IS_PRODUCTION:
    SECURE_CSP = {}
    SECURE_CSP_REPORT_ONLY = _csp_policy
else:
    SECURE_CSP = {}
    SECURE_CSP_REPORT_ONLY = {}

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {
        "main.security": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "main.indexnow": {"handlers": ["console"], "level": "INFO", "propagate": False},
    },
}


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
        "main.SameDayFlower",
        "main.HomeHeroSlide",
        "main.SiteHero",
        "main.HeroFont",
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
        "main.SameDayFlower": "fas fa-bolt",
        "main.HomeHeroSlide": "fas fa-images",
        "main.SiteHero": "fas fa-image",
        "main.HeroFont": "fas fa-font",
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

X_FRAME_OPTIONS = "DENY"
