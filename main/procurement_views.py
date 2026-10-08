"""Private purchasing workspace and manager reporting, sharing one ledger."""
from functools import wraps
from datetime import datetime
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core import signing
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Count, Q, Sum
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from . import procurement_queries as queries, procurement_service as service
from .models import Material, ProcurementAudit, PurchaseInvoice, WasteEntry
from .persian_dates import format_persian_date
from .procurement_forms import (MaterialForm, PurchaseForm, PurchaseLineFormSet,
                                VoidForm, WasteForm, WasteLineFormSet)
from .studio_access import can_manage_studio, can_use_procurement
from .studio_views import _base as studio_context, _period


TOKEN_SALT = 'zad.procurement.entry.v1'


def workspace_required(view=None, *, manager_read=False):
    def decorate(function):
        @wraps(function)
        def wrapped(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path(), reverse('studio_login'))
            if not (can_use_procurement(request.user) or (manager_read and can_manage_studio(request.user))):
                raise PermissionDenied
            return function(request, *args, **kwargs)
        return never_cache(wrapped)
    return decorate(view) if view else decorate


def _context(request, active):
    return {'active': active, 'can_write': can_use_procurement(request.user),
            'can_manage_studio': can_manage_studio(request.user)}


def _errors(form, error):
    # Service validation may name model fields absent from this header form.
    for message in error.messages:
        form.add_error(None, message)


def _token(user, kind):
    return signing.dumps({'user': user.pk, 'kind': kind, 'key': str(uuid4()),
                          'catalog_at': timezone.now().isoformat()}, salt=TOKEN_SALT)


def _submission_key(request, kind, token):
    try:
        payload = signing.loads(token, salt=TOKEN_SALT, max_age=7 * 86400)
        if payload['user'] != request.user.pk or payload['kind'] != kind:
            raise ValueError
        return payload['key'], datetime.fromisoformat(payload['catalog_at'])
    except (signing.BadSignature, KeyError, TypeError, ValueError) as error:
        raise ValidationError('مهلت ثبت این فرم پایان یافته؛ صفحه را تازه کنید و دوباره ثبت کنید.') from error


@workspace_required
@require_GET
def home(request):
    today = timezone.localdate()
    return render(request, 'main/procurement/home.html', {
        **_context(request, 'home'), 'today': today,
        'summary': queries.report({'start': today, 'end': today}),
        'purchases': PurchaseInvoice.objects.select_related('created_by').order_by('-date', '-pk')[:5],
        'wastes': WasteEntry.objects.select_related('created_by').order_by('-date', '-pk')[:5],
    })


@workspace_required
@require_GET
def materials(request):
    search = request.GET.get('q', '').strip()[:120]
    rows = Material.objects.order_by('-is_active', 'name')
    if search:
        rows = rows.filter(name__icontains=search)
    return render(request, 'main/procurement/materials.html', {
        **_context(request, 'materials'), 'q': search,
        'page': Paginator(rows, 30).get_page(request.GET.get('page')),
    })


def _material_data():
    return [{**{key: str(getattr(item, key)) for key in
                ('name', 'base_unit', 'purchase_unit', 'units_per_purchase', 'default_unit_price')},
              'id': item.pk, 'version': service.record_version(item)}
            for item in Material.objects.filter(is_active=True).order_by('name')]


@workspace_required
@require_GET
def material_options(request):
    return JsonResponse({'materials': _material_data()})


@workspace_required
@require_http_methods(['GET', 'POST'])
def material_form(request, pk=None):
    record = get_object_or_404(Material, pk=pk) if pk else None
    initial = {key: getattr(record, key) for key in MaterialForm.base_fields if key != 'version'} if record else {}
    if record:
        initial['version'] = service.record_version(record)
    form = MaterialForm(request.POST if request.method == 'POST' else None, initial=initial)
    if request.method == 'POST' and form.is_valid():
        try:
            record = service.save_material(actor=request.user, data=form.cleaned_data,
                pk=pk, expected_version=form.cleaned_data.get('version'))
        except ValidationError as error:
            _errors(form, error)
        except IntegrityError:
            form.add_error(None, 'کالایی با این نام ثبت شده است؛ نام دیگری انتخاب کنید.')
        else:
            messages.success(request, 'کالا ذخیره شد.')
            return redirect('procurement_materials')
    return render(request, 'main/procurement/material_form.html', {
        **_context(request, 'materials'), 'form': form, 'record': record, 'material': record,
    }, status=400 if request.method == 'POST' else 200)


