"""Models for the independent Wedding catalog and managed page content."""

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError
from django.core.validators import URLValidator
from django.db import models, transaction
from django.db.models import Q

from .legacy import Product, TimeStampedModel, _upload_extension, _upload_slug


def wedding_hero_upload_to(instance, filename):
    return f"weddings/hero/wedding-hero.{_upload_extension(filename)}"


def wedding_hero_mobile_upload_to(instance, filename):
    return f"weddings/hero/wedding-hero-mobile.{_upload_extension(filename)}"


def wedding_open_graph_upload_to(instance, filename):
    return f"weddings/seo/wedding-open-graph.{_upload_extension(filename)}"


def wedding_gallery_upload_to(instance, filename):
    order = instance.sort_order or instance.pk or "new"
    return f"weddings/gallery/wedding-gallery-{order}.{_upload_extension(filename)}"


def wedding_proposal_bouquet_card_upload_to(instance, filename):
    return f"weddings/cards/proposal-bouquet-card.{_upload_extension(filename)}"


def wedding_proposal_sweets_card_upload_to(instance, filename):
    return f"weddings/cards/proposal-sweets-card.{_upload_extension(filename)}"


def wedding_bridal_bouquet_card_upload_to(instance, filename):
    return f"weddings/cards/bridal-bouquet-card.{_upload_extension(filename)}"


def wedding_car_card_upload_to(instance, filename):
    return f"weddings/cards/wedding-car-card.{_upload_extension(filename)}"


def wedding_collection_hero_upload_to(instance, filename):
    collection = _upload_slug(instance.collection_key, "collection")
    return f"weddings/collections/{collection}/hero.{_upload_extension(filename)}"


def wedding_collection_hero_mobile_upload_to(instance, filename):
    collection = _upload_slug(instance.collection_key, "collection")
    return f"weddings/collections/{collection}/hero-mobile.{_upload_extension(filename)}"


