"""Small counter sales share the sales ledger without inventing production."""
from datetime import datetime, time
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo

from django import forms
from django.contrib import messages
from django.core import signing
from django.core.exceptions import ValidationError
from django.db import transaction
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_http_methods

from .models import StudioProduct
from .persian_dates import format_persian_date, parse_persian_date
from .sales_service import _audit, snapshot, version
from .sales_views import sales_required
from .team_forms import latin_digits


class MiscSaleForm(forms.Form):
    token = forms.CharField(widget=forms.HiddenInput)
    version = forms.CharField(required=False, widget=forms.HiddenInput)
    date = forms.CharField(label='تاریخ فروش (شمسی)', max_length=10,
        widget=forms.TextInput(attrs={'dir': 'ltr', 'placeholder': '۱۴۰۵/۰۷/۲۰', 'autocomplete': 'off'}))
    description = forms.CharField(label='توضیحات / نام محصول', max_length=500,
        widget=forms.Textarea(attrs={'rows': 2, 'placeholder': 'مثلاً ۳ شاخه رز با کاغذپیچی', 'autofocus': True}))
    price = forms.CharField(label='مبلغ (تومان)', max_length=30,
        widget=forms.TextInput(attrs={'inputmode': 'numeric', 'dir': 'ltr', 'data-price-input': '', 'placeholder': '۲٬۳۰۰٬۰۰۰'}))

    def clean_date(self):
        try:
            value = parse_persian_date(self.cleaned_data['date'].replace('.', '/').replace('-', '/'))
        except ValueError as exc:
            raise forms.ValidationError('تاریخ شمسی معتبر، مانند ۱۴۰۵/۰۷/۲۰ وارد کنید.') from exc
        if value > timezone.localdate(timezone=ZoneInfo('Asia/Tehran')):
            raise forms.ValidationError('تاریخ فروش نمی‌تواند در آینده باشد.')
        return value

    def clean_price(self):
        raw = latin_digits(self.cleaned_data['price']).replace(',', '').replace('٬', '').replace('.', '').replace(' ', '')
        if not raw.isascii() or not raw.isdigit():
            raise forms.ValidationError('مبلغ را به تومان و بدون اعشار وارد کنید.')
        try:
            value = Decimal(raw)
        except InvalidOperation as exc:
            raise forms.ValidationError('مبلغ معتبر وارد کنید.') from exc
        if not 0 < value < 10**12:
            raise forms.ValidationError('مبلغ باید مثبت و حداکثر ۱۲ رقم باشد.')
        return value


@sales_required
@require_http_methods(['GET', 'POST'])
def counter(request, pk=None):
    record = get_object_or_404(StudioProduct, pk=pk, production_type='MISC', status='SOLD') if pk else None
    selected_date = request.session.get('misc_sale_date', format_persian_date(timezone.localdate()))
    initial = {'date': selected_date, 'token': signing.dumps({'actor': request.user.pk, 'key': str(uuid4())}, salt='misc-sale')}
    if record:
        initial.update(date=format_persian_date(timezone.localtime(record.sold_at).date()),
                       description=record.notes, price=record.price, version=version(record))
    form = MiscSaleForm(request.POST if request.method == 'POST' else None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            token = signing.loads(form.cleaned_data['token'], salt='misc-sale', max_age=86400 * 7)
            if token['actor'] != request.user.pk:
                raise signing.BadSignature
            when = datetime.combine(form.cleaned_data['date'], time.min, tzinfo=ZoneInfo('Asia/Tehran'))
            with transaction.atomic():
                if record:
                    current = StudioProduct.objects.select_for_update().get(pk=record.pk)
                    if current.status != 'SOLD' or version(current) != form.cleaned_data['version']:
                        raise ValidationError('این فروش تغییر کرده است؛ صفحه را تازه کنید و دوباره بررسی کنید.')
                    before = snapshot(current)
                    current.notes, current.price = form.cleaned_data['description'], form.cleaned_data['price']
                    current.sold_at = current.produced_at = when
                    current.save(update_fields=['notes', 'price', 'sold_at', 'produced_at', 'updated_at'])
                    _audit(current, request.user, 'edit', 'اصلاح فروش شاخه و متفرقه', before)
                else:
                    current, created = StudioProduct.objects.get_or_create(submission_key=token['key'], defaults={
                        'factor_code': 'M-' + token['key'].replace('-', ''), 'production_type': 'MISC',
                        'product_type': 'other', 'source': 'DASHBOARD', 'status': 'SOLD',
                        'notes': form.cleaned_data['description'], 'price': form.cleaned_data['price'],
                        'produced_at': when, 'sold_at': when, 'created_by': request.user})
                    if created:
                        _audit(current, request.user, 'create', 'ثبت فروش شاخه و متفرقه', {})
            request.session['misc_sale_date'] = format_persian_date(form.cleaned_data['date'])
            messages.success(request, f'فروش با شناسهٔ {current.pk} ذخیره شد. آمادهٔ ثبت فروش بعدی هستید.')
            return redirect('sales_misc')
        except (signing.BadSignature, KeyError):
            form.add_error(None, 'مهلت فرم تمام شده؛ صفحه را تازه کنید.')
        except ValidationError as exc:
            form.add_error(None, exc)
    records = StudioProduct.objects.filter(production_type='MISC').exclude(status='DELETED').order_by('-pk')
    page = Paginator(records, 20).get_page(request.GET.get('page'))
    return render(request, 'main/sales/misc.html', {'form': form, 'record': record, 'page': page, 'active': 'misc'},
                  status=400 if form.is_bound and form.errors else 200)
