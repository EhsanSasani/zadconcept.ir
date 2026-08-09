"""Existing model definitions kept stable while domains are extracted."""

import uuid
from pathlib import PurePosixPath

from django.core.exceptions import ValidationError
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
    RegexValidator,
)
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.text import Truncator, slugify


# =========================
# Catalog constants
# =========================

FLOWER_CATEGORY_SLUGS = (
    "hand-bouquet",
    "box",
    "bouquet",
    "stand",
    "jarl",
    "wedding",
    "wedding-car",
    "bridal-bouquet",
    "plants",
)

FLOWER_WEDDING_CATEGORY_SLUGS = (
    "wedding",
)

FLOWER_OCCASION_TAG_SLUGS = (
    "birthday",
    "romantic",
    "congratulation",
    "apology",
    "condolence",
    "proposal",
    "engagement",
    "no-occasion",
)

SAME_DAY_TAG_SLUG = "same-day"

PRODUCT_SEO_CATEGORY_LABELS = {
    "hand-bouquet": "دسته گل",
    "box": "باکس گل",
    "bouquet": "بوکت گل",
    "stand": "استند گل",
    "jarl": "جار گل",
    "plants": "گیاه هدیه‌ای",
    "wedding": "گل‌آرایی عروسی",
    "wedding-car": "گل‌آرایی ماشین عروس",
    "bridal-bouquet": "دسته‌گل عروس",
}

PRODUCT_CARD_TYPE_LABELS = {
    "hand-bouquet": "HAND BOUQUET",
    "box": "BOX",
    "bouquet": "BOUQUET",
    "jarl": "JARL",
    "wedding": "WEDDING",
    "wedding-car": "WEDDING CAR",
    "bridal-bouquet": "BRIDAL BOUQUET",
    "stand": "STAND",
    "plants": "PLANTS",
}

PRODUCT_CARD_FALLBACK_IMAGES = {
    "flowers": "main/img/cat-flowers.webp",
    "bakery": "main/img/cat-bakery.webp",
    "gifts": "main/img/cat-gifts.webp",
}

HERO_POSITION_CHOICES = (
    ("top-left", "بالا چپ"),
    ("top-center", "بالا وسط"),
    ("top-right", "بالا راست"),
    ("center-left", "وسط چپ"),
    ("center", "وسط"),
    ("center-right", "وسط راست"),
    ("bottom-left", "پایین چپ"),
    ("bottom-center", "پایین وسط"),
    ("bottom-right", "پایین راست"),
)

HERO_BUILTIN_FONT_CHOICES = (
    ("estedad", "استعداد (فارسی)"),
    ("vazirmatn", "وزیرمتن (فارسی)"),
    ("cormorant", "Cormorant Garamond (انگلیسی)"),
    ("jakarta", "Plus Jakarta Sans (انگلیسی)"),
)

HEX_COLOR_VALIDATOR = RegexValidator(
    regex=r"^#[0-9a-fA-F]{6}$",
    message="رنگ را به فرمت شش‌رقمی وارد کنید؛ مثل #FFFFFF.",
)

MAX_HERO_FONT_SIZE = 5 * 1024 * 1024

PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def validate_hero_font_file_size(uploaded_file):
    if not uploaded_file:
        return
    try:
        file_size = uploaded_file.size
    except (AttributeError, OSError, ValueError):
        # An already-saved file may temporarily be unavailable on storage.
        # Rendering has its own font fallback, so editing other fields must remain safe.
        return
    if file_size > MAX_HERO_FONT_SIZE:
        raise ValidationError("حجم فایل فونت نباید بیشتر از ۵ مگابایت باشد.")


def responsive_image_srcset(image_field, widths=(520, 1040, 1600)):
    if not image_field or not image_field.name:
        return ""
    path = PurePosixPath(image_field.name)
    candidates = []
    for width in widths:
        variant = path.with_name(f"{path.stem}-{width}w.webp")
        try:
            exists = image_field.storage.exists(str(variant))
        except OSError:
            exists = False
        if exists:
            candidates.append(f"{image_field.storage.url(str(variant))} {width}w")
    # A single small candidate can unnecessarily replace a larger original.
    return ", ".join(candidates) if len(candidates) >= 2 else ""

class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("زمان ایجاد", auto_now_add=True)
    updated_at = models.DateTimeField("آخرین ویرایش", auto_now=True)

    class Meta:
        abstract = True


def make_unique_slug(instance, value, slug_field_name="slug", queryset=None):
    slug = slugify(value or "", allow_unicode=True)

    if not slug:
        slug = f"item-{uuid.uuid4().hex[:8]}"

    if queryset is None:
        # Proxy managers (Flower/BakeryItem/GiftItem) only see one section,
        # while Product.slug is unique across the concrete Product table.
        # Always check the concrete model so cross-section names cannot cause
        # an IntegrityError during the second save.
        queryset = instance._meta.concrete_model._default_manager.all()

    if instance.pk:
        queryset = queryset.exclude(pk=instance.pk)

    base_slug = slug
    index = 2

    while queryset.filter(**{slug_field_name: slug}).exists():
        slug = f"{base_slug}-{index}"
        index += 1

    return slug


def _upload_slug(value, fallback):
    slug = slugify(value or "", allow_unicode=False)
    return slug or fallback


def _upload_extension(filename):
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "webp"
    if extension == "jpeg":
        extension = "jpg"
    return extension


