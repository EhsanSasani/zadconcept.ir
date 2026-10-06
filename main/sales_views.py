"""Dedicated mobile sales workspace; its permission grants no manager/admin access."""
from functools import wraps
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo
from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods
from .models import Florist, StudioProduct, StudioSalesAudit
from .studio_access import can_use_sales, can_manage_studio
from .sales_service import apply_sales_action, version
from .image_pipeline import normalize_admin_image, ImageUploadError
from .team_forms import latin_digits


def sales_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not can_use_sales(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return never_cache(login_required(login_url='studio_login')(wrapped))


def today_bounds():
    zone = ZoneInfo('Asia/Tehran')
    day = timezone.now().astimezone(zone).date()
    start = datetime.combine(day, time.min, tzinfo=zone)
    return start, start + timedelta(days=1)


class SalesEditForm(forms.Form):
    version = forms.CharField(widget=forms.HiddenInput)
    image = forms.FileField(label='عکس جدید محصول', required=False,
        widget=forms.FileInput(attrs={'accept':'image/*,.heic,.heif,.avif','data-preview-input':''}))
    factor_code = forms.CharField(label='شماره فاکتور',max_length=40,widget=forms.TextInput(attrs={'dir':'ltr','autocapitalize':'characters'}))
    florist = forms.ModelChoiceField(label='فلوریست سازنده',queryset=Florist.objects.none(),empty_label='انتخاب فلوریست')
    product_type = forms.ChoiceField(label='نوع محصول',choices=StudioProduct.ProductType.choices)
    price = forms.DecimalField(label='قیمت (تومان)',max_digits=12,decimal_places=0,min_value=1,
        widget=forms.TextInput(attrs={'inputmode':'numeric','dir':'ltr','data-price-input':''}))
    notes = forms.CharField(label='یادداشت داخلی',required=False,max_length=2000,widget=forms.Textarea(attrs={'rows':3}))
    reason = forms.CharField(label='علت اصلاح',max_length=500,widget=forms.Textarea(attrs={'rows':2,'placeholder':'مثلاً اصلاح قیمت پس از هماهنگی با مدیر'}))

    def __init__(self, *args, record, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['florist'].queryset = Florist.objects.filter(Q(is_active=True)|Q(pk=record.florist_id))
    def clean_price(self):
        return self.cleaned_data['price']
    def clean_factor_code(self):
        return latin_digits(self.cleaned_data['factor_code']).strip().upper()
    def clean_image(self):
        image = self.cleaned_data.get('image')
        if not image:
            return None
        try:
            return normalize_admin_image(image)
        except ImageUploadError as error:
            raise forms.ValidationError(str(error)) from error


@sales_required
@require_http_methods(['GET'])
def home(request):
    start, end = today_bounds()
    records = StudioProduct.objects.exclude(status=StudioProduct.Status.DELETED)
    daily = records.filter(production_type=StudioProduct.ProductionType.DAILY)
    sold = records.filter(status=StudioProduct.Status.SOLD, sold_at__gte=start, sold_at__lt=end)
    stats = {'available':daily.filter(status='AVAILABLE').count(), 'sold':sold.count(),
             'value':sold.aggregate(value=Sum('price'))['value'] or 0}
    tab = request.GET.get('tab','available')
    filters = {
        'available':Q(production_type='DAILY',status='AVAILABLE'),
        'sold':Q(status='SOLD',sold_at__gte=start,sold_at__lt=end),
        'withdrawn':Q(production_type='DAILY',status='WITHDRAWN'),
        'misc':Q(production_type='MISC'), 'custom':Q(production_type='CUSTOM'), 'all':Q(),
    }
    if tab not in filters:tab='available'
    q = latin_digits(request.GET.get('q','').strip())[:100]
    records = records.filter(filters[tab])
    if q:
        matching = (Q(factor_code__icontains=q) & ~Q(production_type="MISC"))|Q(florist__name__icontains=q)|Q(florist__code__icontains=q)|(Q(production_type="MISC",notes__icontains=q)|Q(production_type="MISC",notes__icontains=request.GET.get("q", "").strip()[:100]))
        if q.isascii() and q.isdigit() and len(q) < 19:
            matching |= Q(production_type='MISC', pk=int(q))
        records = records.filter(matching)
    records = records.select_related('florist','product').order_by('-updated_at','-pk')
    page = Paginator(records,24).get_page(request.GET.get('page'))
    return render(request,'main/sales/home.html',{'page':page,'q':q,'tab':tab,'stats':stats,'active':'home'})


@sales_required
@require_http_methods(['GET','POST'])
def detail(request, pk):
    record = get_object_or_404(StudioProduct.objects.select_related('florist','product'),pk=pk)
    if record.production_type == 'MISC':
        return redirect('sales_misc_edit', pk=record.pk)
    initial = {name:getattr(record,name) for name in ('factor_code','product_type','price','notes')}
    initial.update(florist=record.florist_id,version=version(record))
    action = request.POST.get('action') if request.method=='POST' else None
    data = request.POST.copy() if action=='edit' else None
    if data is not None:data['price']=latin_digits(data.get('price','')).replace(',','').replace('٬','').replace(' ','')
    form = SalesEditForm(data,request.FILES if action=='edit' else None,record=record,initial=initial)
    error = None
    if request.method=='POST':
        valid = action != 'edit' or form.is_valid()
        if valid:
            try:
                apply_sales_action(pk=record.pk,actor=request.user,expected_version=request.POST.get('version',''),
                    action=action,reason=request.POST.get('reason',''),values=form.cleaned_data if action=='edit' else None)
            except (ValidationError,IntegrityError) as exc:
                error = 'این شماره فاکتور قبلاً ثبت شده است.' if isinstance(exc,IntegrityError) else ' '.join(exc.messages)
            else:
                messages.success(request,'تغییر ثبت شد. همگام‌سازی تلگرام از صف ارسال پیگیری می‌شود.')
                return redirect('sales_detail',pk=record.pk)
    jobs=record.deliveries.exclude(status='SENT').order_by('pk')
    return render(request,'main/sales/detail.html',{'record':record,'form':form,'error':error,
        'edit_open':action=='edit','version':version(record),'jobs':jobs,
        'audits':display_audits(record.sales_audits.select_related('actor')[:30]),'active':'home'},status=400 if error or (data is not None and form.errors) else 200)


@never_cache
@login_required(login_url='studio_login')
@require_http_methods(['GET'])
def history(request):
    if not (can_use_sales(request.user) or can_manage_studio(request.user)):
        raise PermissionDenied
    q=latin_digits(request.GET.get('q','').strip())[:100]
    audits=StudioSalesAudit.objects.select_related('record','actor')
    if q:audits=audits.filter(Q(record__factor_code__icontains=q)|Q(before__factor_code__icontains=q)|Q(after__factor_code__icontains=q)|Q(actor_name__icontains=q)|Q(reason__icontains=q))
    page=Paginator(audits,30).get_page(request.GET.get('page'))
    page.object_list=display_audits(page.object_list)
    return render(request,'main/sales/history.html',{'page':page,'q':q,'active':'history'})


def display_audits(audits):
    labels={'factor_code':'شماره فاکتور','florist_id':'فلوریست','product_type':'نوع محصول',
        'production_type':'نوع تولید','price':'قیمت (تومان)','status':'وضعیت','image':'عکس محصول',
        'notes':'یادداشت','sold_at':'زمان فروش','withdrawn_at':'زمان خروج','produced_at':'زمان تولید',
        'telegram_chat_id':'گروه تلگرام','telegram_message_id':'پیام تلگرام'}
    choices={'status':dict(StudioProduct.Status.choices),'product_type':dict(StudioProduct.ProductType.choices),
             'production_type':dict(StudioProduct.ProductionType.choices)}
    from .templatetags.studio_ui import fa_number
    audits=list(audits)
    ids={v for a in audits for v in [a.before.get('florist_id'),a.after.get('florist_id')] if v and str(v).isdigit()}
    names={str(f.pk):f.name for f in Florist.objects.filter(pk__in=ids)}
    def display(key,value):
        if not value:return '—'
        if key in choices:return choices[key].get(value,value)
        if key=='florist_id':return names.get(str(value),'فلوریست سابق')
        if key=='price':
            from decimal import Decimal
            return fa_number(Decimal(value))
        if key.endswith('_at'):
            try:return timezone.localtime(datetime.fromisoformat(value)).strftime('%Y/%m/%d %H:%M')
            except (ValueError,TypeError):return value
        if key=='image':return 'تصویر ثبت‌شده'
        return value
    for audit in audits:
        audit.changes=[{'label':label,'before':display(key,audit.before.get(key)),
                       'after':display(key,audit.after.get(key))}
            for key,label in labels.items() if audit.before.get(key)!=audit.after.get(key)]
    return audits