@workspace_required
@require_http_methods(['GET', 'POST'])
def entry_form(request, kind):
    is_purchase = kind == 'purchase'
    header_class, line_class = (PurchaseForm, PurchaseLineFormSet) if is_purchase else (WasteForm, WasteLineFormSet)
    initial = {'date': format_persian_date(timezone.localdate()), 'token': _token(request.user, kind)}
    form = header_class(request.POST if request.method == 'POST' else None, initial=initial)
    formset = line_class(request.POST if request.method == 'POST' else None, prefix='lines')
    if request.method == 'POST':
        header_valid, lines_valid = form.is_valid(), formset.is_valid()
        if header_valid and lines_valid:
            try:
                key, catalog_at = _submission_key(request, kind, form.cleaned_data['token'])
                lines = [row.cleaned_data for row in formset.forms
                         if row.cleaned_data and not row.cleaned_data.get('DELETE')]
                for line in lines:
                    line['catalog_at'] = catalog_at
                command = service.create_purchase if is_purchase else service.create_waste
                record, created = command(actor=request.user, data=form.cleaned_data, lines=lines, submission_key=key)
            except ValidationError as error:
                _errors(form, error)
            except IntegrityError:
                form.add_error(None, 'ثبت هم‌زمان دیگری انجام شد؛ یک بار دیگر دکمهٔ ثبت را بزنید.')
            else:
                messages.success(request, 'سند ثبت شد.' if created else 'این سند قبلاً ثبت شده؛ ثبت تکراری انجام نشد.')
                if request.POST.get('submit') == 'another':
                    return redirect('procurement_purchase_add' if is_purchase else 'procurement_waste_add')
                return redirect('procurement_purchase_detail' if is_purchase else 'procurement_waste_detail', pk=record.pk)
    material_data = _material_data()
    return render(request, 'main/procurement/entry_form.html', {
        **_context(request, kind), 'kind': kind, 'form': form, 'formset': formset,
        'material_data': material_data, 'has_materials': bool(material_data),
    }, status=400 if request.method == 'POST' else 200)


@workspace_required(manager_read=True)
@require_GET
def ledger(request, kind):
    period = _period(request)
    model = PurchaseInvoice if kind == 'purchase' else WasteEntry
    rows = model.objects.filter(date__range=(period['start'], period['end']))
    amount_field = 'total' if kind == 'purchase' else 'estimated_total'
    days = rows.values('date').annotate(
        amount=Sum(amount_field, filter=Q(status='ACTIVE')),
        active_count=Count('pk', filter=Q(status='ACTIVE')),
        void_count=Count('pk', filter=Q(status='VOID')),
    ).order_by('-date')
    page = Paginator(days, 30).get_page(request.GET.get('page'))
    grouped = {day['date']: day for day in page.object_list}
    for day in grouped.values():
        day['amount'] = day['amount'] or 0
        day['records'] = []
    # Paginate whole days so one day's documents are never split across pages.
    for record in rows.filter(date__in=grouped).select_related('created_by').annotate(
            line_count=Count('lines')).order_by('-date', '-pk'):
        grouped[record.date]['records'].append(record)
    page.object_list = list(grouped.values())
    return render(request, 'main/procurement/ledger.html', {
        **_context(request, kind), 'kind': kind, 'period': period,
        'page': page,
    })


def _detail(request, kind, record, *, void_form=None, status=200):
    version = service.record_version(record)
    return render(request, 'main/procurement/detail.html', {
        **_context(request, kind), 'kind': kind, 'record': record,
        'lines': record.lines.select_related('purchase_line__invoice') if kind == 'waste' else record.lines.all(),
        'version': version, 'void_form': void_form or VoidForm(initial={'version': version}),
        'audits': ProcurementAudit.objects.filter(target_type=record._meta.model_name, target_id=record.pk).order_by('-pk'),
    }, status=status)


@workspace_required(manager_read=True)
@require_GET
def detail(request, kind, pk):
    model = PurchaseInvoice if kind == 'purchase' else WasteEntry
    return _detail(request, kind, get_object_or_404(model.objects.select_related('created_by', 'voided_by'), pk=pk))


@workspace_required
@require_POST
def void(request, kind, pk):
    model = PurchaseInvoice if kind == 'purchase' else WasteEntry
    record = get_object_or_404(model, pk=pk)
    form = VoidForm(request.POST)
    if form.is_valid():
        try:
            command = service.void_purchase if kind == 'purchase' else service.void_waste
            command(actor=request.user, pk=pk, expected_version=form.cleaned_data['version'], reason=form.cleaned_data['reason'])
        except ValidationError as error:
            _errors(form, error)
        else:
            messages.success(request, 'سند با حفظ سابقه باطل شد و از جمع گزارش‌ها کنار رفت.')
            return redirect('procurement_purchase_detail' if kind == 'purchase' else 'procurement_waste_detail', pk=pk)
    return _detail(request, kind, record, void_form=form, status=400)


@never_cache
@require_GET
def manager_report(request):
    if not request.user.is_authenticated:
        return redirect_to_login(request.get_full_path(), reverse('studio_login'))
    if not can_manage_studio(request.user):
        raise PermissionDenied
    period = _period(request)
    return render(request, 'main/procurement/report.html', {
        **studio_context(request, 'procurement', period), **_context(request, 'procurement'),
        'report': queries.report(period),
    })
