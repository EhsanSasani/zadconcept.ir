"""Small forms for daily work; identity and publication policy stay server-side."""
import re
import uuid

from django import forms
from django.contrib.auth.forms import AuthenticationForm

from .image_pipeline import ImageUploadError, normalize_admin_image
from .models import Florist, StudioProduct


_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


def latin_digits(value):
    return str(value or "").translate(_DIGITS)


class TeamLoginForm(AuthenticationForm):
    remember = forms.BooleanField(label="در این دستگاه وارد بمانم", required=False, initial=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].widget.attrs.update({"autocomplete": "username", "autocapitalize": "none", "dir": "ltr"})
        self.fields["password"].widget.attrs.update({"autocomplete": "current-password", "dir": "ltr"})

    def clean(self):
        if getattr(self, "login_throttled", False):
            raise forms.ValidationError("تلاش‌های ورود زیاد شده؛ ۱۵ دقیقه دیگر دوباره امتحان کنید.")
        return super().clean()


class TeamProductForm(forms.Form):
    image = forms.FileField(label="عکس محصول", widget=forms.FileInput(attrs={
        "accept": "image/*,.heic,.heif,.avif", "data-product-image": ""}))
    florist = forms.ModelChoiceField(
        label="فلوریست سازنده", queryset=Florist.objects.none(),
        empty_label="فلوریست را انتخاب کنید",
        error_messages={"required": "فلوریست سازنده را انتخاب کنید.",
                        "invalid_choice": "فلوریست انتخاب‌شده فعال نیست؛ یکی از فلوریست‌های فعال را انتخاب کنید."},
    )
    production_type = forms.ChoiceField(
        label="نوع تولید",
        choices=[(key, label) for key, label in StudioProduct.ProductionType.choices if key != "MISC"],
        error_messages={"required": "مشخص کنید محصول آماده روز است یا سفارش اختصاصی."},
    )
    product_type = forms.ChoiceField(label="نوع محصول", choices=StudioProduct.ProductType.choices)
    factor_code = forms.CharField(label="شماره فاکتور", max_length=40, widget=forms.TextInput(attrs={
        "autocomplete": "off", "autocapitalize": "characters", "dir": "ltr", "placeholder": "مثلاً ۱۰۲۴"}))
    price = forms.DecimalField(label="قیمت (تومان)", max_digits=12, decimal_places=0, min_value=1,
                              widget=forms.TextInput(attrs={"inputmode": "numeric", "autocomplete": "off", "dir": "ltr"}))
    submission_key = forms.UUIDField(widget=forms.HiddenInput, initial=uuid.uuid4)
    notes = forms.CharField(label="یادداشت خصوصی", required=False, max_length=2000,
                           widget=forms.Textarea(attrs={"rows": 3}))

    def __init__(self, data=None, *args, **kwargs):
        if data is not None:
            data = data.copy()
            data["price"] = re.sub(r"[,٬\s]", "", latin_digits(data.get("price")))
            data["factor_code"] = latin_digits(data.get("factor_code"))
        super().__init__(data, *args, **kwargs)
        self.fields["florist"].queryset = Florist.objects.filter(is_active=True).order_by("name", "pk")

    def clean_factor_code(self):
        value = self.cleaned_data["factor_code"].strip().upper()
        if not re.fullmatch(r"[A-Z0-9-]{1,40}", value):
            raise forms.ValidationError("شماره فاکتور فقط می‌تواند شامل عدد، حروف لاتین و خط تیره باشد.")
        if StudioProduct.objects.filter(factor_code__iexact=value).exists():
            raise forms.ValidationError("این شماره فاکتور قبلاً ثبت شده؛ شماره را بررسی کنید.")
        return value

    def clean_image(self):
        try:
            return normalize_admin_image(self.cleaned_data["image"])
        except ImageUploadError as error:
            raise forms.ValidationError(str(error)) from error


class TeamProfileForm(forms.ModelForm):
    photo = forms.FileField(label="عکس پروفایل", required=False, widget=forms.ClearableFileInput(attrs={
        "accept": "image/*,.heic,.heif,.avif"}))

    class Meta:
        model = Florist
        fields = ("photo", "name")

    def clean_photo(self):
        try:
            return normalize_admin_image(self.cleaned_data.get("photo"), max_dimension=800)
        except ImageUploadError as error:
            raise forms.ValidationError(str(error)) from error
