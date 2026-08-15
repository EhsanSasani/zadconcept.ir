from django import forms
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.text import slugify

from .image_pipeline import ImageUploadError, normalize_admin_image
from .models import (
    PROPOSAL_COLLECTION_TAG_SLUG,
    SAME_DAY_TAG_SLUG,
    BakeryItem,
    Category,
    Event,
    Flower,
    GiftItem,
    HeroFont,
    HomeHeroSlide,
    LeadRequest,
    NewsPost,
    PageContentBlock,
    Product,
    ProductImage,
    PublishStatus,
    SameDayFlower,
    SiteHero,
    Tag,
    TelegramBotUser,
    WeddingCollectionContent,
    WeddingGalleryImage,
    WeddingPageContent,
    WeddingProduct,
    WorkshopPageContent,
)

admin.site.site_header = "پنل مدیریت زاد"
admin.site.site_title = "مدیریت زاد"
admin.site.index_title = "مدیریت محتوا، محصولات و درخواست‌ها"

MAX_ADMIN_FONT_SIZE = 5 * 1024 * 1024

ADMIN_IMAGE_ACCEPT = "image/*,.heic,.heif,.heics,.heifs,.hif,.jfif,.jpe"
ADMIN_IMAGE_HELP_TEXT = (
    "JPG/JPEG، PNG، WebP، HEIC/HEIF، AVIF، TIFF، BMP و GIF ثابت "
    "تا ۲۰ مگابایت پذیرفته می‌شوند و هنگام ذخیره به WebP بهینه تبدیل می‌شوند."
)


class PersianImageInput(forms.ClearableFileInput):
    initial_text = "عکس فعلی"
    input_text = "تغییر عکس"
    clear_checkbox_label = "حذف عکس فعلی"

    def __init__(self, attrs=None):
        attrs = dict(attrs or {})
        # ``image/*`` keeps camera/gallery selection available on phones. The
        # explicit suffixes cover browsers that omit HEIC/HEIF from image/*.
        attrs.setdefault("accept", ADMIN_IMAGE_ACCEPT)
        super().__init__(attrs)


class AdminImageUploadField(forms.FileField):
    """Let the content-aware pipeline be the only image validator.

    Django's regular form ImageField rejects by filename extension before a
    ``clean_<field>`` method can inspect the real bytes. Sellers' phone/editor
    uploads can carry unusual or mismatched extensions and MIME values, so the
    admin accepts a file here and validates/normalizes it in one place below.
    The model later receives a verified ``.webp`` file and keeps its own normal
    ImageField validation.
    """

    widget = PersianImageInput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.help_text:
            self.help_text = ADMIN_IMAGE_HELP_TEXT

HERO_SLUG_TARGET_PAGES = {
    SiteHero.TargetPage.EVENTS,
    SiteHero.TargetPage.OCCASIONS,
    SiteHero.TargetPage.BLOG,
    SiteHero.TargetPage.MASHHAD,
    SiteHero.TargetPage.SUBCATEGORY,
    SiteHero.TargetPage.ITEM,
}

HERO_TARGET_SLUG_HELP = {
    SiteHero.TargetPage.EVENTS: "برای یک ورکشاپ خاص، اسلاگ همان ورکشاپ را وارد کن.",
    SiteHero.TargetPage.OCCASIONS: "برای یک مناسبت خاص، مثل birthday یا romantic، اسلاگ را وارد کن.",
    SiteHero.TargetPage.BLOG: "برای یک مطلب خاص، اسلاگ همان مطلب را وارد کن.",
    SiteHero.TargetPage.MASHHAD: "برای صفحات داخلی از flower-order یا flower-delivery استفاده کن.",
    SiteHero.TargetPage.SUBCATEGORY: "برای یک زیردسته خاص، مثل bouquet یا box، اسلاگ را وارد کن.",
    SiteHero.TargetPage.ITEM: "برای یک محصول خاص، اسلاگ همان محصول را وارد کن.",
}


class HiddenFromAdminIndexMixin:
    """Hide a registered model from admin index/sidebar without deleting it."""

    def get_model_perms(self, request):
        return {}


def validate_admin_image(uploaded_file):
    try:
        return normalize_admin_image(uploaded_file)
    except ImageUploadError as error:
        raise forms.ValidationError(str(error), code="invalid_image") from error


def safe_image_url(image):
    try:
        return image.url
    except Exception:
        # A missing object or temporarily unavailable remote storage must not
        # make the Hero list/change page unusable.
        return ""


def to_persian_digits(value):
    value = str(value)
    english_digits = "0123456789"
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    translation_table = str.maketrans(english_digits, persian_digits)
    return value.translate(translation_table)


def to_english_digits(value):
    """Normalize Persian and Arabic-Indic digits for product-code searches."""

    return str(value or "").translate(
        str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    )


def format_toman(value):
    if value in (None, ""):
        return "استعلام قیمت"

    try:
        number = int(value)
    except (TypeError, ValueError):
        return "استعلام قیمت"

    formatted = f"{number:,}".replace(",", "٬")
    return f"{to_persian_digits(formatted)} تومان"


class AdminImagePreviewMixin:
    @admin.display(description="تصویر")
    def image_preview(self, obj):
        image = None

        if obj and hasattr(obj, "cover_image") and obj.cover_image:
            image = obj.cover_image
        elif obj and hasattr(obj, "image") and obj.image:
            image = obj.image

        if not image:
            return format_html(
                '<span style="display:inline-flex;width:44px;height:44px;align-items:center;justify-content:center;border-radius:10px;border:1px dashed #aaa;font-size:10px;color:#999;">{}</span>',
                "بدون عکس",
            )

        image_url = safe_image_url(image)
        if not image_url:
            return "تصویر قابل نمایش نیست"

        return format_html(
            '''
            <img src="{}" class="zad-admin-preview" />
            ''',
            image_url,
        )

    @admin.display(description="نمای بزرگ عکس")
    def large_image_preview(self, obj):
        image = None

        if obj and hasattr(obj, "cover_image") and obj.cover_image:
            image = obj.cover_image
        elif obj and hasattr(obj, "image") and obj.image:
            image = obj.image

        if not image:
            return "بدون عکس"

        image_url = safe_image_url(image)
        if not image_url:
            return "تصویر قابل نمایش نیست"

        return format_html(
            '''
            <a href="{}" target="_blank" class="zad-admin-large-image-link">
                <img src="{}" class="zad-admin-preview" />
            </a>
            ''',
            image_url,
            image_url,
        )

class ActiveActionsMixin:
    actions = ("activate_selected", "deactivate_selected")

    @admin.action(permissions=["change"], description="فعال‌کردن موارد انتخاب‌شده")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} مورد فعال شد.")

    @admin.action(permissions=["change"], description="غیرفعال‌کردن موارد انتخاب‌شده")
    def deactivate_selected(self, request, queryset):
        updated = queryset.update(is_active=False)
        self.message_user(request, f"{updated} مورد غیرفعال شد.")


class ProductActionsMixin(ActiveActionsMixin):
    actions = ActiveActionsMixin.actions + (
        "mark_featured",
        "remove_featured",
        "publish_selected_products",
        "draft_selected_products",
        "mark_in_stock",
        "mark_out_of_stock",
        "make_inquiry_pricing",
    )

    @admin.action(permissions=["change"], description="ویژه‌کردن موارد انتخاب‌شده")
    def mark_featured(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f"{updated} مورد ویژه شد.")

    @admin.action(permissions=["change"], description="حذف از موارد ویژه")
    def remove_featured(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(request, f"{updated} مورد از ویژه‌ها حذف شد.")

    @admin.action(permissions=["change"], description="انتشار موارد انتخاب‌شده")
    def publish_selected_products(self, request, queryset):
        updated = queryset.update(publish_status=Product.PublishStatus.PUBLISHED)
        self.message_user(request, f"{updated} مورد منتشر شد.")

    @admin.action(permissions=["change"], description="بازگردانی به پیش‌نویس")
    def draft_selected_products(self, request, queryset):
        updated = queryset.update(publish_status=Product.PublishStatus.DRAFT)
        self.message_user(request, f"{updated} مورد به پیش‌نویس برگشت.")

    @admin.action(permissions=["change"], description="علامت‌گذاری به عنوان موجود")
    def mark_in_stock(self, request, queryset):
        updated = queryset.update(stock_status=Product.StockStatus.IN_STOCK)
        self.message_user(request, f"{updated} مورد موجود شد.")

    @admin.action(permissions=["change"], description="علامت‌گذاری به عنوان ناموجود")
    def mark_out_of_stock(self, request, queryset):
        updated = queryset.update(stock_status=Product.StockStatus.OUT_OF_STOCK)
        self.message_user(request, f"{updated} مورد ناموجود شد.")

    @admin.action(permissions=["change"], description="قیمت‌گذاری به حالت استعلامی")
    def make_inquiry_pricing(self, request, queryset):
        updated = queryset.update(pricing_type=Product.PricingType.INQUIRY, price=None, price_usd=None)
        self.message_user(request, f"{updated} مورد استعلامی شد.")


class PublishActionsMixin:
    actions = ("publish_selected", "unpublish_selected")

    @admin.action(permissions=["change"], description="انتشار موارد انتخاب‌شده")
    def publish_selected(self, request, queryset):
        updated = queryset.update(
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.message_user(request, f"{updated} مورد منتشر شد.")

    @admin.action(permissions=["change"], description="بازگردانی به پیش‌نویس")
    def unpublish_selected(self, request, queryset):
        updated = queryset.update(
            status=PublishStatus.DRAFT,
            published_at=None,
        )
        self.message_user(request, f"{updated} مورد به پیش‌نویس برگشت.")


class CategoryAdminForm(forms.ModelForm):
    class Meta:
        model = Category
        fields = "__all__"
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "یک توضیح کوتاه برای این زیر‌دسته بنویس.",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "parent" in self.fields:
            section = self.data.get("section") or getattr(self.instance, "section", "")
            queryset = Category.objects.for_general_catalog().filter(
                parent__isnull=True
            )
            if section:
                queryset = queryset.filter(section=section)
            if self.instance and self.instance.pk:
                queryset = queryset.exclude(pk=self.instance.pk)
            self.fields["parent"].queryset = queryset.order_by(
                "section", "sort_order", "name"
            )

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))

    def clean(self):
        cleaned_data = super().clean()
        section = cleaned_data.get("section") or ""
        slug = slugify(cleaned_data.get("slug") or "", allow_unicode=True)
        parent = cleaned_data.get("parent")
        candidate = Category(section=section, slug=slug, parent=parent)
        if candidate.is_wedding_category:
            raise forms.ValidationError(
                "دسته‌های سیستمی عروسی فقط از بخش مستقل عروسی مدیریت می‌شوند."
            )
        return cleaned_data


class TagAdminForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = "__all__"
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "توضیح کوتاه برای کارت مناسبتی یا کاربرد این برچسب.",
                }
            ),
        }

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))

    def clean(self):
        cleaned_data = super().clean()
        slug = (cleaned_data.get("slug") or "").strip().casefold()
        name = (cleaned_data.get("name") or "").strip()

        if Tag(slug=slug).is_wedding_legacy:
            raise forms.ValidationError(
                "برچسب‌های قدیمی عروسی، خواستگاری و بله‌برون محافظت شده‌اند."
            )

        if (slug == "wedding" or name == "عروسی") and cleaned_data.get(
            "is_occasion"
        ):
            self.add_error(
                "is_occasion",
                (
                    "عروسی، خواستگاری و بله‌برون در بخش مستقل عروسی مدیریت "
                    "می‌شوند و نباید به‌عنوان مناسبت عمومی ساخته شوند."
                ),
            )

        return cleaned_data


class ProductAdminForm(forms.ModelForm):
    class Meta:
        fields = "__all__"
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
                "cover_image": PersianImageInput,
                "tags": forms.CheckboxSelectMultiple,
                "description": forms.Textarea(
                    attrs={
                        "rows": 4,
                        "placeholder": "توضیح کوتاه و احساسی بنویس؛ اگر خالی بماند مشکلی نیست.",
                    }
                ),
            }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if "category" in self.fields:
            section_filter = getattr(self, "section_filter", None)

            category_queryset = Category.objects.for_general_catalog().filter(
                is_active=True
            )

            if section_filter:
                category_queryset = category_queryset.filter(section=section_filter)

            self.fields["category"].queryset = category_queryset.order_by(
                "section",
                "sort_order",
                "name",
            )
            self.fields["category"].help_text = (
                "دسته دقیق محصول را انتخاب کن. اگر محصول هنوز زیردسته مشخصی "
                "ندارد، می‌تواند مستقیم داخل دسته والد بماند."
            )

        if "tags" in self.fields:
            self.fields["tags"].queryset = (
                Tag.objects.for_general_catalog()
                .filter(is_active=True)
                .order_by("sort_order", "name")
            )

        if "price" in self.fields:
            self.fields["price"].help_text = "فقط عدد وارد کن؛ مثلاً 2500000."

        if "price_usd" in self.fields:
            self.fields["price_usd"].help_text = "اختیاری است؛ اگر قیمت دلاری نداری خالی بگذار."

        if "sort_order" in self.fields:
            self.fields["sort_order"].help_text = "عدد کمتر یعنی محصول بالاتر نمایش داده می‌شود."

        if "cover_image" in self.fields:
            self.fields["cover_image"].help_text = (
                "تصویر اصلی محصول است. JPG/JPEG، PNG، WebP، HEIC/HEIF، AVIF، "
                "TIFF، BMP و GIF ثابت تا ۲۰ مگابایت، هنگام ذخیره با حفظ "
                "کیفیت به WebP بهینه تبدیل می‌شوند."
            )

        if "featured" in self.fields:
            self.fields["featured"].help_text = "محصول ویژه در بخش‌های انتخاب‌شده و ترتیب نمایش بالاتر اولویت می‌گیرد؛ محصولات غیر ویژه را مخفی نمی‌کند."

        if "tags" in self.fields:
            self.fields["tags"].help_text = (
                "برچسب می‌تواند داخلی باشد یا اگر گزینه مناسبت روشن است، "
                "در بخش مناسبت‌های سایت نمایش داده شود. برچسب ارسال روز "
                "برای فیلتر ارسال فوری است؛ عروسی از بخش مستقل مدیریت می‌شود."
            )

    def clean(self):
        cleaned_data = super().clean()

        pricing_type = cleaned_data.get("pricing_type")
        price = cleaned_data.get("price")
        price_usd = cleaned_data.get("price_usd")

        if pricing_type == Product.PricingType.INQUIRY:
            cleaned_data["price"] = None
            cleaned_data["price_usd"] = None

        if price is not None and price < 0:
            self.add_error("price", "قیمت نمی‌تواند منفی باشد.")

        if price_usd is not None and price_usd < 0:
            self.add_error("price_usd", "قیمت دلاری نمی‌تواند منفی باشد.")

        return cleaned_data

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))

    def _save_m2m(self):
        protected_tag_ids = ()
        if self.instance.pk:
            protected_tag_ids = tuple(
                self.instance.tags.filter(
                    slug=PROPOSAL_COLLECTION_TAG_SLUG,
                    is_active=False,
                ).values_list("pk", flat=True)
            )

        super()._save_m2m()

        if protected_tag_ids:
            self.instance.tags.add(*protected_tag_ids)


