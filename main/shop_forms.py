"""Forms for the independent online shop; catalog scope is never client input."""
from django import forms
from django.db.models import Q

from .image_pipeline import ImageUploadError, normalize_admin_image
from .models import Category, Product, ShopConfiguration
from .customer_auth import normalize_phone


DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


class ShopImageInput(forms.ClearableFileInput):
    initial_text = "تصویر فعلی"
    input_text = "جایگزین تصویر"
    clear_checkbox_label = "حذف تصویر"


class ShopCheckoutForm(forms.Form):
    recipient_name = forms.CharField(label="نام و نام خانوادگی تحویل‌گیرنده", max_length=120)
    recipient_phone = forms.CharField(label="شماره موبایل تحویل‌گیرنده", max_length=30,
        widget=forms.TextInput(attrs={"inputmode": "tel", "autocomplete": "tel", "dir": "ltr", "placeholder": "09xxxxxxxxx"}))
    customer_note = forms.CharField(label="یادداشت برای زاد", max_length=500, required=False,
        widget=forms.Textarea(attrs={"rows": 3, "placeholder": "در صورت نیاز، توضیح کوتاهی بنویسید."}))
    fulfillment = forms.ChoiceField(label="روش دریافت", choices=[("pickup", "دریافت حضوری از زاد")],
        widget=forms.RadioSelect, initial="pickup")
    recipient_address = forms.CharField(label="آدرس دریافت در مشهد", max_length=1000, required=False,
        help_text="فقط برای ارسال در مشهد لازم است؛ محله، خیابان، پلاک و واحد را بنویسید.",
        widget=forms.Textarea(attrs={"rows": 3, "autocomplete": "street-address"}))
    accept_terms = forms.BooleanField(label="شرایط خرید و لغو سفارش را خوانده‌ام و می‌پذیرم.")
    expected_total = forms.IntegerField(min_value=1, widget=forms.HiddenInput)

    def __init__(self, *args, configuration=None, **kwargs):
        super().__init__(*args, **kwargs)
        configuration = configuration or ShopConfiguration()
        choices = []
        if configuration.pickup_enabled:
            choices.append(("pickup", "دریافت حضوری از زاد"))
        if configuration.delivery_enabled and configuration.delivery_fee_toman is not None:
            choices.append(("delivery", "ارسال در مشهد"))
        self.fields["fulfillment"].choices = choices
        selected = self.data.get("fulfillment") if self.is_bound else self.initial.get("fulfillment", "pickup")
        self.fields["recipient_address"].required = selected == "delivery"

    def clean_recipient_phone(self):
        return normalize_phone(self.cleaned_data["recipient_phone"])

    def clean(self):
        data = super().clean()
        if data.get("fulfillment") == "delivery" and not self.has_error("recipient_address") and len(data.get("recipient_address", "").strip()) < 10:
            self.add_error("recipient_address", "آدرس کامل در مشهد را با حداقل ۱۰ نویسه وارد کنید.")
        return data


class ShopConfigurationForm(forms.ModelForm):
    class Meta:
        model = ShopConfiguration
        fields = ["pickup_enabled", "delivery_enabled", "delivery_fee_toman"]
        labels = {"pickup_enabled": "دریافت حضوری فعال باشد", "delivery_enabled": "ارسال در مشهد فعال باشد",
                  "delivery_fee_toman": "هزینه ثابت ارسال در مشهد (تومان)"}
        help_texts = {"delivery_fee_toman": "پیش از فعال‌کردن ارسال، مبلغ را تعیین کنید. برای ارسال رایگان، عدد صفر را صریح وارد کنید."}
        widgets = {"delivery_fee_toman": forms.NumberInput(attrs={"min": 0, "inputmode": "numeric"})}


class ShopProductForm(forms.ModelForm):
    cover_image = forms.FileField(label="تصویر محصول", required=False,
        widget=ShopImageInput(attrs={"accept": "image/*,.heic,.heif,.avif"}),
        help_text="تصویر واقعی محصول؛ هنگام ذخیره برای وب بهینه می‌شود.")
    inventory_quantity = forms.IntegerField(label="موجودی قابل فروش", min_value=0, max_value=1000000,
        help_text="تعداد قابل خرید؛ سفارش‌های رزروشده در این عدد نیستند.")
    inventory_version = forms.IntegerField(min_value=0, widget=forms.HiddenInput, initial=0)
    inventory_reason = forms.CharField(label="علت اصلاح موجودی", max_length=250, required=False,
        widget=forms.TextInput(attrs={"placeholder": "مثلاً ورود کالا یا اصلاح شمارش"}))

    class Meta:
        model = Product
        fields = ["name", "category", "description", "price", "cover_image", "is_active", "publish_status", "sort_order"]
        labels = {"price": "قیمت واحد (تومان)", "is_active": "محصول فعال باشد", "sort_order": "ترتیب نمایش"}
        widgets = {"description": forms.Textarea(attrs={"rows": 4}),
            "price": forms.NumberInput(attrs={"min": 1, "inputmode": "numeric"}),
            "name": forms.TextInput(attrs={"autocomplete": "off"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.catalog_scope = Product.CatalogScope.SHOP
        self.instance.pricing_type = Product.PricingType.FIXED
        self.instance.price_usd = None
        self.instance.stock_status = Product.StockStatus.IN_STOCK
        self.instance.wedding_type = ""
        self.instance.wedding_needs_review = False
        categories = Category.objects.for_general_catalog().exclude(section=Category.Section.EVENTS)
        self.fields["category"].queryset = categories.filter(Q(is_active=True) | Q(pk=self.instance.category_id))
        self.fields["name"].required = True
        self.fields["price"].required = True
        self.fields["price"].help_text = "قیمت ثابت هر واحد را به تومان وارد کنید."
        self.initial.setdefault("inventory_quantity", getattr(getattr(self.instance, "shop_inventory", None), "quantity", 0))
        self.initial.setdefault("inventory_version", getattr(getattr(self.instance, "shop_inventory", None), "version", 0))

    def clean_price(self):
        price = self.cleaned_data["price"]
        if price is None or price <= 0:
            raise forms.ValidationError("برای خرید آنلاین، قیمت باید بیشتر از صفر باشد.")
        return price

    def clean_cover_image(self):
        image = self.cleaned_data.get("cover_image")
        if image and "cover_image" in self.files:
            try:
                return normalize_admin_image(image)
            except ImageUploadError as error:
                raise forms.ValidationError(str(error)) from error
        return image

    def clean(self):
        data = super().clean()
        previous = getattr(getattr(self.instance, "shop_inventory", None), "quantity", 0)
        if self.instance.pk and data.get("inventory_quantity") != previous and not data.get("inventory_reason"):
            self.add_error("inventory_reason", "علت تغییر موجودی را بنویسید تا در سابقه ثبت شود.")
        if data.get("publish_status") == Product.PublishStatus.PUBLISHED and not data.get("cover_image"):
            self.add_error("cover_image", "پیش از انتشار، تصویر واقعی محصول را بارگذاری کنید.")
        return data
