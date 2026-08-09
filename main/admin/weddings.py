"""Admin workflows for the independent Wedding catalog."""

from django import forms
from django.contrib import admin
from django.utils.safestring import mark_safe

from ..models import (
    Category,
    Product,
    WeddingCollectionContent,
    WeddingGalleryImage,
    WeddingPageContent,
    WeddingProduct,
)
from .legacy import (
    AdminImagePreviewMixin,
    AdminImageUploadField,
    BaseProductAdmin,
    PersianImageInput,
    ProductAdminForm,
    ProductImageInline,
    validate_admin_image,
)


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