def category_cover_upload_to(instance, filename):
    section = _upload_slug(instance.section, "category")
    slug = _upload_slug(instance.slug or instance.name, f"category-{instance.pk or 'new'}")
    return f"categories/category-{section}-{slug}.{_upload_extension(filename)}"


def tag_cover_upload_to(instance, filename):
    slug = _upload_slug(instance.slug or instance.name, f"tag-{instance.pk or 'new'}")
    return f"tags/tag-{slug}.{_upload_extension(filename)}"


def product_cover_upload_to(instance, filename):
    code = _upload_slug(instance.product_code or instance.slug, f"product-{instance.pk or 'new'}")
    return f"products/covers/product-{code}.{_upload_extension(filename)}"


def product_gallery_upload_to(instance, filename):
    product = getattr(instance, "product", None)
    code = _upload_slug(
        getattr(product, "product_code", "") or getattr(product, "slug", ""),
        f"product-{getattr(instance, 'product_id', None) or 'new'}",
    )
    order = instance.ordering or instance.pk or "new"
    return f"products/gallery/product-{code}-gallery-{order}.{_upload_extension(filename)}"


def news_cover_upload_to(instance, filename):
    slug = _upload_slug(instance.slug or instance.title, f"news-{instance.pk or 'new'}")
    return f"news/covers/news-{slug}.{_upload_extension(filename)}"


def event_cover_upload_to(instance, filename):
    slug = _upload_slug(instance.slug or instance.title, f"event-{instance.pk or 'new'}")
    return f"events/covers/event-{slug}.{_upload_extension(filename)}"


def home_hero_upload_to(instance, filename):
    order = instance.sort_order or instance.pk or "new"
    return f"heroes/home/home-hero-{order}.{_upload_extension(filename)}"


def home_hero_mobile_upload_to(instance, filename):
    order = instance.sort_order or instance.pk or "new"
    return f"heroes/home/mobile/home-hero-mobile-{order}.{_upload_extension(filename)}"


def site_hero_upload_to(instance, filename):
    page = _upload_slug(instance.target_page, "page")
    target = _upload_slug(instance.target_slug, "default")
    order = instance.sort_order or instance.pk or "new"
    return f"heroes/pages/page-hero-{page}-{target}-{order}.{_upload_extension(filename)}"


def site_hero_mobile_upload_to(instance, filename):
    page = _upload_slug(instance.target_page, "page")
    target = _upload_slug(instance.target_slug, "default")
    order = instance.sort_order or instance.pk or "new"
    return f"heroes/pages/mobile/page-hero-{page}-{target}-{order}-mobile.{_upload_extension(filename)}"


def hero_font_upload_to(instance, filename):
    name = _upload_slug(instance.name, f"font-{instance.pk or 'new'}")
    extension = filename.rsplit(".", 1)[-1].lower() if "." in filename else "woff2"
    return f"heroes/fonts/hero-font-{name}.{extension}"


