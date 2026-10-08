"""Localized inputs for the purchase and waste ledger."""
from decimal import Decimal

from django import forms
from django.forms import BaseFormSet, formset_factory
from django.utils import timezone

from .models import Material
from .persian_dates import parse_persian_date
from .team_forms import latin_digits


class PersianDecimalField(forms.DecimalField):
    def __init__(self, *args, money=False, **kwargs):
        self.money = money
        kwargs.setdefault('widget', forms.TextInput(attrs={
            'inputmode': 'numeric' if money else 'decimal', 'dir': 'ltr',
            'autocomplete': 'off', 'data-money' if money else 'data-quantity': ''}))
        super().__init__(*args, **kwargs)

    def to_python(self, value):
        if value not in self.empty_values:
            value = latin_digits(value).replace('٬', '').replace(',', '').replace(' ', '').replace('٫', '.')
            # Dotted grouping is conventional for whole-toman amounts only.
            if self.money and '.' in value:
                parts = value.split('.')
                if 1 <= len(parts[0]) <= 3 and all(len(p) == 3 and p.isdigit() for p in parts[1:]):
                    value = ''.join(parts)
            if any(character in value for character in ('e', 'E', '+', '-')):
                raise forms.ValidationError('عدد مثبت و بدون علامت وارد کنید.')
        return super().to_python(value)


class JalaliDayField(forms.CharField):
    def __init__(self, **kwargs):
        super().__init__(label='تاریخ (شمسی)', max_length=10,
            widget=forms.TextInput(attrs={'dir': 'ltr', 'placeholder': '۱۴۰۵/۰۷/۱۵'}), **kwargs)

    def clean(self, value):
        value = super().clean(value)
        try:
            day = parse_persian_date(value.replace('.', '/').replace('-', '/'))
        except ValueError as error:
            raise forms.ValidationError('تاریخ شمسی معتبر مانند ۱۴۰۵/۰۷/۱۵ وارد کنید.') from error
        if day > timezone.localdate():
            raise forms.ValidationError('تاریخ نمی‌تواند در آینده باشد.')
        return day


class MaterialForm(forms.Form):
    version = forms.CharField(required=False, widget=forms.HiddenInput)
    name = forms.CharField(label='نام کالا', max_length=120,
        widget=forms.TextInput(attrs={'placeholder': 'مثلاً رز هلندی', 'autofocus': True}))
    base_unit = forms.CharField(label='واحد پایه / دورریز', max_length=30,
        widget=forms.TextInput(attrs={'placeholder': 'مثلاً شاخه، عدد یا متر'}))
    purchase_unit = forms.CharField(label='واحد خرید', max_length=30,
        widget=forms.TextInput(attrs={'placeholder': 'مثلاً بسته یا دسته'}))
    units_per_purchase = PersianDecimalField(label='تعداد واحد پایه در هر واحد خرید',
        max_digits=9, decimal_places=3, min_value=Decimal('0.001'), initial=1,
        help_text='مقدار پیش‌فرض؛ در هر ردیف فاکتور قابل تغییر است.')
    default_unit_price = PersianDecimalField(label='قیمت مرجع هر واحد خرید (تومان)',
        max_digits=15, decimal_places=0, min_value=0, money=True,
        help_text='قیمت پیشنهادی هنگام ثبت خرید؛ مبلغ واقعی هر فاکتور جدا ذخیره می‌شود.')
    is_active = forms.BooleanField(label='کالا برای ثبت جدید فعال باشد', required=False, initial=True)


class PurchaseForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    date = JalaliDayField()
    supplier = forms.CharField(label='فروشنده / تأمین‌کننده', max_length=120, required=False)
    reference = forms.CharField(label='شماره فاکتور فروشنده', max_length=80, required=False)
    notes = forms.CharField(label='یادداشت', max_length=1000, required=False,
        widget=forms.Textarea(attrs={'rows': 2}))


class WasteForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    date = JalaliDayField()
    reason = forms.ChoiceField(label='علت دورریز', choices=[
        ('wilted', 'پژمردگی'), ('damaged', 'آسیب‌دیدگی'), ('expired', 'ماندگی'), ('other', 'سایر')])
    notes = forms.CharField(label='توضیحات', max_length=1000, required=False,
        widget=forms.Textarea(attrs={'rows': 2}))


class PurchaseLineForm(forms.Form):
    material_version = forms.CharField(required=False, widget=forms.HiddenInput)
    material = forms.ModelChoiceField(label='کالا', queryset=Material.objects.none(), empty_label='انتخاب کالا')
    unit_mode = forms.ChoiceField(label='واحد', choices=[('purchase', 'واحد خرید'), ('base', 'واحد پایه')], initial='purchase')
    quantity = PersianDecimalField(label='مقدار', max_digits=12, decimal_places=3, min_value=Decimal('0.001'))
    conversion_factor = PersianDecimalField(label='تعداد در هر بسته', required=False,
        max_digits=9, decimal_places=3, min_value=Decimal('0.001'),
        help_text='خالی = تعداد پیش‌فرض کالا. برای واحد پایه همیشه ۱ است.')
    unit_price = PersianDecimalField(label='قیمت هر واحد انتخاب‌شده (تومان)',
        max_digits=15, decimal_places=0, min_value=0, money=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['material'].queryset = Material.objects.filter(is_active=True).order_by('name')


class WasteLineForm(PurchaseLineForm):
    unit_price = None
    unit_mode = forms.ChoiceField(label='واحد', choices=[('base', 'واحد پایه'), ('purchase', 'واحد خرید')], initial='base')


class EntryLineFormSet(BaseFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return
        lines = [f.cleaned_data for f in self.forms if f.cleaned_data and not f.cleaned_data.get('DELETE')]
        if not lines:
            raise forms.ValidationError('حداقل یک ردیف کالا اضافه کنید.')


PurchaseLineFormSet = formset_factory(PurchaseLineForm, formset=EntryLineFormSet,
    extra=3, can_delete=True, max_num=50, validate_max=True, absolute_max=50)
WasteLineFormSet = formset_factory(WasteLineForm, formset=EntryLineFormSet,
    extra=3, can_delete=True, max_num=50, validate_max=True, absolute_max=50)


class VoidForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)
    reason = forms.CharField(label='علت ابطال', min_length=3, max_length=500,
        widget=forms.Textarea(attrs={'rows': 2}))
