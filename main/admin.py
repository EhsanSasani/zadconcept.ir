from django import forms
from django.contrib import admin
from django.db.models import Count
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe

from .models import (
    BakeryItem,
    Category,
    Event,
    Flower,
    GiftItem,
    HomeHeroSlide,
    LeadRequest,
    NewsPost,
    PageContentBlock,
    Product,
    ProductImage,
    PublishStatus,
    SiteHero,
    Tag,
    WorkshopPageContent,
)


admin.site.site_header = "پنل مدیریت زاد"
admin.site.site_title = "مدیریت زاد"
admin.site.index_title = "مدیریت محتوا، محصولات و درخواست‌ها"

MAX_ADMIN_IMAGE_SIZE = 10 * 1024 * 1024


class HiddenFromAdminIndexMixin:
    """Hide a registered model from admin index/sidebar without deleting it."""

    def get_model_perms(self, request):
        return {}
ALLOWED_ADMIN_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def validate_admin_image(uploaded_file):
    if not uploaded_file or not hasattr(uploaded_file, "content_type"):
        return uploaded_file

    if uploaded_file.content_type not in ALLOWED_ADMIN_IMAGE_TYPES:
        raise forms.ValidationError("فرمت تصویر باید JPG، PNG یا WEBP باشد.")

    if uploaded_file.size > MAX_ADMIN_IMAGE_SIZE:
        raise forms.ValidationError("حجم تصویر نباید بیشتر از ۱۰ مگابایت باشد.")

    return uploaded_file


def safe_image_url(image):
    try:
        return image.url
    except (ValueError, OSError):
        return ""


def to_persian_digits(value):
    value = str(value)
    english_digits = "0123456789"
    persian_digits = "۰۱۲۳۴۵۶۷۸۹"
    translation_table = str.maketrans(english_digits, persian_digits)
    return value.translate(translation_table)


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

    @admin.action(description="فعال‌کردن موارد انتخاب‌شده")
    def activate_selected(self, request, queryset):
        updated = queryset.update(is_active=True)
        self.message_user(request, f"{updated} مورد فعال شد.")

    @admin.action(description="غیرفعال‌کردن موارد انتخاب‌شده")
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

    @admin.action(description="ویژه‌کردن موارد انتخاب‌شده")
    def mark_featured(self, request, queryset):
        updated = queryset.update(featured=True)
        self.message_user(request, f"{updated} مورد ویژه شد.")

    @admin.action(description="حذف از موارد ویژه")
    def remove_featured(self, request, queryset):
        updated = queryset.update(featured=False)
        self.message_user(request, f"{updated} مورد از ویژه‌ها حذف شد.")

    @admin.action(description="انتشار موارد انتخاب‌شده")
    def publish_selected_products(self, request, queryset):
        updated = queryset.update(publish_status=Product.PublishStatus.PUBLISHED)
        self.message_user(request, f"{updated} مورد منتشر شد.")

    @admin.action(description="بازگردانی به پیش‌نویس")
    def draft_selected_products(self, request, queryset):
        updated = queryset.update(publish_status=Product.PublishStatus.DRAFT)
        self.message_user(request, f"{updated} مورد به پیش‌نویس برگشت.")

    @admin.action(description="علامت‌گذاری به عنوان موجود")
    def mark_in_stock(self, request, queryset):
        updated = queryset.update(stock_status=Product.StockStatus.IN_STOCK)
        self.message_user(request, f"{updated} مورد موجود شد.")

    @admin.action(description="علامت‌گذاری به عنوان ناموجود")
    def mark_out_of_stock(self, request, queryset):
        updated = queryset.update(stock_status=Product.StockStatus.OUT_OF_STOCK)
        self.message_user(request, f"{updated} مورد ناموجود شد.")

    @admin.action(description="قیمت‌گذاری به حالت استعلامی")
    def make_inquiry_pricing(self, request, queryset):
        updated = queryset.update(pricing_type=Product.PricingType.INQUIRY, price=None, price_usd=None)
        self.message_user(request, f"{updated} مورد استعلامی شد.")