class WeddingProductAdminForm(ProductAdminForm):
    wedding_type = forms.ChoiceField(
        label="نوع محصول عروسی",
        choices=Product.WeddingType.choices,
        required=True,
        help_text="نوع را انتخاب کنید؛ بخش و دستهٔ سیستمی به‌صورت خودکار تعیین می‌شود.",
    )

    class Meta:
        model = WeddingProduct
        fields = (
            "cover_image",
            "name",
            "pricing_type",
            "price",
            "price_usd",
            "stock_status",
            "publish_status",
            "is_active",
            "wedding_type",
            "wedding_sort_order",
            "description",
            "slug",
        )
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
            "cover_image": PersianImageInput,
            "description": forms.Textarea(attrs={"rows": 4}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.wedding_needs_review:
            self.fields["wedding_type"].required = False
            self.fields["wedding_type"].choices = (
                ("", "نیازمند تعیین نوع"),
                *Product.WeddingType.choices,
            )
            self.fields["wedding_type"].help_text = (
                "این محصول legacy هنوز نوع قطعی ندارد؛ با انتخاب یکی از چهار نوع، "
                "دستهٔ صحیح به‌صورت خودکار ثبت می‌شود."
            )

    def clean(self):
        cleaned_data = super().clean()
        wedding_type = cleaned_data.get("wedding_type") or ""

        self.instance.catalog_scope = Product.CatalogScope.WEDDING
        self.instance.featured = False

        if not wedding_type:
            if self.instance._state.adding or not self.instance.wedding_needs_review:
                self.add_error(
                    "wedding_type",
                    "برای محصول جدید عروسی یکی از چهار نوع مجاز را انتخاب کنید.",
                )
            else:
                self.instance.wedding_type = ""
            return cleaned_data

        category_key = Product.WEDDING_CATEGORY_MAP.get(wedding_type)
        if category_key is None:
            self.add_error("wedding_type", "نوع انتخاب‌شده معتبر نیست.")
            return cleaned_data

        section, slug = category_key
        category = (
            Category.objects.for_weddings()
            .filter(section=section, slug=slug, is_active=True)
            .first()
        )
        if category is None:
            self.add_error(
                "wedding_type",
                "دستهٔ سیستمی این نوع پیدا نشد یا غیرفعال است؛ ابتدا migrationها را بررسی کنید.",
            )
            return cleaned_data

        self.instance.category = category
        self.instance.wedding_type = wedding_type
        self.instance.wedding_needs_review = False
        return cleaned_data


class WeddingPageContentAdminForm(forms.ModelForm):
    class Meta:
        model = WeddingPageContent
        fields = "__all__"
        field_classes = {
            "hero_image": AdminImageUploadField,
            "hero_mobile_image": AdminImageUploadField,
            "proposal_bouquet_card_image": AdminImageUploadField,
            "proposal_sweets_card_image": AdminImageUploadField,
            "bridal_bouquet_card_image": AdminImageUploadField,
            "wedding_car_card_image": AdminImageUploadField,
            "open_graph_image": AdminImageUploadField,
        }
        widgets = {
            "hero_text": forms.Textarea(attrs={"rows": 3}),
            "proposal_text": forms.Textarea(attrs={"rows": 3}),
            "wedding_day_text": forms.Textarea(attrs={"rows": 3}),
            "bridal_bouquet_card_text": forms.Textarea(attrs={"rows": 2}),
            "wedding_car_card_text": forms.Textarea(attrs={"rows": 2}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        field_help = {
            "hero_image": "تصویر اصلی دسکتاپ؛ ترجیحاً افقی و عریض (حدود 16:9).",
            "hero_mobile_image": "اختیاری؛ نسخه عمودی یا موبایل. اگر خالی باشد تصویر دسکتاپ استفاده می‌شود.",
            "hero_title": "تیتر بزرگ روی تصویر Hero.",
            "hero_text": "یک توضیح کوتاه؛ بهتر است حداکثر دو خط باشد.",
            "proposal_title": "اختیاری؛ عنوان فارسی بالای دو کارت. اگر خالی باشد این عنوان نمایش داده نمی‌شود.",
            "proposal_text": "اختیاری؛ برای طراحی مینیمال می‌توانید خالی بگذارید.",
            "proposal_bouquet_card_image": "تصویر مستقل کارت دسته‌گل خواستگاری؛ بهتر است افقی با نسبت حدود 5:3 باشد.",
            "proposal_sweets_card_image": "تصویر مستقل کارت شیرینی خواستگاری؛ بهتر است افقی با نسبت حدود 5:3 باشد.",
            "wedding_day_title": "عنوانی که بالای کارت‌های دسته‌گل عروس و ماشین عروس نمایش داده می‌شود.",
            "wedding_day_text": "توضیح کوتاه زیر عنوان روز عروسی.",
            "bridal_bouquet_card_image": "تصویر مستقل کارت دسته‌گل عروس؛ بهتر است با نسبت 4:3 بارگذاری شود.",
            "bridal_bouquet_card_kicker": "اختیاری؛ عنوان انگلیسی کوچک روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "bridal_bouquet_card_title": "اختیاری؛ عنوان فارسی روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "bridal_bouquet_card_text": "اختیاری؛ توضیح کوتاه روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "wedding_car_card_image": "تصویر مستقل کارت ماشین عروس؛ بهتر است با نسبت 4:3 بارگذاری شود.",
            "wedding_car_card_kicker": "اختیاری؛ عنوان انگلیسی کوچک روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "wedding_car_card_title": "اختیاری؛ عنوان فارسی روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "wedding_car_card_text": "اختیاری؛ توضیح کوتاه روی کارت. برای کارت فقط‌تصویر خالی بگذارید.",
            "gallery_title": "عنوان بالای گالری تصاویر. خود تصاویر را در انتهای همین صفحه اضافه و مرتب کنید.",
            "seo_title": "اختیاری؛ اگر خالی باشد عنوان پیش‌فرض صفحه استفاده می‌شود.",
            "meta_description": "اختیاری؛ خلاصه صفحه برای نتایج جست‌وجو. حدود 120 تا 160 کاراکتر مناسب است.",
            "open_graph_image": "اختیاری؛ تصویر اشتراک‌گذاری در شبکه‌های اجتماعی.",
            "is_active": "فقط یک تنظیم فعال وجود دارد. این گزینه را معمولاً روشن نگه دارید.",
        }
        for name, help_text in field_help.items():
            if name in self.fields:
                self.fields[name].help_text = help_text

        placeholders = {
            "hero_title": "مثلاً: از بله تا روز عروسی، کنار شما",
            "proposal_title": "مثلاً: خواستگاری و بله‌برون",
            "wedding_day_title": "مثلاً: روز عروسی",
            "bridal_bouquet_card_kicker": "BRIDAL BOUQUETS",
            "bridal_bouquet_card_title": "مثلاً: دسته‌گل عروس",
            "wedding_car_card_kicker": "WEDDING CARS",
            "wedding_car_card_title": "مثلاً: ماشین عروس",
            "gallery_title": "مثلاً: انتخاب‌های زاد",
            "seo_title": "عنوان صفحه در گوگل",
            "meta_description": "توضیح کوتاه صفحه برای گوگل",
        }
        for name, placeholder in placeholders.items():
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("placeholder", placeholder)

    def clean_hero_image(self):
        return validate_admin_image(self.cleaned_data.get("hero_image"))

    def clean_hero_mobile_image(self):
        return validate_admin_image(self.cleaned_data.get("hero_mobile_image"))

    def clean_proposal_bouquet_card_image(self):
        return validate_admin_image(
            self.cleaned_data.get("proposal_bouquet_card_image")
        )

    def clean_proposal_sweets_card_image(self):
        return validate_admin_image(
            self.cleaned_data.get("proposal_sweets_card_image")
        )

    def clean_bridal_bouquet_card_image(self):
        return validate_admin_image(
            self.cleaned_data.get("bridal_bouquet_card_image")
        )

    def clean_wedding_car_card_image(self):
        return validate_admin_image(
            self.cleaned_data.get("wedding_car_card_image")
        )

    def clean_open_graph_image(self):
        return validate_admin_image(self.cleaned_data.get("open_graph_image"))


class WeddingCollectionContentAdminForm(forms.ModelForm):
    class Meta:
        model = WeddingCollectionContent
        fields = "__all__"
        field_classes = {
            "hero_image": AdminImageUploadField,
            "hero_mobile_image": AdminImageUploadField,
        }
        widgets = {
            "hero_text": forms.Textarea(attrs={"rows": 3}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        placeholders = {
            "hero_kicker": "مثلاً: PROPOSAL BOUQUETS",
            "hero_title": "عنوان فارسی صفحه",
            "hero_text": "توضیح کوتاه و حداکثر دو خط",
            "hero_alt_text": "توضیح کوتاه تصویر برای دسترس‌پذیری",
            "seo_title": "عنوان صفحه در گوگل",
            "meta_description": "توضیح کوتاه صفحه برای گوگل",
        }
        for name, placeholder in placeholders.items():
            if name in self.fields:
                self.fields[name].widget.attrs.setdefault("placeholder", placeholder)

    def clean_hero_image(self):
        return validate_admin_image(self.cleaned_data.get("hero_image"))

    def clean_hero_mobile_image(self):
        return validate_admin_image(self.cleaned_data.get("hero_mobile_image"))


class WeddingGalleryImageAdminForm(forms.ModelForm):
    class Meta:
        model = WeddingGalleryImage
        fields = "__all__"
        field_classes = {"image": AdminImageUploadField}

    def clean_image(self):
        return validate_admin_image(self.cleaned_data.get("image"))


class NewsPostAdminForm(forms.ModelForm):
    class Meta:
        model = NewsPost
        fields = "__all__"
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 8}),
        }

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))


class EventAdminForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = "__all__"
        field_classes = {"cover_image": AdminImageUploadField}
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))


