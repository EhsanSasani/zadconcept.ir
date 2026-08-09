"""Existing admin registrations pending domain-by-domain extraction."""

from django import forms
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html
from django.utils.text import slugify

from ..image_pipeline import ImageUploadError, normalize_admin_image
from ..models import (
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
                    "همچنان در صفحه آن نمایش داده می‌شوند."
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
                    "برای عروسی فقط «ماشین عروس» یا «دسته‌گل عروس» را انتخاب "
                    "کن؛ عروسی برچسب نیست. برچسب‌ها برای تولد، عاشقانه، ترحیم "
                    "یا ارسال روز هستند."
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

    @admin.display(description="برچسب‌ها")
    def tags_summary(self, obj):
        names = [tag.name for tag in obj.tags.all() if tag.slug != SAME_DAY_TAG_SLUG]
        return "، ".join(names[:4]) or "—"

    @admin.action(description="حذف محصولات انتخاب‌شده از ارسال روز")
    def remove_from_same_day(self, request, queryset):
        tag = Tag.objects.filter(slug=SAME_DAY_TAG_SLUG).first()
        products = list(queryset)
        if tag:
            tag.products.remove(*products)
        self.message_user(
            request,
            f"{len(products)} محصول از بخش ارسال روز حذف شد.",
        )


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

    @admin.action(description="استفاده از عکس انتخاب‌شده به عنوان تصویر اصلی محصول")
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