class PublishActionsMixin:
    actions = ("publish_selected", "unpublish_selected")

    @admin.action(description="انتشار موارد انتخاب‌شده")
    def publish_selected(self, request, queryset):
        updated = queryset.update(
            status=PublishStatus.PUBLISHED,
            published_at=timezone.now(),
        )
        self.message_user(request, f"{updated} مورد منتشر شد.")

    @admin.action(description="بازگردانی به پیش‌نویس")
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
        widgets = {
            "description": forms.Textarea(
                attrs={
                    "rows": 3,
                    "placeholder": "یک توضیح کوتاه برای این زیر‌دسته بنویس.",
                }
            ),
        }

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))


class TagAdminForm(forms.ModelForm):
    class Meta:
        model = Tag
        fields = "__all__"
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

class PersianImageInput(forms.ClearableFileInput):
    initial_text = "عکس فعلی"
    input_text = "تغییر عکس"
    clear_checkbox_label = "حذف عکس فعلی"

class ProductAdminForm(forms.ModelForm):
    class Meta:
        fields = "__all__"
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

            category_queryset = Category.objects.filter(is_active=True)

            if section_filter:
                category_queryset = category_queryset.filter(section=section_filter)

            self.fields["category"].queryset = category_queryset.order_by(
                "section",
                "sort_order",
                "name",
            )
            self.fields["category"].help_text = "نوع فیزیکی محصول را انتخاب کن؛ مثل باکس، دسته گل، کیک تولد، شمع."

        if "tags" in self.fields:
            self.fields["tags"].queryset = Tag.objects.filter(
                is_active=True
            ).order_by("sort_order", "name")
            self.fields["tags"].help_text = "مناسبت یا کاربرد محصول؛ مثل تولد، ترحیم، ارسال روز، عاشقانه، یونیک و ..."

        if "price" in self.fields:
            self.fields["price"].help_text = "فقط عدد وارد کن؛ مثلاً 2500000."

        if "price_usd" in self.fields:
            self.fields["price_usd"].help_text = "اختیاری است؛ اگر قیمت دلاری نداری خالی بگذار."

        if "sort_order" in self.fields:
            self.fields["sort_order"].help_text = "عدد کمتر یعنی محصول بالاتر نمایش داده می‌شود."

        if "cover_image" in self.fields:
            self.fields["cover_image"].help_text = "تصویر اصلی محصول است و روی کارت‌ها، لیست‌ها و ابتدای صفحه محصول نمایش داده می‌شود. عکس‌های گالری کارت جداگانه نمی‌سازند."

        if "featured" in self.fields:
            self.fields["featured"].help_text = "محصول ویژه در بخش‌های انتخاب‌شده و ترتیب نمایش بالاتر اولویت می‌گیرد؛ محصولات غیر ویژه را مخفی نمی‌کند."

        if "tags" in self.fields:
            self.fields["tags"].help_text = "برچسب می‌تواند داخلی باشد یا اگر گزینه مناسبت روشن است، در بخش مناسبت‌های سایت نمایش داده شود. برچسب ارسال روز برای فیلتر ارسال فوری استفاده می‌شود."

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
        widgets = {
            "excerpt": forms.Textarea(attrs={"rows": 3}),
            "body": forms.Textarea(attrs={"rows": 8}),
        }


class EventAdminForm(forms.ModelForm):
    class Meta:
        model = Event
        fields = "__all__"
        widgets = {
            "description": forms.Textarea(attrs={"rows": 6}),
        }

    def clean_cover_image(self):
        return validate_admin_image(self.cleaned_data.get("cover_image"))


class HeroAdminForm(forms.ModelForm):
    class Meta:
        fields = "__all__"

    def clean_image(self):
        return validate_admin_image(self.cleaned_data.get("image"))

    def clean_mobile_image(self):
        return validate_admin_image(self.cleaned_data.get("mobile_image"))


class ProductImageAdminForm(forms.ModelForm):
    class Meta:
        model = ProductImage
        fields = "__all__"

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