class HeroAdminForm(forms.ModelForm):
    class Meta:
        fields = "__all__"
        field_classes = {
            "image": AdminImageUploadField,
            "mobile_image": AdminImageUploadField,
        }
        widgets = {
            "text_color": forms.TextInput(attrs={"type": "color"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "custom_font" in self.fields:
            self.fields["custom_font"].queryset = HeroFont.objects.order_by(
                "-is_active", "name"
            )

        if "target_slug" in self.fields:
            field_name = self.add_prefix("target_page")
            target_page = self.data.get(field_name) or getattr(
                self.instance,
                "target_page",
                "",
            )
            if not target_page:
                self.fields["target_slug"].help_text = (
                    "ابتدا صفحه هدف را انتخاب کن. برای Hero اصلی صفحه، این فیلد خالی می‌ماند."
                )
            else:
                detail_help = HERO_TARGET_SLUG_HELP.get(target_page, "")
                self.fields["target_slug"].help_text = (
                    "برای Hero کل صفحه خالی بگذار. "
                    f"{detail_help or 'این صفحه مقصد جزئی ندارد و اسلاگ باید خالی بماند.'}"
                )

    def clean(self):
        cleaned_data = super().clean()
        if "target_slug" not in self.fields:
            return cleaned_data

        target_page = cleaned_data.get("target_page")
        raw_target_slug = (cleaned_data.get("target_slug") or "").strip()

        if "/" in raw_target_slug:
            self.add_error(
                "target_slug",
                "فقط خود اسلاگ را وارد کن؛ مسیر کامل یا / لازم نیست.",
            )
            return cleaned_data

        target_slug = slugify(raw_target_slug, allow_unicode=True)
        cleaned_data["target_slug"] = target_slug

        if target_slug and target_page not in HERO_SLUG_TARGET_PAGES:
            self.add_error(
                "target_slug",
                "برای این صفحه Hero فقط به‌صورت سراسری تعریف می‌شود؛ اسلاگ را خالی بگذار.",
            )

        return cleaned_data

    def clean_image(self):
        return validate_admin_image(self.cleaned_data.get("image"))

    def clean_mobile_image(self):
        return validate_admin_image(self.cleaned_data.get("mobile_image"))


class HeroFontAdminForm(forms.ModelForm):
    class Meta:
        model = HeroFont
        fields = "__all__"

    def clean_font_file(self):
        uploaded_file = self.cleaned_data.get("font_file")
        if not uploaded_file:
            return uploaded_file

        # When no replacement is uploaded Django returns the existing FieldFile.
        # Do not reopen a missing/remote file just to edit metadata; the public
        # Hero renderer safely falls back to the selected built-in font.
        if not hasattr(uploaded_file, "content_type"):
            return uploaded_file

        try:
            file_size = uploaded_file.size
            file_name = uploaded_file.name
        except (AttributeError, OSError, ValueError):
            raise forms.ValidationError(
                "فایل فونت خوانده نشد؛ لطفاً فایل را دوباره انتخاب کنید."
            )

        if file_size > MAX_ADMIN_FONT_SIZE:
            raise forms.ValidationError("حجم فایل فونت نباید بیشتر از ۵ مگابایت باشد.")

        extension = file_name.rsplit(".", 1)[-1].lower()
        if extension not in {"woff2", "woff", "ttf", "otf"}:
            raise forms.ValidationError(
                "فقط فایل‌های WOFF2، WOFF، TTF و OTF قابل آپلود هستند."
            )

        signatures = {
            "woff2": {b"wOF2"},
            "woff": {b"wOFF"},
            "ttf": {b"\x00\x01\x00\x00", b"true"},
            "otf": {b"OTTO"},
        }
        try:
            position = uploaded_file.tell()
            header = uploaded_file.read(4)
            uploaded_file.seek(position)
        except (AttributeError, OSError, ValueError):
            raise forms.ValidationError(
                "محتوای فایل فونت خوانده نشد؛ لطفاً یک فایل سالم انتخاب کنید."
            )
        if header not in signatures[extension]:
            raise forms.ValidationError(
                "پسوند فایل درست است اما محتوای آن فونت معتبر نیست."
            )

        return uploaded_file


class ProductImageAdminForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = "__all__"
        field_classes = {"image": AdminImageUploadField}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "product" in self.fields:
            self.fields["product"].queryset = Product.objects.for_general_catalog()

    def clean_image(self):
        return validate_admin_image(self.cleaned_data.get("image"))


class ProductImageInline(AdminImagePreviewMixin, admin.StackedInline):
    model = ProductImage
    form = ProductImageAdminForm
    extra = 1
    fields = (
        "image",
        "image_preview",
        "alt_text",
        "ordering",
        "created_at",
        "updated_at",
    )
    readonly_fields = (
        "image_preview",
        "created_at",
        "updated_at",
    )
    ordering = (
        "ordering",
        "id",
    )
    verbose_name = "عکس گالری"
    verbose_name_plural = "گالری محصول"


class WeddingGalleryImageInline(AdminImagePreviewMixin, admin.TabularInline):
    model = WeddingGalleryImage
    form = WeddingGalleryImageAdminForm
    extra = 1
    fields = (
        "image_preview",
        "image",
        "alt_text",
        "sort_order",
    )
    readonly_fields = ("image_preview",)
    ordering = ("sort_order", "id")
    verbose_name = "تصویر"
    verbose_name_plural = "گالری تصاویر — برای جابه‌جایی، عدد ترتیب نمایش را تغییر دهید"


class GeneralParentCategoryFilter(admin.SimpleListFilter):
    title = "دسته والد"
    parameter_name = "parent__id__exact"

    def lookups(self, request, model_admin):
        return [
            (str(category.pk), category.name)
            for category in Category.objects.for_general_catalog()
            .filter(parent__isnull=True)
            .order_by("section", "sort_order", "name")
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(parent_id=self.value())
        return queryset


@admin.register(Category)
class CategoryAdmin(ActiveActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = CategoryAdminForm

    list_display = (
        "image_preview",
        "name",
        "section",
        "parent",
        "is_active",
        "sort_order",
        "product_count",
        "updated_at",
    )
    list_filter = (
        "section",
        GeneralParentCategoryFilter,
        "is_active",
    )
    search_fields = (
        "name",
        "slug",
        "description",
    )
    ordering = (
        "section",
        "sort_order",
        "name",
    )
    list_editable = (
        "is_active",
        "sort_order",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
        "product_count",
    )
    save_on_top = True
    list_per_page = 30

    fieldsets = (
        (
            "۱. زیر‌دسته",
            {
                "description": (
                    "زیر‌دسته یعنی نوع فیزیکی محصول؛ مثل دسته گل، باکس، استند، "
                    "کیک تولد یا شمع. دسته‌های سیستمی عروسی در بخش مستقل عروسی "
                    "مدیریت می‌شوند و در این فرم نمایش داده نمی‌شوند. محصولاتی "
                    "که هنوز زیردسته دقیق ندارند می‌توانند مستقیم در والد بمانند "
                    "و همچنان در صفحه آن نمایش داده می‌شوند."
                ),
                "fields": (
                    "cover_image",
                    "image_preview",
                    "name",
                    "section",
                    "parent",
                ),
            },
        ),
        (
            "۲. توضیح کوتاه",
            {
                "fields": (
                    "description",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "۳. نمایش",
            {
                "description": "برای مخفی کردن یک زیر‌دسته، فعال را خاموش کن. عدد کمتر یعنی نمایش بالاتر.",
                "fields": (
                    "is_active",
                    "sort_order",
                ),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "product_count",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).for_general_catalog()
        return queryset.annotate(
            products_total=Count("products", distinct=True),
            child_products_total=Count("children__products", distinct=True),
        )

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_wedding_category:
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset.for_general_catalog())

    @admin.display(description="تعداد محصول")
    def product_count(self, obj):
        if not obj.pk:
            return 0

        if hasattr(obj, "products_total"):
            return obj.products_total

        return obj.products.count()


@admin.register(Tag)
class TagAdmin(ActiveActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = TagAdminForm

    list_display = (
        "image_preview",
        "name",
        "is_occasion",
        "is_active",
        "sort_order",
        "product_count",
    )
    list_filter = (
        "is_occasion",
        "is_active",
    )
    search_fields = (
        "name",
        "slug",
        "description",
    )
    ordering = (
        "sort_order",
        "name",
    )
    list_editable = (
        "is_occasion",
        "is_active",
        "sort_order",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
        "product_count",
    )
    list_per_page = 40
    save_on_top = True

    fieldsets = (
        (
            "۱. برچسب",
            {
                "description": "برچسب یعنی مناسبت یا کاربرد محصول؛ مثل تولد، عاشقانه، تبریک، ترحیم یا ارسال روز.",
                "fields": (
                    "cover_image",
                    "image_preview",
                    "name",
                    "slug",
                ),
            },
        ),
        (
            "۲. کارت مناسبتی",
            {
                "description": "اگر روشن باشد، این برچسب می‌تواند در کارت‌های مناسبتی سایت نمایش داده شود.",
                "fields": (
                    "is_occasion",
                    "description",
                ),
            },
        ),
        (
            "۳. نمایش",
            {
                "fields": (
                    "is_active",
                    "sort_order",
                ),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "product_count",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        queryset = super().get_queryset(request).for_general_catalog()
        return queryset.annotate(products_total=Count("products"))

    def has_delete_permission(self, request, obj=None):
        if obj is not None and obj.is_wedding_legacy:
            return False
        return super().has_delete_permission(request, obj=obj)

    def delete_queryset(self, request, queryset):
        super().delete_queryset(request, queryset.for_general_catalog())

    @admin.display(description="تعداد محصول")
    def product_count(self, obj):
        if not obj.pk:
            return 0

        if hasattr(obj, "products_total"):
            return obj.products_total + getattr(obj, "child_products_total", 0)

        return obj.products.count() + Product.objects.filter(
            category__parent=obj
        ).count()


class SectionCategoryFilter(admin.SimpleListFilter):
    title = "زیردسته"
    parameter_name = "category"

    def lookups(self, request, model_admin):
        queryset = (
            Category.objects.for_general_catalog()
            .filter(is_active=True)
            .select_related("parent")
        )

        if getattr(model_admin, "section_filter", None):
            queryset = queryset.filter(section=model_admin.section_filter)

        return [
            (
                category.pk,
                (
                    f"{category.parent.name} / {category.name}"
                    if category.parent_id
                    else category.name
                ),
            )
            for category in queryset.order_by("sort_order", "name")
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(category_id=self.value())

        return queryset


class BaseProductAdmin(ProductActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = ProductAdminForm
    section_filter = None
    catalog_scope_filter = Product.CatalogScope.GENERAL

    list_display = (
        "image_preview",
        "product_code_display",
        "name_display",
        "price_toman",
        "category_display",
        "stock_badge",
        "featured",
    )

    list_filter = (
        SectionCategoryFilter,
        "stock_status",
        "featured",
        "is_active",
    )

    search_fields = (
        "product_code",
        "name",
        "category__name",
        "tags__name",
    )
    search_help_text = (
        "نام یا کد محصول را وارد کنید؛ کد با رقم فارسی یا انگلیسی قابل جست‌وجو است."
    )

    readonly_fields = (
        "product_code",
        "created_at",
        "updated_at",
        "image_preview",
        "large_image_preview",
    )

    ordering = (
        "sort_order",
        "-updated_at",
    )

    list_editable = ()
    inlines = [ProductImageInline]
    list_select_related = ("category",)
    list_per_page = 25
    save_on_top = True
    actions_on_top = True
    actions_on_bottom = False

    fieldsets = (
        (
            "۱. عکس و نام محصول",
            {
                "description": "اول عکس اصلی و اسم محصول را وارد کن.",
                "fields": (
                    "cover_image",
                    "image_preview",
                    "large_image_preview",
                    "name",
                ),
            },
        ),
        (
            "۲. قیمت و موجودی",
            {
                "description": "اگر قیمت قطعی نیست، نوع قیمت‌گذاری را استعلامی بگذار.",
                "fields": (
                    "pricing_type",
                    "price",
                    "price_usd",
                    "stock_status",
                ),
            },
        ),
        (
            "۳. نمایش در سایت",
            {
                "description": "برای دیده شدن در سایت، محصول باید فعال و منتشرشده باشد.",
                "fields": (
                    "publish_status",
                    "is_active",
                    "featured",
                    "sort_order",
                ),
            },
        ),
        (
            "۴. نوع محصول و مناسبت",
            {
                "fields": (
                    "category",
                    "tags",
                ),
            },
        ),
        (
            "۵. توضیح",
            {
                "fields": (
                    "description",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "product_code",
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_form(self, request, obj=None, change=False, **kwargs):
        form_class = super().get_form(request, obj, change, **kwargs)
        form_class.section_filter = self.section_filter
        return form_class

    def get_queryset(self, request):
        queryset = (
            super()
            .get_queryset(request)
            .select_related("category")
            .prefetch_related("tags")
        )

        if self.catalog_scope_filter == Product.CatalogScope.WEDDING:
            queryset = queryset.for_weddings()
        else:
            queryset = queryset.for_general_catalog()

        if self.section_filter:
            queryset = queryset.filter(category__section=self.section_filter)

        return queryset

    def get_search_results(self, request, queryset, search_term):
        normalized_term = to_english_digits(search_term).strip()
        return super().get_search_results(request, queryset, normalized_term)

    @admin.display(description="کد", ordering="product_code")
    def product_code_display(self, obj):
        if not obj.product_code:
            return "-"

        return format_html(
            '<strong style="font-size:13px;letter-spacing:.04em;">{}</strong>',
            to_persian_digits(obj.product_code),
        )

    @admin.display(description="نام محصول", ordering="name")
    def name_display(self, obj):
        if not obj.name:
            return "-"

        return obj.name

    @admin.display(description="قیمت", ordering="price")
    def price_toman(self, obj):
        if obj.pricing_type == Product.PricingType.INQUIRY or not obj.price:
            return format_html(
                '<span class="zad-price zad-price--inquiry">{}</span>',
                "استعلام قیمت",
            )

        price_parts = [format_toman(obj.price)]

        if obj.price_usd:
            price_parts.append(f"{int(obj.price_usd):,} USD")

        return format_html(
            '<span class="zad-price">{}</span>',
            " · ".join(price_parts),
        )

    @admin.display(description="نوع", ordering="category__name")
    def category_display(self, obj):
        if not obj.category_id:
            return "-"

        return obj.category.name

    @admin.display(description="موجودی", ordering="stock_status")
    def stock_badge(self, obj):
        label_map = {
            Product.StockStatus.IN_STOCK: "موجود",
            Product.StockStatus.OUT_OF_STOCK: "ناموجود",
            Product.StockStatus.PREORDER: "پیش‌سفارش",
        }

        return label_map.get(obj.stock_status, "-")

    def get_changeform_initial_data(self, request):
        initial = {
            "pricing_type": Product.PricingType.INQUIRY,
            "stock_status": Product.StockStatus.IN_STOCK,
            "publish_status": Product.PublishStatus.PUBLISHED,
            "is_active": True,
            "featured": False,
            "sort_order": 0,
        }

        if self.section_filter:
            first_category = (
                Category.objects.for_general_catalog().filter(
                    section=self.section_filter,
                    is_active=True,
                    children__isnull=True,
                )
                .order_by("sort_order", "name")
                .first()
            )

            if first_category:
                initial["category"] = first_category.pk

        return initial

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "category":
            queryset = Category.objects.for_general_catalog().filter(is_active=True)

            if self.section_filter:
                queryset = queryset.filter(section=self.section_filter)

            kwargs["queryset"] = queryset.order_by("section", "sort_order", "name")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tags":
            kwargs["queryset"] = (
                Tag.objects.for_general_catalog()
                .filter(is_active=True)
                .order_by(
                    "sort_order",
                    "name",
                )
            )

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if self.catalog_scope_filter == Product.CatalogScope.GENERAL:
            obj.catalog_scope = Product.CatalogScope.GENERAL
            obj.wedding_type = ""
            obj.wedding_needs_review = False
            obj.wedding_sort_order = 0

        if obj.pricing_type == Product.PricingType.INQUIRY:
            obj.price = None
            obj.price_usd = None

        super().save_model(request, obj, form, change)


@admin.register(Product)
class ProductAdmin(BaseProductAdmin):
    """
    این مدل برای مدیریت کلی محصول است، اما از صفحه اصلی ادمین مخفی می‌شود
    تا Behzad یک محصول را دو جا نبیند و گیج نشود.
    """

    list_filter = BaseProductAdmin.list_filter + ("category__section",)

    def has_module_permission(self, request):
        return False


@admin.register(Flower)
class FlowerAdmin(BaseProductAdmin):
    section_filter = Category.Section.FLOWERS

    fieldsets = (
        (
            "۱. عکس و نام گل",
            {
                "fields": (
                    "cover_image",
                    "large_image_preview",
                    "name", 
                ),
            },
        ),
        (
            "۲. قیمت و موجودی",
            {
                "fields": (
                    "pricing_type",
                    "price",
                    "price_usd",
                    "stock_status",
                ),
            },
        ),
        (
            "۳. انتشار در سایت",
            {
                "fields": (
                    "publish_status",
                    "is_active",
                    "featured",
                    "sort_order",
                ),
            },
        ),
        (
            "۴. نوع گل و مناسبت",
            {
                "description": (
                    "نوع گل مثل دسته گل، باکس، بوکت، استند، جار یا گیاه است. "
                    "محصولات عروسی را از بخش مستقل عروسی مدیریت کن. برچسب‌ها "
                    "برای تولد، عاشقانه، ترحیم یا ارسال روز هستند."
                ),
                "fields": (
                    "category",
                    "tags",
                ),
            },
        ),
        (
            "توضیح",
            {
                "fields": (
                    "description",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(SameDayFlower)
class SameDayFlowerAdmin(FlowerAdmin):
    """Edit only today's flowers; adding here preselects the same-day tag."""

    section_filter = Category.Section.FLOWERS
    list_per_page = 50
    list_display = (
        "image_preview",
        "product_code_display",
        "name_display",
        "category_display",
        "stock_badge",
        "tags_summary",
    )
    list_display_links = (
        "image_preview",
        "product_code_display",
        "name_display",
    )
    list_filter = (
        SectionCategoryFilter,
        "stock_status",
        "publish_status",
        "is_active",
    )
    actions = (
        "remove_from_same_day",
        "mark_in_stock",
        "mark_out_of_stock",
        "publish_selected_products",
        "draft_selected_products",
    )
    fieldsets = FlowerAdmin.fieldsets

    @staticmethod
    def _ensure_same_day_tag():
        tag = Tag.objects.filter(slug=SAME_DAY_TAG_SLUG).first()
        if tag is None:
            tag = Tag.objects.filter(name="ارسال روز").first()
        if tag is None:
            return Tag.objects.create(
                name="ارسال روز",
                slug=SAME_DAY_TAG_SLUG,
                is_active=True,
                is_occasion=False,
                sort_order=100,
            )

        update_fields = []
        if tag.slug != SAME_DAY_TAG_SLUG:
            tag.slug = SAME_DAY_TAG_SLUG
            update_fields.append("slug")
        if not tag.is_active:
            tag.is_active = True
            update_fields.append("is_active")
        if tag.is_occasion:
            tag.is_occasion = False
            update_fields.append("is_occasion")
        if update_fields:
            update_fields.append("updated_at")
            tag.save(update_fields=update_fields)
        return tag

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(tags__slug=SAME_DAY_TAG_SLUG)
            .distinct()
        )

    def get_changeform_initial_data(self, request):
        initial = super().get_changeform_initial_data(request)
        initial["tags"] = [self._ensure_same_day_tag().pk]
        return initial

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        product = form.instance
        if (
            product.catalog_scope != Product.CatalogScope.GENERAL
            or product.category.is_wedding_category
        ):
            raise forms.ValidationError(
                "محصول عروسی را نمی‌توان از بخش ارسال روز ذخیره کرد."
            )
        # Adding through this proxy must create a same-day product. On change,
        # however, the submitted checkbox selection is authoritative: removing
        # the tag intentionally removes the product from this proxy list.
        if not change:
            product.tags.add(self._ensure_same_day_tag())

    @admin.display(description="برچسب‌ها")
    def tags_summary(self, obj):
        names = [tag.name for tag in obj.tags.all() if tag.slug != SAME_DAY_TAG_SLUG]
        return "، ".join(names[:4]) or "—"

    @admin.action(
        permissions=["change"],
        description="حذف محصولات انتخاب‌شده از ارسال روز",
    )
    def remove_from_same_day(self, request, queryset):
        tag = Tag.objects.filter(slug=SAME_DAY_TAG_SLUG).first()
        products = list(queryset)
        if tag:
            tag.products.remove(*products)
        self.message_user(
            request,
            f"{len(products)} محصول از بخش ارسال روز حذف شد.",
        )


@admin.register(WeddingProduct)
class WeddingProductAdmin(BaseProductAdmin):
    form = WeddingProductAdminForm
    section_filter = None
    catalog_scope_filter = Product.CatalogScope.WEDDING
    list_per_page = 50
    ordering = ("wedding_sort_order", "-updated_at")
    list_display = (
        "image_preview",
        "product_code_display",
        "name_display",
        "wedding_type_display",
        "review_badge",
        "publish_status",
        "stock_badge",
        "wedding_sort_order",
    )
    list_display_links = (
        "image_preview",
        "product_code_display",
        "name_display",
    )
    list_editable = ("wedding_sort_order",)
    list_filter = (
        "wedding_type",
        "wedding_needs_review",
        "publish_status",
        "stock_status",
        "is_active",
    )
    search_fields = ("product_code", "name")
    actions = (
        "activate_selected",
        "deactivate_selected",
        "publish_selected_products",
        "draft_selected_products",
        "mark_in_stock",
        "mark_out_of_stock",
        "make_inquiry_pricing",
    )
    inlines = [ProductImageInline]
    fieldsets = (
        (
            "۱. عکس و نام محصول عروسی",
            {
                "fields": (
                    "cover_image",
                    "large_image_preview",
                    "name",
                )
            },
        ),
        (
            "۲. نوع محصول عروسی",
            {
                "description": (
                    "فقط یکی از چهار نوع مجاز را انتخاب کنید؛ بخش و دستهٔ سیستمی "
                    "به‌صورت خودکار تعیین می‌شود."
                ),
                "fields": ("wedding_type", "wedding_sort_order"),
            },
        ),
        (
            "۳. قیمت و موجودی",
            {
                "fields": (
                    "pricing_type",
                    "price",
                    "price_usd",
                    "stock_status",
                )
            },
        ),
        (
            "۴. انتشار در صفحه عروسی",
            {"fields": ("publish_status", "is_active")},
        ),
        (
            "توضیحات",
            {"fields": ("description",), "classes": ("collapse",)},
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "product_code",
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_changeform_initial_data(self, request):
        return {
            "pricing_type": Product.PricingType.INQUIRY,
            "stock_status": Product.StockStatus.IN_STOCK,
            "publish_status": Product.PublishStatus.PUBLISHED,
            "is_active": True,
            "wedding_sort_order": 0,
        }

    @admin.display(description="نوع عروسی", ordering="wedding_type")
    def wedding_type_display(self, obj):
        if obj.wedding_needs_review or not obj.wedding_type:
            return "نیازمند تعیین نوع"
        return obj.get_wedding_type_display()

    @admin.display(
        boolean=True,
        description="نیازمند بررسی",
        ordering="wedding_needs_review",
    )
    def review_badge(self, obj):
        return obj.wedding_needs_review

    def save_model(self, request, obj, form, change):
        obj.catalog_scope = Product.CatalogScope.WEDDING
        obj.featured = False
        wedding_type = form.cleaned_data.get("wedding_type") or ""
        if wedding_type:
            section, slug = Product.WEDDING_CATEGORY_MAP[wedding_type]
            obj.category = Category.objects.for_weddings().get(
                section=section,
                slug=slug,
                is_active=True,
            )
            obj.wedding_type = wedding_type
            obj.wedding_needs_review = False
        super().save_model(request, obj, form, change)

    def save_related(self, request, form, formsets, change):
        super().save_related(request, form, formsets, change)
        form.instance.tags.clear()

    @admin.action(
        permissions=["change"],
        description="انتشار محصولات معتبر انتخاب‌شده",
    )
    def publish_selected_products(self, request, queryset):
        valid_queryset = queryset.valid_weddings()
        selected_count = queryset.count()
        updated = valid_queryset.update(
            publish_status=Product.PublishStatus.PUBLISHED
        )
        skipped = selected_count - updated
        message = f"{updated} محصول معتبر عروسی منتشر شد."
        if skipped:
            message += f" {skipped} مورد نیازمند بررسی یا ناسازگار منتشر نشد."
        self.message_user(request, message)


@admin.register(BakeryItem)
class BakeryItemAdmin(BaseProductAdmin):
    section_filter = Category.Section.BAKERY

    fieldsets = (
        (
            "۱. عکس و نام محصول بیکری",
            {
                "fields": (
                    "cover_image",
                    "large_image_preview",
                    "name",
                ),
            },
        ),
        (
            "۲. قیمت و موجودی",
            {
                "fields": (
                    "pricing_type",
                    "price",
                    "price_usd",
                    "stock_status",
                ),
            },
        ),
        (
            "۳. انتشار در سایت",
            {
                "fields": (
                    "publish_status",
                    "is_active",
                    "featured",
                    "sort_order",
                ),
            },
        ),
        (
            "۴. نوع بیکری و مناسبت",
            {
                "description": "زیر‌دسته مثل کیک تولد یا کوکی است. برچسب مثل تولد، تبریک، یونیک یا بدون مناسبت است.",
                "fields": (
                    "category",
                    "tags",
                ),
            },
        ),
        (
            "توضیح",
            {
                "fields": (
                    "description",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(GiftItem)
class GiftItemAdmin(BaseProductAdmin):
    section_filter = Category.Section.GIFTS

    fieldsets = (
        (
            "۱. عکس و نام هدیه",
            {
                "fields": (
                    "cover_image",
                    "large_image_preview",
                    "name",
                ),
            },
        ),
        (
            "۲. قیمت و موجودی",
            {
                "fields": (
                    "pricing_type",
                    "price",
                    "price_usd",
                    "stock_status",
                ),
            },
        ),
        (
            "۳. انتشار در سایت",
            {
                "fields": (
                    "publish_status",
                    "is_active",
                    "featured",
                    "sort_order",
                ),
            },
        ),
        (
            "۴. نوع هدیه و مناسبت",
            {
                "description": "زیر‌دسته مثل شمع، سفال یا سایر است. برچسب مثل تولد، تبریک، یونیک یا بدون مناسبت است.",
                "fields": (
                    "category",
                    "tags",
                ),
            },
        ),
        (
            "توضیح",
            {
                "fields": (
                    "description",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(ProductImage)
class ProductImageAdmin(
    HiddenFromAdminIndexMixin,
    AdminImagePreviewMixin,
    admin.ModelAdmin,
):
    form = ProductImageAdminForm
    actions = ("promote_to_cover",)
    list_display = (
        "image_preview",
        "product",
        "ordering",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "created_at",
    )
    search_fields = (
        "product__name",
        "product__slug",
        "alt_text",
    )
    ordering = (
        "product",
        "ordering",
    )
    list_editable = (
        "ordering",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
    )
    list_select_related = (
        "product",
    )
    save_on_top = True

    fieldsets = (
        (
            "تصویر",
            {
                "fields": (
                    "product",
                    "image",
                    "image_preview",
                    "alt_text",
                ),
            },
        ),
        (
            "نمایش",
            {
                "fields": (
                    "ordering",
                ),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(product__in=Product.objects.for_general_catalog())
            .select_related("product")
        )

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "product":
            kwargs["queryset"] = Product.objects.for_general_catalog()
        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    @admin.action(
        permissions=["change"],
        description="استفاده از عکس انتخاب‌شده به عنوان تصویر اصلی محصول",
    )
    def promote_to_cover(self, request, queryset):
        updated = 0

        for image in queryset.select_related("product"):
            image.product.cover_image = image.image
            image.product.save(update_fields=["cover_image", "updated_at"])
            updated += 1

        self.message_user(request, f"{updated} تصویر به عنوان کاور محصول تنظیم شد.")


@admin.register(NewsPost)
class NewsPostAdmin(
    HiddenFromAdminIndexMixin,
    PublishActionsMixin,
    AdminImagePreviewMixin,
    admin.ModelAdmin,
):
    form = NewsPostAdminForm

    list_display = (
        "image_preview",
        "title",
        "status",
        "published_at",
        "created_at",
        "updated_at",
    )
    list_filter = (
        "status",
        "published_at",
        "created_at",
    )
    search_fields = (
        "title",
        "slug",
        "excerpt",
        "body",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
    )
    ordering = (
        "-published_at",
        "-created_at",
    )
    date_hierarchy = "published_at"
    list_editable = (
        "status",
    )
    save_on_top = True

    fieldsets = (
        (
            "محتوا",
            {
                "fields": (
                    "title",
                    "excerpt",
                    "body",
                ),
            },
        ),
        (
            "رسانه و انتشار",
            {
                "fields": (
                    "cover_image",
                    "image_preview",
                    "status",
                    "published_at",
                ),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(Event)
class EventAdmin(PublishActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = EventAdminForm

    list_display = (
        "image_preview",
        "title",
        "status",
        "schedule_status",
        "start_at",
        "end_at",
        "location",
        "published_at",
    )
    list_filter = (
        "status",
        "start_at",
        "end_at",
        "published_at",
    )
    search_fields = (
        "title",
        "slug",
        "description",
        "location",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
    )
    ordering = (
        "start_at",
        "-created_at",
    )
    date_hierarchy = "start_at"
    list_editable = (
        "status",
    )
    save_on_top = True

    @admin.display(description="وضعیت زمانی")
    def schedule_status(self, obj):
        now = timezone.now()
        if obj.end_at < now:
            return "پایان‌یافته"
        if obj.start_at <= now:
            return "در حال برگزاری"
        return "آینده"

    fieldsets = (
        (
            "محتوا",
            {
                "fields": (
                    "title",
                    "description",
                ),
            },
        ),
        (
            "زمان و مکان",
            {
                "fields": (
                    "start_at",
                    "end_at",
                    "location",
                ),
            },
        ),
        (
            "رسانه و انتشار",
            {
                "fields": (
                    "cover_image",
                    "image_preview",
                    "status",
                    "published_at",
                ),
            },
        ),
        (
            "تنظیمات پیشرفته",
            {
                "fields": (
                    "slug",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(TelegramBotUser)
class TelegramBotUserAdmin(admin.ModelAdmin):
    list_display = (
        "name",
        "telegram_user_id",
        "telegram_username",
        "can_receive_leads",
        "can_lookup_products",
        "is_active",
        "updated_at",
    )
    list_filter = (
        "is_active",
        "can_receive_leads",
        "can_lookup_products",
    )
    list_editable = (
        "can_receive_leads",
        "can_lookup_products",
        "is_active",
    )
    search_fields = (
        "name",
        "=telegram_user_id",
        "telegram_username",
        "notes",
    )
    readonly_fields = ("created_at", "updated_at")
    ordering = ("name", "telegram_user_id")
    save_on_top = True
    list_per_page = 30

    fieldsets = (
        (
            "کاربر تلگرام",
            {
                "fields": (
                    "name",
                    "telegram_user_id",
                    "telegram_username",
                    "is_active",
                )
            },
        ),
        (
            "دسترسی‌ها",
            {
                "description": (
                    "هر دسترسی مستقل است؛ می‌توان فقط یکی یا هر دو را فعال کرد."
                ),
                "fields": (
                    "can_receive_leads",
                    "can_lookup_products",
                ),
            },
        ),
        (
            "یادداشت و زمان‌ها",
            {
                "fields": ("notes", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(LeadRequest)
class LeadRequestAdmin(admin.ModelAdmin):
    list_display = (
        "full_name",
        "mobile",
        "lead_type",
        "product",
        "delivery_window",
        "preferred_date",
        "created_at",
    )
    list_filter = (
        "lead_type",
        "delivery_window",
        "created_at",
    )
    search_fields = (
        "full_name",
        "mobile",
        "product__name",
        "note",
        "event_location",
        "source_page",
    )
    readonly_fields = (
        "created_at",
        "updated_at",
    )
    ordering = (
        "-created_at",
    )
    list_select_related = (
        "product",
    )
    list_per_page = 30

    fieldsets = (
        (
            "اطلاعات متقاضی",
            {
                "fields": (
                    "full_name",
                    "mobile",
                    "lead_type",
                    "product",
                ),
            },
        ),
        (
            "جزئیات سفارش",
            {
                "fields": (
                    "delivery_window",
                    "preferred_date",
                    "event_location",
                    "note",
                ),
            },
        ),
        (
            "فنی",
            {
                "fields": (
                    "source_page",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(HeroFont)
class HeroFontAdmin(admin.ModelAdmin):
    form = HeroFontAdminForm
    list_display = (
        "name",
        "file_type",
        "is_active",
        "usage_count",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("name", "font_file")
    list_editable = ("is_active",)
    readonly_fields = ("usage_count", "created_at", "updated_at")
    save_on_top = True
    fieldsets = (
        (
            "آپلود فونت Hero",
            {
                "description": (
                    "فایل WOFF2 بهترین انتخاب برای سرعت سایت است. بعد از ذخیره، "
                    "این فونت در فرم Hero خانه و Hero صفحات قابل انتخاب می‌شود. "
                    "اگر فایل پاک یا غیرفعال شود، سایت خودکار به فونت داخلی برمی‌گردد."
                ),
                "fields": ("name", "font_file", "is_active"),
            },
        ),
        (
            "اطلاعات",
            {
                "fields": ("usage_count", "created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    @admin.display(description="فرمت")
    def file_type(self, obj):
        if not obj.font_file or "." not in obj.font_file.name:
            return "—"
        return obj.font_file.name.rsplit(".", 1)[-1].upper()

    @admin.display(description="تعداد استفاده")
    def usage_count(self, obj):
        if not obj.pk:
            return 0
        return obj.home_hero_slides.count() + obj.site_heroes.count()


class HeroAdminBase(admin.ModelAdmin):
    form = HeroAdminForm
    list_per_page = 20
    save_on_top = True

    readonly_fields = (
        "created_at",
        "updated_at",
        "image_preview",
        "mobile_image_preview",
    )

    search_fields = (
        "title",
        "kicker",
        "description",
    )

    ordering = (
        "sort_order",
        "id",
    )

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("custom_font")

    @admin.display(description="فونت")
    def font_display(self, obj):
        if obj.custom_font_id:
            suffix = "" if obj.custom_font.is_active else " (غیرفعال؛ fallback)"
            return f"{obj.custom_font.name}{suffix}"
        return obj.get_builtin_font_display()

    @admin.display(description="پیش‌نمایش تصویر")
    def image_preview(self, obj):
        if obj and obj.image:
            image_url = safe_image_url(obj.image)
            if not image_url:
                return "تصویر قابل نمایش نیست"
            return format_html(
                '<img src="{}" class="zad-admin-hero-preview" alt="" />',
                image_url,
            )

        return format_html(
            '<span class="zad-admin-hero-empty-preview zad-admin-hero-empty-preview--desktop">{}</span>',
            "بدون عکس",
        )

    @admin.display(description="پیش‌نمایش موبایل")
    def mobile_image_preview(self, obj):
        if obj and obj.mobile_image:
            image_url = safe_image_url(obj.mobile_image)
            if not image_url:
                return "تصویر قابل نمایش نیست"
            return format_html(
                '<img src="{}" class="zad-admin-hero-mobile-preview" alt="" />',
                image_url,
            )

        return format_html(
            '<span class="zad-admin-hero-empty-preview zad-admin-hero-empty-preview--mobile">{}</span>',
            "ندارد",
        )


@admin.register(HomeHeroSlide)
class HomeHeroSlideAdmin(HeroAdminBase):
    list_display = (
        "image_preview",
        "mobile_image_preview",
        "title",
        "font_display",
        "content_position",
        "mobile_content_position",
        "is_active",
        "sort_order",
        "updated_at",
    )

    list_filter = (
        "is_active",
        "created_at",
        "updated_at",
    )

    list_editable = (
        "is_active",
        "sort_order",
    )

    fieldsets = (
        (
            "۱. متن اسلاید صفحه خانه",
            {
                "fields": (
                    "title",
                    "kicker",
                    "description",
                ),
            },
        ),
        (
            "۲. چیدمان و تایپوگرافی",
            {
                "description": (
                    "موقعیت و اندازه‌های دسکتاپ و موبایل مستقل‌اند. ابتدا فونت داخلی "
                    "را انتخاب کن؛ فونت آپلودی اختیاری است و اگر مشکل داشته باشد، "
                    "سایت بدون خطا از همان فونت داخلی استفاده می‌کند."
                ),
                "fields": (
                    "content_position",
                    "mobile_content_position",
                    "text_color",
                    "builtin_font",
                    "custom_font",
                    "title_font_size",
                    "body_font_size",
                    "mobile_title_font_size",
                    "mobile_body_font_size",
                ),
            },
        ),
        (
            "۳. عکس اسلاید",
            {
                "fields": (
                    "image",
                    "image_preview",
                    "mobile_image",
                    "mobile_image_preview",
                ),
            },
        ),
        (
            "۴. دکمه‌ها",
            {
                "fields": (
                    "primary_button_text",
                    "primary_button_url",
                    "secondary_button_text",
                    "secondary_button_url",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "۵. نمایش در سایت",
            {
                "fields": (
                    "is_active",
                    "sort_order",
                ),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(SiteHero)
class SiteHeroAdmin(HeroAdminBase):
    list_display = (
        "image_preview",
        "mobile_image_preview",
        "title",
        "target_page_display",
        "target_slug_display",
        "font_display",
        "content_position",
        "mobile_content_position",
        "is_active",
        "sort_order",
        "updated_at",
    )

    list_filter = (
        "target_page",
        "is_active",
        "created_at",
        "updated_at",
    )

    list_editable = (
        "is_active",
        "sort_order",
    )

    search_fields = (
        "title",
        "kicker",
        "description",
        "target_slug",
    )

    @admin.display(description="صفحه")
    def target_page_display(self, obj):
        return obj.get_target_page_display()

    @admin.display(description="اسلاگ هدف")
    def target_slug_display(self, obj):
        if obj.target_slug:
            return obj.target_slug

        return "کل صفحه"

    fieldsets = (
        (
            "۱. این بنر برای کجاست؟",
            {
                "description": (
                    "صفحه هدف را انتخاب کن. برای Hero اصلی همان صفحه، «اسلاگ هدف» "
                    "را خالی بگذار. اسلاگ فقط برای ورکشاپ، مناسبت، مطلب، صفحه مشهد، "
                    "زیردسته یا محصول مشخص استفاده می‌شود."
                ),
                "fields": (
                    "target_page",
                    "target_slug",
                ),
            },
        ),
        (
            "۲. متن بنر",
            {
                "fields": (
                    "title",
                    "kicker",
                    "description",
                ),
            },
        ),
        (
            "۳. چیدمان و تایپوگرافی",
            {
                "description": (
                    "برای اینکه متن روی سوژه نیفتد، جای آن را برای دسکتاپ و موبایل "
                    "جدا انتخاب کن. فونت آپلودی اختیاری است؛ در صورت حذف یا خرابی "
                    "فایل، فونت داخلی به‌صورت خودکار جایگزین می‌شود."
                ),
                "fields": (
                    "content_position",
                    "mobile_content_position",
                    "text_color",
                    "builtin_font",
                    "custom_font",
                    "title_font_size",
                    "body_font_size",
                    "mobile_title_font_size",
                    "mobile_body_font_size",
                ),
            },
        ),
        (
            "۴. عکس بنر",
            {
                "fields": (
                    "image",
                    "image_preview",
                    "mobile_image",
                    "mobile_image_preview",
                ),
            },
        ),
        (
            "۵. نمایش در سایت",
            {
                "fields": (
                    "is_active",
                    "sort_order",
                ),
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )


@admin.register(WeddingCollectionContent)
class WeddingCollectionContentAdmin(admin.ModelAdmin):
    form = WeddingCollectionContentAdminForm
    list_display = (
        "collection_name",
        "hero_title",
        "has_desktop_image",
        "has_mobile_image",
        "updated_at",
    )
    list_filter = ("collection_key",)
    search_fields = ("hero_title", "hero_kicker", "hero_text")
    ordering = ("collection_key",)
    save_on_top = True
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "صفحه مجموعه",
            {
                "fields": ("collection_key",),
                "description": "هر ردیف تنظیمات یکی از چهار صفحه محصولات عروسی را کنترل می‌کند.",
            },
        ),
        (
            "Hero صفحه",
            {
                "fields": (
                    "hero_image",
                    "hero_mobile_image",
                    "hero_kicker",
                    "hero_title",
                    "hero_text",
                    "hero_alt_text",
                ),
                "description": (
                    "عنوان‌ها و توضیح اختیاری‌اند. اگر هر سه فیلد متنی خالی باشند، "
                    "Hero فقط تصویر نمایش می‌دهد."
                ),
            },
        ),
        (
            "SEO — اختیاری",
            {
                "fields": ("seo_title", "meta_description"),
                "classes": ("collapse",),
            },
        ),
        (
            "اطلاعات سیستمی",
            {
                "fields": ("created_at", "updated_at"),
                "classes": ("collapse",),
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly = list(self.readonly_fields)
        if obj:
            readonly.append("collection_key")
        return tuple(readonly)

    @admin.display(description="مجموعه")
    def collection_name(self, obj):
        return obj.get_collection_key_display()

    @admin.display(description="تصویر دسکتاپ", boolean=True)
    def has_desktop_image(self, obj):
        return bool(obj.hero_image)

    @admin.display(description="تصویر موبایل", boolean=True)
    def has_mobile_image(self, obj):
        return bool(obj.hero_mobile_image)


@admin.register(WeddingPageContent)
class WeddingPageContentAdmin(admin.ModelAdmin):
    form = WeddingPageContentAdminForm
    inlines = [WeddingGalleryImageInline]
    list_display = (
        "__str__",
        "is_active",
        "updated_at",
    )
    readonly_fields = ("admin_guide", "created_at", "updated_at")
    save_on_top = True

    fieldsets = (
        (
            "راهنمای سریع",
            {
                "fields": ("admin_guide",),
                "classes": ("wedding-admin-guide",),
            },
        ),
        (
            "۱) تصویر و متن بالای صفحه",
            {
                "fields": (
                    "hero_image",
                    "hero_mobile_image",
                    "hero_title",
                    "hero_text",
                ),
                "description": "Hero اولین بخش صفحه است. تصویر دسکتاپ ضروری و تصویر موبایل اختیاری است.",
            },
        ),
        (
            "۲) بخش خواستگاری و بله‌برون",
            {
                "fields": (
                    "proposal_title",
                    "proposal_bouquet_card_image",
                    "proposal_sweets_card_image",
                ),
                "description": "عنوان این قسمت مربوط به نوار جداکننده است. خود کارت‌ها فقط تصویر نمایش می‌دهند و عنوان یا توضیح قابل‌نمایش ندارند.",
            },
        ),
        (
            "۳) عنوان بخش روز عروسی",
            {
                "fields": (
                    "wedding_day_title",
                    "wedding_day_text",
                ),
                "description": "این عنوان و توضیح بالای دو کارت روز عروسی نمایش داده می‌شوند.",
            },
        ),
        (
            "۴) کارت دسته‌گل عروس",
            {
                "fields": (
                    "bridal_bouquet_card_image",
                    "bridal_bouquet_card_kicker",
                    "bridal_bouquet_card_title",
                    "bridal_bouquet_card_text",
                ),
                "description": "عکس را مستقل از محصولات عوض کنید. برای نمایش کارت فقط به‌صورت تصویر، هر سه فیلد متنی را خالی بگذارید.",
            },
        ),
        (
            "۵) کارت ماشین عروس",
            {
                "fields": (
                    "wedding_car_card_image",
                    "wedding_car_card_kicker",
                    "wedding_car_card_title",
                    "wedding_car_card_text",
                ),
                "description": "عکس را مستقل از محصولات عوض کنید. برای نمایش کارت فقط به‌صورت تصویر، هر سه فیلد متنی را خالی بگذارید.",
            },
        ),
        (
            "۶) گالری تصاویر",
            {
                "fields": ("gallery_title",),
                "description": "عنوان گالری را اینجا بنویسید و تصاویر را در جدول پایین همین فرم مدیریت کنید.",
            },
        ),
        (
            "SEO و اشتراک‌گذاری — اختیاری",
            {
                "fields": (
                    "seo_title",
                    "meta_description",
                    "open_graph_image",
                ),
                "classes": ("collapse",),
            },
        ),
        (
            "تنظیمات سیستمی",
            {
                "fields": (
                    "is_active",
                    "created_at",
                    "updated_at",
                ),
                "classes": ("collapse",),
            },
        ),
    )

    class Media:
        css = {"all": ("main/css/admin-wedding-page.css",)}

    @admin.display(description="")
    def admin_guide(self, obj):
        return mark_safe(
            '<div class="wedding-admin-guide__content">'
            '<strong>ترتیب کار پیشنهادی</strong>'
            '<ol>'
            '<li>Hero و عنوان‌های دو بخش اصلی را تنظیم کنید.</li>'
            '<li>دو تصویر کارت خواستگاری را جداگانه آپلود کنید.</li>'
            '<li>عنوان گالری را بنویسید و تصاویر گالری را در جدول پایین فرم مرتب کنید.</li>'
            '<li>در پایان روی «ذخیره» بزنید.</li>'
            '</ol>'
            '<p>کارت‌های خواستگاری فقط تصویر نمایش می‌دهند؛ عنوان و توضیح روی خود کارت‌ها وجود ندارد.</p>'
            '</div>'
        )

    def has_add_permission(self, request):
        if WeddingPageContent.objects.exists():
            return False
        return super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(WorkshopPageContent)
class WorkshopPageContentAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    list_display = (
        "__str__",
        "is_active",
        "updated_at",
    )
    list_editable = ("is_active",)
    readonly_fields = ("created_at", "updated_at")
    save_on_top = True

    fieldsets = (
        (
            "بخش فلسفه ورکشاپ‌ها",
            {
                "fields": (
                    "story_kicker",
                    "story_title",
                    "story_text",
                ),
            },
        ),
        (
            "بخش برنامه‌های آینده",
            {
                "fields": (
                    "upcoming_kicker",
                    "upcoming_title",
                    "upcoming_empty_title",
                    "upcoming_empty_text",
                ),
            },
        ),
        (
            "بخش انواع ورکشاپ",
            {
                "fields": (
                    "types_kicker",
                    "types_title",
                    "public_title",
                    "public_text",
                    "private_title",
                    "private_text",
                    "corporate_title",
                    "corporate_text",
                ),
            },
        ),
        (
            "بخش درخواست و هماهنگی",
            {
                "fields": (
                    "cta_title",
                    "cta_text",
                ),
            },
        ),
        (
            "نمایش",
            {
                "fields": (
                    "is_active",
                    "created_at",
                    "updated_at",
                ),
            },
        ),
    )


@admin.register(PageContentBlock)
class PageContentBlockAdmin(HiddenFromAdminIndexMixin, admin.ModelAdmin):
    list_display = (
        "page",
        "section_key",
        "title",
        "is_active",
        "sort_order",
        "updated_at",
    )
    list_filter = ("page", "is_active")
    search_fields = ("section_key", "kicker", "title", "body", "cta_text")
    list_editable = ("is_active", "sort_order")
    ordering = ("page", "sort_order", "section_key")
    readonly_fields = ("created_at", "updated_at")
    save_on_top = True
    fieldsets = (
        (
            "جایگاه متن",
            {"fields": ("page", "section_key", "sort_order", "is_active")},
        ),
        (
            "محتوا",
            {"fields": ("kicker", "title", "body")},
        ),
        (
            "دکمه اختیاری",
            {"fields": ("cta_text", "cta_url")},
        ),
        (
            "زمان‌ها",
            {"fields": ("created_at", "updated_at"), "classes": ("collapse",)},
        ),
    )