class Category(TimeStampedModel):
    class Section(models.TextChoices):
        FLOWERS = "flowers", "گل‌ها"
        BAKERY = "bakery", "بیکری"
        GIFTS = "gifts", "هدایا"
        EVENTS = "events", "رویدادها"

    name = models.CharField("نام زیر‌دسته", max_length=100)
    slug = models.SlugField(
        "اسلاگ",
        max_length=120,
        db_index=True,
        blank=True,
        allow_unicode=True,
        help_text="اگر خالی بماند، خودکار از نام ساخته می‌شود. برای لینک بهتر، انگلیسی وارد کن؛ مثل bouquet یا box.",
    )

    section = models.CharField(
        "بخش اصلی",
        max_length=20,
        choices=Section.choices,
        db_index=True,
    )

    parent = models.ForeignKey(
        "self",
        verbose_name="دسته والد",
        on_delete=models.PROTECT,
        related_name="children",
        null=True,
        blank=True,
        help_text=(
            "فقط برای ساخت زیردسته انتخاب شود. مثال: «ماشین عروس» و "
            "«دسته‌گل عروس» هر دو والد «عروسی» دارند."
        ),
    )

    description = models.TextField("توضیح کوتاه", blank=True)

    cover_image = models.ImageField(
        "تصویر زیر‌دسته",
        upload_to=category_cover_upload_to,
        blank=True,
        null=True,
    )

    is_active = models.BooleanField("فعال باشد؟", default=True, db_index=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["section", "sort_order", "name"]
        verbose_name = "زیر‌دسته"
        verbose_name_plural = "زیر‌دسته‌ها"
        constraints = [
            models.UniqueConstraint(
                fields=["section", "slug"],
                name="uniq_category_section_slug",
            ),
            models.UniqueConstraint(
                fields=["section", "name"],
                name="uniq_category_section_name",
            ),
        ]
        indexes = [
            models.Index(fields=["section", "is_active", "sort_order"]),
        ]

    def __str__(self) -> str:
        if self.parent_id:
            return f"{self.get_section_display()} / {self.parent.name} / {self.name}"
        return f"{self.get_section_display()} / {self.name}"

    @property
    def is_flower_category(self):
        return self.section == self.Section.FLOWERS

    @property
    def is_wedding_flower_category(self):
        return self.section == self.Section.FLOWERS and (
            self.slug in FLOWER_WEDDING_CATEGORY_SLUGS
            or (
                self.parent_id
                and self.parent.slug in FLOWER_WEDDING_CATEGORY_SLUGS
            )
        )

    @property
    def is_leaf(self):
        if not self.pk:
            return True
        return not self.children.exists()

    def clean(self):
        super().clean()

        if not self.parent_id:
            return

        if self.pk and self.parent_id == self.pk:
            raise ValidationError({"parent": "یک دسته نمی‌تواند والد خودش باشد."})

        if self.parent.section != self.section:
            raise ValidationError(
                {"parent": "دسته والد و زیردسته باید در یک بخش اصلی باشند."}
            )

        if self.parent.parent_id:
            raise ValidationError(
                {"parent": "ساختار دسته‌بندی زاد حداکثر دو سطح دارد."}
            )

    def save(self, *args, **kwargs):
        if not self.slug:
            queryset = Category.objects.filter(section=self.section)
            self.slug = make_unique_slug(self, self.name, queryset=queryset)
        else:
            self.slug = slugify(self.slug, allow_unicode=True)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        route_name = {
            self.Section.FLOWERS: "flower_subcategory",
            self.Section.BAKERY: "bakery_subcategory",
            self.Section.GIFTS: "gift_subcategory",
        }.get(self.section)
        if not route_name:
            return reverse("events")
        return reverse(route_name, args=[self.slug])


class Tag(TimeStampedModel):
    name = models.CharField("نام برچسب", max_length=50, unique=True)
    slug = models.SlugField(
        "اسلاگ",
        max_length=80,
        unique=True,
        blank=True,
        allow_unicode=True,
        help_text="اگر خالی بماند، خودکار ساخته می‌شود. برای لینک بهتر، انگلیسی وارد کن؛ مثل birthday یا romantic.",
    )

    description = models.TextField("توضیح کوتاه", blank=True)

    cover_image = models.ImageField(
        "تصویر کارت مناسبتی",
        upload_to=tag_cover_upload_to,
        blank=True,
        null=True,
        help_text="برای کارت‌های مناسبتی مثل تولد، تسلیت، عاشقانه و ...",
    )

    is_occasion = models.BooleanField(
        "در کارت‌های مناسبتی نمایش داده شود؟",
        default=False,
        db_index=True,
    )

    is_active = models.BooleanField("فعال باشد؟", default=True, db_index=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name = "برچسب"
        verbose_name_plural = "برچسب‌ها"
        indexes = [
            models.Index(fields=["is_occasion", "is_active", "sort_order"]),
        ]

    def __str__(self) -> str:
        return self.name

    @property
    def is_flower_occasion(self):
        return self.slug in FLOWER_OCCASION_TAG_SLUGS

    @property
    def is_same_day(self):
        return self.slug == SAME_DAY_TAG_SLUG

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_unique_slug(self, self.name)
        else:
            self.slug = slugify(self.slug, allow_unicode=True)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("occasion_detail", args=[self.slug])


class ProductQuerySet(models.QuerySet):
    """Composable product policy shared by selectors and proxy admins."""

    def active(self):
        return self.filter(
            Q(category__parent__isnull=True) | Q(category__parent__is_active=True),
            is_active=True,
            category__is_active=True,
        )

    def published(self):
        return self.active().filter(publish_status="published")

    def for_section(self, section):
        return self.filter(category__section=section)

    def same_day(self):
        return self.filter(tags__slug=SAME_DAY_TAG_SLUG).distinct()

    def with_card_relations(self):
        return self.select_related("category", "category__parent")

    def with_detail_relations(self):
        return self.with_card_relations().prefetch_related(
            "tags",
            "gallery_images",
        )


class Product(TimeStampedModel):
    class PricingType(models.TextChoices):
        FIXED = "fixed", "قیمت ثابت"
        INQUIRY = "inquiry", "استعلام قیمت"

    class StockStatus(models.TextChoices):
        IN_STOCK = "in_stock", "موجود"
        OUT_OF_STOCK = "out_of_stock", "ناموجود"
        PREORDER = "preorder", "پیش‌سفارش"

    class PublishStatus(models.TextChoices):
        DRAFT = "draft", "پیش‌نویس"
        PUBLISHED = "published", "منتشرشده"

    name = models.CharField("نام محصول", max_length=120, blank=True)
    product_code = models.CharField(
    "کد محصول",
    unique=True,
    max_length=40,
    blank=True,
    editable=False,
)
    slug = models.SlugField(
        "اسلاگ",
        max_length=160,
        unique=True,
        blank=True,
        allow_unicode=True,
        help_text="اگر خالی بماند، خودکار از نام محصول ساخته می‌شود.",
    )

    description = models.TextField("توضیحات", blank=True)

    pricing_type = models.CharField(
        "نوع قیمت‌گذاری",
        max_length=20,
        choices=PricingType.choices,
        default=PricingType.INQUIRY,
        db_index=True,
    )

    price = models.DecimalField(
        "قیمت به تومان",
        max_digits=12,
        decimal_places=0,
        null=True,
        blank=True,
        help_text="فقط عدد وارد کن؛ مثلاً 2500000. اگر قیمت استعلامی باشد، این فیلد خالی می‌ماند.",
    )
    price_usd = models.DecimalField(
        "قیمت دلاری",
        max_digits=8,
        decimal_places=2,
        null=True,
        blank=True,
    )

    cover_image = models.ImageField(
        "تصویر اصلی",
        upload_to=product_cover_upload_to,
        null=True,
        blank=True,
    )

    category = models.ForeignKey(
        Category,
        verbose_name="زیر‌دسته",
        on_delete=models.PROTECT,
        related_name="products",
        help_text="نوع فیزیکی محصول؛ مثل دسته گل، باکس، استند، کیک تولد، شمع و ...",
    )

    tags = models.ManyToManyField(
        Tag,
        verbose_name="برچسب‌ها",
        related_name="products",
        blank=True,
        help_text="مناسبت یا کاربرد محصول؛ مثل تولد، ترحیم، ارسال روز، عاشقانه، یونیک و ...",
    )

    is_active = models.BooleanField("فعال باشد؟", default=True, db_index=True)

    publish_status = models.CharField(
        "وضعیت انتشار",
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )

    stock_status = models.CharField(
        "وضعیت موجودی",
        max_length=20,
        choices=StockStatus.choices,
        default=StockStatus.IN_STOCK,
        db_index=True,
    )

    featured = models.BooleanField("ویژه باشد؟", default=False, db_index=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "-created_at"]
        verbose_name = "محصول"
        verbose_name_plural = "محصولات"
        constraints = [
            models.CheckConstraint(
                condition=Q(price__isnull=True) | Q(price__gte=0),
                name="product_price_is_positive_or_null",
            ),
        ]
        indexes = [
            models.Index(fields=["category", "is_active", "publish_status"]),
            models.Index(fields=["featured", "sort_order"]),
            models.Index(fields=["sort_order", "-created_at"]),
            models.Index(fields=["pricing_type", "stock_status"]),
        ]

    def __str__(self):
        return self.display_name

    @property
    def section(self):
        if self.category_id:
            return self.category.section
        return None

    @property
    def section_display(self):
        if self.category_id:
            return self.category.get_section_display()
        return "-"

    @property
    def is_published(self):
        return self.is_active and self.publish_status == self.PublishStatus.PUBLISHED
    @property
    def display_name(self):
        clean_name = self.name.strip() if self.name else ""
        return clean_name or self.product_code or f"{self.pk or 'NEW'}"

    @property
    def card_type_label(self):
        if not self.category_id:
            return "COLLECTION"
        return PRODUCT_CARD_TYPE_LABELS.get(
            self.category.slug,
            self.category.slug.replace("-", " ").upper(),
        )

    @property
    def card_fallback_image(self):
        return PRODUCT_CARD_FALLBACK_IMAGES.get(
            self.section,
            "main/img/cat-flowers.webp",
        )

    @property
    def seo_category_name(self):
        if not self.category_id:
            return "محصول"
        if self.category.slug in PRODUCT_SEO_CATEGORY_LABELS:
            return PRODUCT_SEO_CATEGORY_LABELS[self.category.slug]
        if self.category.section == Category.Section.BAKERY:
            return f"محصول سوئیت‌بار {self.category.name}"
        if self.category.section == Category.Section.GIFTS:
            return f"هدیه {self.category.name}"
        return self.category.name or "محصول"

    @property
    def seo_name(self):
        clean_name = self.name.strip() if self.name else ""
        code = (self.product_code or str(self.pk or "")).translate(PERSIAN_DIGITS)
        if clean_name:
            if code:
                return f"{clean_name}، کد {code}"
            return clean_name
        if code:
            return f"{self.seo_category_name} زاد، کد {code}"
        return f"{self.seo_category_name} زاد"

    @property
    def seo_description(self):
        description = " ".join((self.description or "").split())
        code = (self.product_code or str(self.pk or "")).translate(PERSIAN_DIGITS)
        if description:
            suffix = f" کد محصول: {code}." if code else ""
            return Truncator(f"{description}{suffix}").chars(160)
        return Truncator(
            f"{self.seo_name}؛ بررسی موجودی، استعلام قیمت و هماهنگی سفارش و ارسال در مشهد."
        ).chars(160)

    @property
    def schema_availability(self):
        if self.stock_status == self.StockStatus.OUT_OF_STOCK:
            return "https://schema.org/OutOfStock"
        if self.stock_status == self.StockStatus.PREORDER:
            return "https://schema.org/PreOrder"
        return "https://schema.org/InStock"

    @cached_property
    def cover_srcset(self):
        return responsive_image_srcset(self.cover_image)

    @property
    def is_flower(self):
        return self.category_id and self.category.section == Category.Section.FLOWERS

    @property
    def is_bakery(self):
        return self.category_id and self.category.section == Category.Section.BAKERY

    @property
    def is_gift(self):
        return self.category_id and self.category.section == Category.Section.GIFTS

    @property
    def is_fixed_price(self):
        return self.pricing_type == self.PricingType.FIXED

    @property
    def has_price(self):
        return self.is_fixed_price and self.price is not None

    @property
    def display_price(self):
        if not self.has_price:
            return "استعلام قیمت"

        price_parts = [f"{int(self.price):,} تومان"]

        if self.price_usd:
            price_parts.append(f"{int(self.price_usd):,} USD")

        return " · ".join(price_parts)

    @property
    def display_price_en(self):
        if not self.has_price:
            return "Call for Price"

        price_parts = [f"{int(self.price):,} IRT"]

        if self.price_usd:
            price_parts.append(f"{int(self.price_usd):,} USD")

        return " · ".join(price_parts)

    @property
    def order_contact_text(self):
        if self.has_price:
            return "برای ثبت سفارش با ما در ارتباط باشید"

        return "برای استعلام قیمت و ثبت سفارش با ما در ارتباط باشید"

    @property
    def stock_status_label(self):
        return self.get_stock_status_display()

    @property
    def is_same_day(self):
        if not self.pk:
            return False

        return self.tags.filter(slug=SAME_DAY_TAG_SLUG).exists()

    def _final_product_code(self):
        if not self.pk:
            return ""

        base_code = f"{self.pk:04d}"
        code = base_code
        index = 2

        while Product.objects.exclude(pk=self.pk).filter(product_code=code).exists():
            code = f"{base_code}-{index}"
            index += 1

        return code

    def clean(self):
        super().clean()

        if self.category_id and self.is_active and not self.category.is_active:
            raise ValidationError(
                {
                    "category": "زیردسته غیرفعال است. برای نمایش محصول، ابتدا زیردسته را فعال کنید."
                }
            )

        if self.pricing_type == self.PricingType.FIXED and self.price is None:
            raise ValidationError(
                {"price": "برای قیمت ثابت، وارد کردن قیمت الزامی است."}
            )

    def save(self, *args, **kwargs):
        if self.pricing_type == self.PricingType.INQUIRY:
            self.price = None
            self.price_usd = None

        if self.pk:
            generated_fields = set()
            if not self.product_code:
                self.product_code = self._final_product_code()
                generated_fields.add("product_code")

            if not self.slug:
                self.slug = make_unique_slug(self, self.name or self.product_code)
                generated_fields.add("slug")
            else:
                self.slug = slugify(self.slug, allow_unicode=True)

            if kwargs.get("update_fields") is not None and generated_fields:
                kwargs["update_fields"] = set(kwargs["update_fields"]) | generated_fields

            super().save(*args, **kwargs)
            return

        if not self.product_code:
            self.product_code = f"pending-{uuid.uuid4().hex[:12]}"

        super().save(*args, **kwargs)

        update_fields = []

        if self.product_code.startswith("pending-"):
            self.product_code = self._final_product_code()
            update_fields.append("product_code")

        if not self.slug:
            self.slug = make_unique_slug(self, self.name or self.product_code)
            update_fields.append("slug")

        if update_fields:
            super().save(update_fields=update_fields)

    def get_absolute_url(self):
        route_name = {
            Category.Section.FLOWERS: "flower_product_detail",
            Category.Section.BAKERY: "bakery_product_detail",
            Category.Section.GIFTS: "gift_product_detail",
        }.get(self.section, "product_detail")

        if route_name == "product_detail":
            return reverse(route_name, args=[self.pk, self.slug])

        return reverse(route_name, args=[self.category.slug, self.slug])


class FlowerManager(models.Manager.from_queryset(ProductQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(
            category__section=Category.Section.FLOWERS,
        )


class BakeryItemManager(models.Manager.from_queryset(ProductQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(
            category__section=Category.Section.BAKERY,
        )


class GiftItemManager(models.Manager.from_queryset(ProductQuerySet)):
    def get_queryset(self):
        return super().get_queryset().filter(
            category__section=Category.Section.GIFTS,
        )


class SameDayFlowerManager(FlowerManager):
    def get_queryset(self):
        return super().get_queryset().same_day()


class Flower(Product):
    objects = FlowerManager()

    class Meta:
        proxy = True
        ordering = ["sort_order", "-created_at"]
        verbose_name = "محصول گل"
        verbose_name_plural = "محصولات گل"


class SameDayFlower(Product):
    """Admin-only proxy for the fast same-day selection workflow."""

    objects = SameDayFlowerManager()

    class Meta:
        proxy = True
        ordering = ["sort_order", "-updated_at"]
        verbose_name = "گل ارسال روز"
        verbose_name_plural = "مدیریت ارسال روز"


class BakeryItem(Product):
    objects = BakeryItemManager()

    class Meta:
        proxy = True
        ordering = ["sort_order", "-created_at"]
        verbose_name = "محصول بیکری"
        verbose_name_plural = "محصولات بیکری"


class GiftItem(Product):
    objects = GiftItemManager()

    class Meta:
        proxy = True
        ordering = ["sort_order", "-created_at"]
        verbose_name = "هدیه"
        verbose_name_plural = "هدایا"


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(
        Product,
        verbose_name="محصول",
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )

    image = models.ImageField("تصویر", upload_to=product_gallery_upload_to)
    alt_text = models.CharField("متن جایگزین", max_length=150, blank=True)
    ordering = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["ordering", "id"]
        verbose_name = "تصویر محصول"
        verbose_name_plural = "تصاویر محصول"
        indexes = [
            models.Index(fields=["product", "ordering"]),
        ]

    def __str__(self) -> str:
        return f"{self.product.display_name} - image {self.ordering}"

    @cached_property
    def image_srcset(self):
        return responsive_image_srcset(self.image)


class PublishStatus(models.TextChoices):
    DRAFT = "draft", "پیش‌نویس"
    PUBLISHED = "published", "منتشرشده"


class NewsPost(TimeStampedModel):
    title = models.CharField("عنوان", max_length=180)
    slug = models.SlugField("اسلاگ", max_length=200, unique=True, blank=True, allow_unicode=True)
    excerpt = models.CharField("خلاصه", max_length=300, blank=True)
    body = models.TextField("متن")
    cover_image = models.ImageField("تصویر کاور", upload_to=news_cover_upload_to, null=True, blank=True)
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)

    class Meta:
        ordering = ["-published_at", "-created_at"]
        verbose_name = "خبر"
        verbose_name_plural = "اخبار"

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_unique_slug(self, self.title)
        else:
            self.slug = slugify(self.slug, allow_unicode=True)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("blog_detail", args=[self.slug])


class Event(TimeStampedModel):
    title = models.CharField("عنوان", max_length=180)
    slug = models.SlugField("اسلاگ", max_length=200, unique=True, blank=True, allow_unicode=True)
    description = models.TextField("توضیحات")
    start_at = models.DateTimeField("شروع")
    end_at = models.DateTimeField("پایان")
    location = models.CharField("مکان", max_length=200)
    cover_image = models.ImageField("تصویر کاور", upload_to=event_cover_upload_to, null=True, blank=True)
    status = models.CharField(
        "وضعیت",
        max_length=20,
        choices=PublishStatus.choices,
        default=PublishStatus.DRAFT,
        db_index=True,
    )
    published_at = models.DateTimeField("تاریخ انتشار", null=True, blank=True)

    class Meta:
        ordering = ["start_at", "-created_at"]
        verbose_name = "رویداد"
        verbose_name_plural = "رویدادها"
        constraints = [
            models.CheckConstraint(
                condition=Q(end_at__gt=F("start_at")),
                name="event_end_after_start",
            ),
        ]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = make_unique_slug(self, self.title)
        else:
            self.slug = slugify(self.slug, allow_unicode=True)

        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("event_detail", args=[self.slug])

    def clean(self):
        super().clean()

        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError(
                {"end_at": "زمان پایان باید بعد از زمان شروع باشد."}
            )


class LeadRequest(TimeStampedModel):
    class LeadType(models.TextChoices):
        FLOWER = "flower", "گل"
        BAKERY = "bakery", "بیکری"
        GIFT = "gift", "هدیه"
        EVENT = "event", "رویداد"

    class DeliveryWindow(models.TextChoices):
        TODAY = "today", "امروز"
        TOMORROW = "tomorrow", "فردا"
        PICK_DATE = "pick_date", "تاریخ انتخابی"

    full_name = models.CharField("نام", max_length=120)
    mobile = models.CharField("شماره موبایل", max_length=20)

    lead_type = models.CharField(
        "نوع درخواست",
        max_length=20,
        choices=LeadType.choices,
    )

    product = models.ForeignKey(
        Product,
        verbose_name="محصول",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="lead_requests",
    )

    delivery_window = models.CharField(
        "بازه تحویل",
        max_length=20,
        choices=DeliveryWindow.choices,
    )

    preferred_date = models.DateField("تاریخ انتخابی", null=True, blank=True)
    event_location = models.CharField("مکان رویداد", max_length=180, blank=True)
    note = models.TextField("یادداشت", blank=True)
    source_page = models.CharField("صفحه مبدا", max_length=255, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "درخواست مشاوره"
        verbose_name_plural = "درخواست‌های مشاوره"

    def __str__(self) -> str:
        base = f"{self.full_name} - {self.get_lead_type_display()}"
        if self.product:
            return f"{base} - {self.product.display_name}"
        return base


class HeroFont(TimeStampedModel):
    name = models.CharField(
        "نام نمایشی فونت",
        max_length=100,
        unique=True,
        help_text="یک نام واضح بنویس؛ مثلاً «فونت فارسی کمپین نوروز».",
    )
    font_file = models.FileField(
        "فایل فونت",
        upload_to=hero_font_upload_to,
        validators=[
            FileExtensionValidator(["woff2", "woff", "ttf", "otf"]),
            validate_hero_font_file_size,
        ],
        help_text=(
            "فرمت WOFF2 پیشنهاد می‌شود. فرمت‌های WOFF، TTF و OTF هم پذیرفته "
            "می‌شوند. حداکثر حجم فایل ۵ مگابایت است."
        ),
    )
    is_active = models.BooleanField(
        "قابل انتخاب باشد؟",
        default=True,
        help_text=(
            "اگر خاموش شود، Heroهایی که این فونت را انتخاب کرده‌اند بدون خطا "
            "با فونت پیش‌فرض نمایش داده می‌شوند."
        ),
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "فونت Hero"
        verbose_name_plural = "فونت‌های Hero"

    def __str__(self):
        return self.name if self.is_active else f"{self.name} (غیرفعال)"

    @property
    def css_family_name(self):
        return f"ZADHeroFont-{self.pk}" if self.pk else "ZADHeroFont"


class HomeHeroSlide(TimeStampedModel):
    title = models.CharField("عنوان", max_length=180)
    kicker = models.CharField("متن کوتاه بالا", max_length=100, blank=True)
    description = models.TextField("توضیح", blank=True)

    image = models.ImageField("تصویر اصلی", upload_to=home_hero_upload_to)
    mobile_image = models.ImageField(
        "تصویر موبایل",
        upload_to=home_hero_mobile_upload_to,
        blank=True,
        null=True,
    )

    primary_button_text = models.CharField("متن دکمه اصلی", max_length=60, blank=True)
    primary_button_url = models.CharField("لینک دکمه اصلی", max_length=255, blank=True)

    secondary_button_text = models.CharField("متن دکمه دوم", max_length=60, blank=True)
    secondary_button_url = models.CharField("لینک دکمه دوم", max_length=255, blank=True)

    content_position = models.CharField(
        "موقعیت متن در دسکتاپ",
        max_length=20,
        choices=HERO_POSITION_CHOICES,
        default="bottom-right",
        help_text="جای تقریبی کل بلوک متن روی تصویر دسکتاپ را مشخص می‌کند.",
    )
    mobile_content_position = models.CharField(
        "موقعیت متن در موبایل",
        max_length=20,
        choices=HERO_POSITION_CHOICES,
        default="bottom-center",
        help_text="موقعیت مستقل متن روی تصویر موبایل؛ برای جلوگیری از پوشاندن سوژه.",
    )
    text_color = models.CharField(
        "رنگ متن",
        max_length=7,
        default="#FFFFFF",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="رنگ شش‌رقمی؛ مثل #FFFFFF برای سفید یا #2D2A27 برای قهوه‌ای تیره.",
    )
    builtin_font = models.CharField(
        "فونت داخلی",
        max_length=20,
        choices=HERO_BUILTIN_FONT_CHOICES,
        default="estedad",
        help_text="اگر فونت آپلودی انتخاب نشود یا در دسترس نباشد، این فونت استفاده می‌شود.",
    )
    custom_font = models.ForeignKey(
        HeroFont,
        verbose_name="فونت آپلودی",
        on_delete=models.SET_NULL,
        related_name="home_hero_slides",
        null=True,
        blank=True,
        help_text="اختیاری است. در صورت انتخاب، بر فونت داخلی اولویت دارد.",
    )
    title_font_size = models.PositiveSmallIntegerField(
        "اندازه عنوان در دسکتاپ",
        default=64,
        validators=[MinValueValidator(28), MaxValueValidator(120)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۲۸ تا ۱۲۰.",
    )
    body_font_size = models.PositiveSmallIntegerField(
        "اندازه توضیح در دسکتاپ",
        default=18,
        validators=[MinValueValidator(12), MaxValueValidator(32)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۳۲.",
    )
    mobile_title_font_size = models.PositiveSmallIntegerField(
        "اندازه عنوان در موبایل",
        default=40,
        validators=[MinValueValidator(22), MaxValueValidator(72)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۲۲ تا ۷۲.",
    )
    mobile_body_font_size = models.PositiveSmallIntegerField(
        "اندازه توضیح در موبایل",
        default=14,
        validators=[MinValueValidator(12), MaxValueValidator(24)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۲۴.",
    )

    is_active = models.BooleanField("فعال باشد؟", default=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "اسلاید هیروی خانه"
        verbose_name_plural = "اسلایدهای هیروی خانه"

    def __str__(self) -> str:
        return self.title


class SiteHero(TimeStampedModel):
    class TargetPage(models.TextChoices):
        FLOWERS = "flowers", "گل‌ها"
        BAKERY = "bakery", "بیکری"
        GIFTS = "gifts", "هدایا"
        EVENTS = "events", "رویدادها"
        OCCASIONS = "occasions", "مناسبت‌ها"
        CONTACT = "contact", "تماس با ما"
        FAQ = "faq", "سوالات پرتکرار"
        BLOG = "blog", "بلاگ"
        ABOUT = "about", "درباره زاد"
        MASHHAD = "mashhad", "سفارش در مشهد"
        SUBCATEGORY = "subcategory", "زیر‌دسته"
        ITEM = "item", "صفحه محصول"

    title = models.CharField("عنوان", max_length=180)
    kicker = models.CharField("متن کوتاه بالا", max_length=100, blank=True)
    description = models.TextField("توضیح", blank=True)

    image = models.ImageField("تصویر اصلی", upload_to=site_hero_upload_to)
    mobile_image = models.ImageField(
        "تصویر موبایل",
        upload_to=site_hero_mobile_upload_to,
        blank=True,
        null=True,
    )

    target_page = models.CharField(
        "صفحه هدف",
        max_length=30,
        choices=TargetPage.choices,
    )

    target_slug = models.CharField(
        "اسلاگ هدف",
        max_length=120,
        blank=True,
        help_text="برای زیر‌دسته یا صفحه خاص، اسلاگ را وارد کن. مثال: bouquet",
    )

    content_position = models.CharField(
        "موقعیت متن در دسکتاپ",
        max_length=20,
        choices=HERO_POSITION_CHOICES,
        default="center-left",
        help_text="جای تقریبی کل بلوک متن روی تصویر دسکتاپ را مشخص می‌کند.",
    )
    mobile_content_position = models.CharField(
        "موقعیت متن در موبایل",
        max_length=20,
        choices=HERO_POSITION_CHOICES,
        default="bottom-center",
        help_text="موقعیت مستقل متن روی تصویر موبایل؛ برای جلوگیری از پوشاندن سوژه.",
    )
    text_color = models.CharField(
        "رنگ متن",
        max_length=7,
        default="#FFFFFF",
        validators=[HEX_COLOR_VALIDATOR],
        help_text="رنگ شش‌رقمی؛ مثل #FFFFFF برای سفید یا #2D2A27 برای قهوه‌ای تیره.",
    )
    builtin_font = models.CharField(
        "فونت داخلی",
        max_length=20,
        choices=HERO_BUILTIN_FONT_CHOICES,
        default="estedad",
        help_text="اگر فونت آپلودی انتخاب نشود یا در دسترس نباشد، این فونت استفاده می‌شود.",
    )
    custom_font = models.ForeignKey(
        HeroFont,
        verbose_name="فونت آپلودی",
        on_delete=models.SET_NULL,
        related_name="site_heroes",
        null=True,
        blank=True,
        help_text="اختیاری است. در صورت انتخاب، بر فونت داخلی اولویت دارد.",
    )
    title_font_size = models.PositiveSmallIntegerField(
        "اندازه عنوان در دسکتاپ",
        default=68,
        validators=[MinValueValidator(28), MaxValueValidator(120)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۲۸ تا ۱۲۰.",
    )
    body_font_size = models.PositiveSmallIntegerField(
        "اندازه توضیح در دسکتاپ",
        default=18,
        validators=[MinValueValidator(12), MaxValueValidator(32)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۳۲.",
    )
    mobile_title_font_size = models.PositiveSmallIntegerField(
        "اندازه عنوان در موبایل",
        default=40,
        validators=[MinValueValidator(22), MaxValueValidator(72)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۲۲ تا ۷۲.",
    )
    mobile_body_font_size = models.PositiveSmallIntegerField(
        "اندازه توضیح در موبایل",
        default=14,
        validators=[MinValueValidator(12), MaxValueValidator(24)],
        help_text="بر حسب پیکسل؛ بازه مجاز ۱۲ تا ۲۴.",
    )

    is_active = models.BooleanField("فعال باشد؟", default=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["target_page", "sort_order", "id"]
        verbose_name = "هیروی صفحه"
        verbose_name_plural = "هیروهای صفحات"
        constraints = [
            models.UniqueConstraint(
                fields=["target_page", "target_slug", "sort_order"],
                name="uniq_sitehero_target_slug_sort",
            ),
        ]

    def __str__(self) -> str:
        if self.target_slug:
            return f"{self.get_target_page_display()} - {self.target_slug}"
        return self.get_target_page_display()


class WorkshopPageContent(TimeStampedModel):
    story_kicker = models.CharField("عنوان کوتاه بخش فلسفه", max_length=120, blank=True)
    story_title = models.CharField("عنوان بخش فلسفه", max_length=220, blank=True)
    story_text = models.TextField("متن بخش فلسفه", blank=True)
    types_kicker = models.CharField("عنوان کوتاه انواع ورکشاپ", max_length=120, blank=True)
    types_title = models.CharField("عنوان انواع ورکشاپ", max_length=220, blank=True)
    public_title = models.CharField("عنوان ورکشاپ عمومی", max_length=160, blank=True)
    public_text = models.TextField("متن ورکشاپ عمومی", blank=True)
    private_title = models.CharField("عنوان ورکشاپ خصوصی", max_length=160, blank=True)
    private_text = models.TextField("متن ورکشاپ خصوصی", blank=True)
    corporate_title = models.CharField("عنوان ورکشاپ سازمانی", max_length=160, blank=True)
    corporate_text = models.TextField("متن ورکشاپ سازمانی", blank=True)
    upcoming_kicker = models.CharField("عنوان کوتاه برنامه‌های آینده", max_length=120, blank=True)
    upcoming_title = models.CharField("عنوان برنامه‌های آینده", max_length=220, blank=True)
    upcoming_empty_title = models.CharField("عنوان حالت بدون برنامه", max_length=220, blank=True)
    upcoming_empty_text = models.TextField("متن حالت بدون برنامه", blank=True)
    cta_title = models.CharField("عنوان بخش درخواست", max_length=220, blank=True)
    cta_text = models.TextField("متن بخش درخواست", blank=True)
    is_active = models.BooleanField("فعال باشد؟", default=True)

    class Meta:
        verbose_name = "متن صفحه ورکشاپ"
        verbose_name_plural = "متن صفحه ورکشاپ"

    def __str__(self) -> str:
        return "متن صفحه ورکشاپ"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        if self.is_active:
            type(self).objects.exclude(pk=self.pk).filter(is_active=True).update(
                is_active=False
            )

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).order_by("-updated_at", "-id").first()


class PageContentBlock(TimeStampedModel):
    class Page(models.TextChoices):
        HOME = "home", "خانه"
        FLOWERS = "flowers", "گل‌ها"
        BAKERY = "bakery", "بیکری"
        GIFTS = "gifts", "هدایا"
        OCCASIONS = "occasions", "مناسبت‌ها"
        WORKSHOPS = "workshops", "ورکشاپ‌ها"
        ABOUT = "about", "درباره زاد"
        CONTACT = "contact", "تماس با ما"
        FAQ = "faq", "سوالات پرتکرار"
        BLOG = "blog", "بلاگ"
        MASHHAD = "mashhad", "صفحات مشهد"
        PRODUCT = "product", "صفحه محصول"
        SUBCATEGORY = "subcategory", "صفحه زیردسته"
        OCCASION_DETAIL = "occasion-detail", "جزئیات مناسبت"
        EVENT_DETAIL = "event-detail", "جزئیات ورکشاپ"
        BLOG_DETAIL = "blog-detail", "جزئیات بلاگ"

    page = models.CharField("صفحه", max_length=40, choices=Page.choices, db_index=True)
    section_key = models.SlugField(
        "کلید بخش",
        max_length=80,
        allow_unicode=False,
        help_text="یک کلید انگلیسی پایدار؛ مثل intro، story، cta یا empty.",
    )
    kicker = models.CharField("عنوان کوتاه", max_length=140, blank=True)
    title = models.CharField("عنوان", max_length=240, blank=True)
    body = models.TextField("متن", blank=True)
    cta_text = models.CharField("متن دکمه", max_length=100, blank=True)
    cta_url = models.CharField(
        "لینک دکمه",
        max_length=300,
        blank=True,
        help_text="مسیر داخلی مثل /contact/#lead-form یا آدرس کامل https://...",
    )
    is_active = models.BooleanField("فعال باشد؟", default=True, db_index=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["page", "sort_order", "section_key"]
        verbose_name = "متن قابل ویرایش صفحه"
        verbose_name_plural = "متن‌های قابل ویرایش صفحات"
        constraints = [
            models.UniqueConstraint(
                fields=["page", "section_key"],
                name="uniq_page_content_block",
            )
        ]
        indexes = [
            models.Index(
                fields=["page", "is_active", "sort_order"],
                name="page_content_lookup_idx",
            ),
        ]

    def __str__(self):
        return f"{self.get_page_display()} / {self.section_key}"