@admin.register(Category)
class CategoryAdmin(ActiveActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = CategoryAdminForm

    list_display = (
        "image_preview",
        "name",
        "section",
        "is_active",
        "sort_order",
        "product_count",
        "updated_at",
    )
    list_filter = (
        "section",
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
                "description": "زیر‌دسته یعنی نوع فیزیکی محصول؛ مثل دسته گل، باکس، استند، کیک تولد، شمع.",
                "fields": (
                    "cover_image",
                    "image_preview",
                    "name",
                    "section",
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
        queryset = super().get_queryset(request)
        return queryset.annotate(products_total=Count("products"))

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
        queryset = super().get_queryset(request)
        return queryset.annotate(products_total=Count("products"))

    @admin.display(description="تعداد محصول")
    def product_count(self, obj):
        if not obj.pk:
            return 0

        if hasattr(obj, "products_total"):
            return obj.products_total

        return obj.products.count()
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

    def get_queryset(self, request):
        queryset = super().get_queryset(request)
        return queryset.annotate(products_total=Count("products"))

    @admin.display(description="تعداد محصول")
    def product_count(self, obj):
        if not obj.pk:
            return 0

        if hasattr(obj, "products_total"):
            return obj.products_total

        return obj.products.count()
class SectionCategoryFilter(admin.SimpleListFilter):
    title = "زیردسته"
    parameter_name = "category"

    def lookups(self, request, model_admin):
        queryset = Category.objects.filter(is_active=True)

        if getattr(model_admin, "section_filter", None):
            queryset = queryset.filter(section=model_admin.section_filter)

        return [
            (category.pk, category.name)
            for category in queryset.order_by("sort_order", "name")
        ]

    def queryset(self, request, queryset):
        if self.value():
            return queryset.filter(category_id=self.value())

        return queryset


class BaseProductAdmin(ProductActionsMixin, AdminImagePreviewMixin, admin.ModelAdmin):
    form = ProductAdminForm
    section_filter = None

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

        if self.section_filter:
            queryset = queryset.filter(category__section=self.section_filter)

        return queryset

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
                Category.objects.filter(
                    section=self.section_filter,
                    is_active=True,
                )
                .order_by("sort_order", "name")
                .first()
            )

            if first_category:
                initial["category"] = first_category.pk

        return initial

    def formfield_for_foreignkey(self, db_field, request, **kwargs):
        if db_field.name == "category":
            queryset = Category.objects.filter(is_active=True)

            if self.section_filter:
                queryset = queryset.filter(section=self.section_filter)

            kwargs["queryset"] = queryset.order_by("section", "sort_order", "name")

        return super().formfield_for_foreignkey(db_field, request, **kwargs)

    def formfield_for_manytomany(self, db_field, request, **kwargs):
        if db_field.name == "tags":
            kwargs["queryset"] = Tag.objects.filter(is_active=True).order_by(
                "sort_order",
                "name",
            )

        return super().formfield_for_manytomany(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
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
                "description": "زیر‌دسته مثل دسته گل، باکس گل، بوکت، استند، جار گل یا گیاه است. برچسب مثل تولد، عاشقانه، یونیک، ترحیم یا ارسال روز است.",
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

    @admin.display(description="پیش‌نمایش تصویر")
    def image_preview(self, obj):
        if obj and obj.image:
            return format_html(
                '''
                <img src="{}" style="
                    width:72px !important;
                    height:42px !important;
                    object-fit:cover !important;
                    border-radius:8px !important;
                    display:block !important;
                " />
                ''',
                obj.image.url,
            )

        return format_html(
            '<span style="display:inline-flex;width:72px;height:42px;align-items:center;justify-content:center;border:1px dashed #999;border-radius:8px;font-size:10px;color:#999;">{}</span>',
            "بدون عکس",
        )

    @admin.display(description="پیش‌نمایش موبایل")
    def mobile_image_preview(self, obj):
        if obj and obj.mobile_image:
            return format_html(
                '''
                <img src="{}" style="
                    width:32px !important;
                    height:54px !important;
                    object-fit:cover !important;
                    border-radius:8px !important;
                    display:block !important;
                " />
                ''',
                obj.mobile_image.url,
            )

        return format_html(
            '<span style="display:inline-flex;width:32px;height:54px;align-items:center;justify-content:center;border:1px dashed #999;border-radius:8px;font-size:9px;color:#999;">{}</span>',
            "ندارد",
        )


@admin.register(HomeHeroSlide)
class HomeHeroSlideAdmin(HeroAdminBase):
    list_display = (
        "image_preview",
        "title",
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
            "۲. عکس اسلاید",
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
            "۳. دکمه‌ها",
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
            "۴. نمایش در سایت",
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
        "title",
        "target_page_display",
        "target_slug_display",
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

    @admin.display(description="برای کدام دسته؟")
    def target_slug_display(self, obj):
        if obj.target_slug:
            return obj.target_slug

        return "کل صفحه"

    fieldsets = (
        (
            "۱. این بنر برای کجاست؟",
            {
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
            "۳. عکس بنر",
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
            "۴. نمایش در سایت",
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