class WeddingPageContent(TimeStampedModel):
    hero_image = models.ImageField(
        "Hero دسکتاپ",
        upload_to=wedding_hero_upload_to,
        blank=True,
        null=True,
    )
    hero_mobile_image = models.ImageField(
        "Hero موبایل",
        upload_to=wedding_hero_mobile_upload_to,
        blank=True,
        null=True,
    )
    hero_title = models.CharField(
        "عنوان Hero",
        max_length=220,
        blank=True,
        default="",
        help_text="اختیاری است؛ برای بنر تصویری بدون متن خالی بگذارید.",
    )
    hero_text = models.TextField(
        "متن Hero",
        blank=True,
        default="",
        help_text="اختیاری است؛ برای بنر تصویری بدون متن خالی بگذارید.",
    )
    proposal_title = models.CharField(
        "عنوان نوار خواستگاری و بله‌برون",
        max_length=220,
        default="خواستگاری و بله‌برون",
        help_text="عنوان نوار جداکننده بین Hero و دو کارت خواستگاری است.",
    )
    proposal_text = models.TextField(
        "توضیح بخش خواستگاری و بله‌برون",
        blank=True,
        default="",
        help_text="اختیاری است و در طراحی فعلی صفحه نمایش داده نمی‌شود.",
    )
    proposal_bouquet_card_image = models.ImageField(
        "تصویر کارت دسته‌گل خواستگاری",
        upload_to=wedding_proposal_bouquet_card_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
    )
    proposal_sweets_card_image = models.ImageField(
        "تصویر کارت شیرینی خواستگاری",
        upload_to=wedding_proposal_sweets_card_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
    )
    transition_title = models.CharField(
        "عنوان گذار روایی",
        max_length=220,
        default="از یک بله شیرین تا روزی که همیشه می‌ماند",
    )
    transition_text = models.TextField(
        "متن گذار روایی",
        default="پس از انتخاب‌های آغاز این مسیر، برای جزئیات روز عروسی هم با همان دقت کنار شما هستیم.",
    )
    wedding_day_title = models.CharField(
        "عنوان بخش روز عروسی",
        max_length=220,
        default="روز عروسی",
    )
    wedding_day_text = models.TextField(
        "توضیح بخش روز عروسی",
        default="دسته‌گل عروس و گل‌آرایی ماشین عروس با هماهنگی رنگ، سبک و زمان تحویل.",
    )
    bridal_bouquet_card_image = models.ImageField(
        "تصویر کارت دسته‌گل عروس",
        upload_to=wedding_bridal_bouquet_card_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
    )
    bridal_bouquet_card_kicker = models.CharField(
        "عنوان انگلیسی کارت دسته‌گل عروس",
        max_length=100,
        blank=True,
        default="BRIDAL BOUQUETS",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    bridal_bouquet_card_title = models.CharField(
        "عنوان فارسی کارت دسته‌گل عروس",
        max_length=180,
        blank=True,
        default="دسته‌گل عروس",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    bridal_bouquet_card_text = models.TextField(
        "توضیح کارت دسته‌گل عروس",
        blank=True,
        default="طراحی دسته‌گل عروس متناسب با استایل، فصل و پالت رنگ روز عروسی.",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    wedding_car_card_image = models.ImageField(
        "تصویر کارت ماشین عروس",
        upload_to=wedding_car_card_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر محصول یا تصویر پیش‌فرض نمایش داده می‌شود.",
    )
    wedding_car_card_kicker = models.CharField(
        "عنوان انگلیسی کارت ماشین عروس",
        max_length=100,
        blank=True,
        default="WEDDING CARS",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    wedding_car_card_title = models.CharField(
        "عنوان فارسی کارت ماشین عروس",
        max_length=180,
        blank=True,
        default="ماشین عروس",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    wedding_car_card_text = models.TextField(
        "توضیح کارت ماشین عروس",
        blank=True,
        default="گل‌آرایی اختصاصی خودرو با توجه به مدل ماشین، فصل و سبک مراسم.",
        help_text="اختیاری؛ برای کارت کاملاً تصویری خالی بگذارید.",
    )
    gallery_title = models.CharField(
        "عنوان گالری",
        max_length=180,
        default="روایت‌های عروسی زاد",
    )
    steps_title = models.CharField(
        "عنوان مراحل سفارش",
        max_length=180,
        default="مسیر انتخاب و ثبت سفارش",
    )
    steps_text = models.TextField(
        "متن مراحل سفارش",
        default=(
            "انتخاب نوع محصول و ثبت گزینه‌های مورد علاقه\n"
            "هماهنگی رنگ، بودجه و زمان تحویل با تیم زاد\n"
            "تأیید نهایی جزئیات و ثبت سفارش"
        ),
        help_text="هر مرحله را در یک خط جداگانه وارد کنید.",
    )
    cta_title = models.CharField(
        "عنوان CTA نهایی",
        max_length=220,
        default="برای هماهنگی اختصاصی با زاد در تماس باشید",
    )
    cta_text = models.TextField(
        "متن CTA نهایی",
        default="برای بررسی موجودی، زمان آماده‌سازی و جزئیات انتخاب‌ها ابتدا تماس بگیرید یا در تلگرام پیام بدهید.",
    )
    contact_url = models.CharField(
        "لینک تماس",
        max_length=300,
        blank=True,
        help_text="اختیاری؛ مسیر داخلی، لینک tel: یا آدرس کامل. در حالت خالی شماره تماس سایت استفاده می‌شود.",
    )
    telegram_url = models.URLField(
        "لینک Telegram",
        max_length=300,
        blank=True,
        help_text="در حالت خالی لینک تلگرام اصلی سایت استفاده می‌شود.",
    )
    seo_title = models.CharField(
        "SEO Title",
        max_length=180,
        blank=True,
    )
    meta_description = models.CharField(
        "Meta Description",
        max_length=320,
        blank=True,
    )
    open_graph_image = models.ImageField(
        "تصویر Open Graph",
        upload_to=wedding_open_graph_upload_to,
        blank=True,
        null=True,
    )
    is_active = models.BooleanField("فعال باشد؟", default=True, db_index=True)

    class Meta:
        verbose_name = "تنظیمات صفحه عروسی"
        verbose_name_plural = "تنظیمات صفحه عروسی"
        constraints = [
            models.UniqueConstraint(
                fields=["is_active"],
                condition=Q(is_active=True),
                name="single_active_wedding_page_content",
            )
        ]

    def __str__(self):
        return "تنظیمات صفحه عروسی"

    def clean(self):
        super().clean()
        errors = {}
        contact_url = (self.contact_url or "").strip()
        telegram_url = (self.telegram_url or "").strip()

        if contact_url:
            parsed = urlsplit(contact_url)
            is_internal = (
                contact_url.startswith("/") and not contact_url.startswith("//")
            )
            is_phone = parsed.scheme == "tel" and bool(parsed.path.strip())
            is_web = parsed.scheme in {"http", "https"} and bool(parsed.netloc)
            if not (is_internal or is_phone or is_web):
                errors["contact_url"] = (
                    "لینک تماس باید مسیر داخلی، tel: یا نشانی کامل http/https باشد."
                )

        if telegram_url:
            try:
                URLValidator(schemes=("http", "https"))(telegram_url)
            except ValidationError:
                errors["telegram_url"] = "لینک تلگرام باید نشانی معتبر http/https باشد."

        if errors:
            raise ValidationError(errors)

        self.contact_url = contact_url
        self.telegram_url = telegram_url

    def save(self, *args, **kwargs):
        self.clean()
        with transaction.atomic():
            if self.is_active:
                type(self).objects.exclude(pk=self.pk).filter(is_active=True).update(
                    is_active=False
                )
            super().save(*args, **kwargs)

    @classmethod
    def current(cls):
        return cls.objects.filter(is_active=True).order_by("-updated_at", "-id").first()

    @property
    def steps(self):
        return [line.strip() for line in self.steps_text.splitlines() if line.strip()]


class WeddingCollectionContent(TimeStampedModel):
    class CollectionKey(models.TextChoices):
        PROPOSAL_BOUQUETS = "proposal-bouquets", "دسته‌گل خواستگاری و بله‌برون"
        PROPOSAL_SWEETS = "proposal-sweets", "شیرینی خواستگاری و بله‌برون"
        BRIDAL_BOUQUETS = "bridal-bouquets", "دسته‌گل عروس"
        WEDDING_CARS = "wedding-cars", "ماشین عروس"

    collection_key = models.CharField(
        "صفحه مجموعه",
        max_length=40,
        choices=CollectionKey.choices,
        unique=True,
    )
    hero_image = models.ImageField(
        "تصویر Hero دسکتاپ",
        upload_to=wedding_collection_hero_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر اولین محصول یا تصویر پیش‌فرض استفاده می‌شود.",
    )
    hero_mobile_image = models.ImageField(
        "تصویر Hero موبایل",
        upload_to=wedding_collection_hero_mobile_upload_to,
        blank=True,
        null=True,
        help_text="اختیاری؛ اگر خالی باشد تصویر دسکتاپ استفاده می‌شود.",
    )
    hero_kicker = models.CharField(
        "عنوان انگلیسی Hero",
        max_length=100,
        blank=True,
        default="",
        help_text="اختیاری است؛ برای Hero بدون متن خالی بگذارید.",
    )
    hero_title = models.CharField(
        "عنوان فارسی Hero",
        max_length=220,
        blank=True,
        default="",
        help_text="اختیاری است؛ برای Hero فقط‌تصویر خالی بگذارید.",
    )
    hero_text = models.TextField(
        "توضیح Hero",
        blank=True,
        default="",
        help_text="اختیاری است؛ بهتر است کوتاه و حداکثر دو خط باشد.",
    )
    hero_alt_text = models.CharField(
        "متن جایگزین تصویر Hero",
        max_length=180,
        blank=True,
        default="",
        help_text="اختیاری؛ برای دسترس‌پذیری و سئو تصویر.",
    )
    seo_title = models.CharField(
        "SEO Title",
        max_length=180,
        blank=True,
        default="",
    )
    meta_description = models.CharField(
        "Meta Description",
        max_length=320,
        blank=True,
        default="",
    )

    class Meta:
        ordering = ["collection_key"]
        verbose_name = "تنظیمات صفحه مجموعه عروسی"
        verbose_name_plural = "تنظیمات صفحات مجموعه‌های عروسی"

    def __str__(self):
        return self.get_collection_key_display()


class WeddingGalleryImage(TimeStampedModel):
    page = models.ForeignKey(
        WeddingPageContent,
        verbose_name="صفحه عروسی",
        on_delete=models.CASCADE,
        related_name="gallery_images",
    )
    image = models.ImageField("تصویر", upload_to=wedding_gallery_upload_to)
    alt_text = models.CharField("متن جایگزین", max_length=180, blank=True)
    sort_order = models.PositiveIntegerField("ترتیب نمایش", default=0)

    class Meta:
        ordering = ["sort_order", "id"]
        verbose_name = "تصویر گالری عروسی"
        verbose_name_plural = "گالری عروسی"
        indexes = [models.Index(fields=["page", "sort_order"])]

    def __str__(self):
        return self.alt_text or f"تصویر {self.pk or 'جدید'} گالری عروسی"


class WeddingMigrationSnapshot(models.Model):
    """Internal reversible snapshot for the first Wedding data migration."""

    product = models.OneToOneField(
        Product,
        primary_key=True,
        on_delete=models.CASCADE,
        related_name="wedding_migration_snapshot",
    )
    original_category_id = models.PositiveBigIntegerField()
    original_tag_ids = models.JSONField(default=list)
    original_catalog_scope = models.CharField(max_length=16, default="general")
    original_wedding_type = models.CharField(max_length=32, blank=True, default="")
    original_wedding_needs_review = models.BooleanField(default=False)
    original_wedding_sort_order = models.PositiveIntegerField(default=0)
    migration_reason = models.CharField(max_length=80)
    migrated_to_wedding = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تصویر وضعیت مهاجرت عروسی"
        verbose_name_plural = "تصاویر وضعیت مهاجرت عروسی"


class WeddingTaxonomyMigrationSnapshot(models.Model):
    """Internal reversible snapshot for taxonomy touched by the Wedding migration."""

    key = models.CharField(max_length=180, primary_key=True)
    object_kind = models.CharField(max_length=16)
    object_id = models.PositiveBigIntegerField(null=True, blank=True)
    existed_before = models.BooleanField(default=True)
    original_values = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تصویر وضعیت رده‌بندی مهاجرت عروسی"
        verbose_name_plural = "تصاویر وضعیت رده‌بندی مهاجرت عروسی"
