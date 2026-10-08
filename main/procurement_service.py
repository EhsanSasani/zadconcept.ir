"""Atomic purchasing and waste commands. Posted amounts are frozen snapshots."""
import hashlib
import json
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import UUID
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from .models import Material, ProcurementAudit, PurchaseInvoice, PurchaseLine, WasteEntry, WasteLine


def record_version(record):
    return hashlib.sha256(f'{record._meta.label}:{record.pk}:{record.updated_at.isoformat()}'.encode()).hexdigest()


def _author(actor):
    current = get_user_model().objects.select_for_update().filter(pk=getattr(actor, 'pk', None)).first()
    if current is None or not current.is_active or not current.has_perm('main.use_procurement_workspace'):
        raise PermissionDenied
    return current


def _text(value):
    return ' '.join(str(value or '').translate(str.maketrans({'ي': 'ی', 'ك': 'ک', '\u200c': ' '})).split())


def _number(value, *, places, label, positive=False, max_digits=15):
    try:
        result = Decimal(str(value))
        if not result.is_finite() or result < 0 or (positive and result == 0):
            raise InvalidOperation
        quantum = Decimal(1).scaleb(-places)
        if result.quantize(quantum) != result:
            raise InvalidOperation
        if result >= Decimal(10) ** (max_digits - places):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        raise ValidationError(f'{label} معتبر وارد کنید.')
    return result


def _date(value):
    if not isinstance(value, date) or isinstance(value, datetime):
        raise ValidationError('تاریخ معتبر وارد کنید.')
    if value > timezone.localdate(timezone=ZoneInfo('Asia/Tehran')):
        raise ValidationError('تاریخ نمی‌تواند در آینده باشد.')
    return value


def _key(value):
    try:
        return UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError('شناسهٔ ثبت معتبر نیست؛ صفحه را تازه کنید.')


def _snapshot(record):
    fields = ('name', 'base_unit', 'purchase_unit', 'units_per_purchase', 'default_unit_price', 'is_active') if isinstance(record, Material) else (
        'date', 'notes', 'status', 'created_by_id', 'void_reason', 'voided_at', 'voided_by_id')
    if isinstance(record, PurchaseInvoice):
        fields += ('supplier', 'reference', 'total')
    elif isinstance(record, WasteEntry):
        fields += ('reason', 'estimated_total')
    result = {field: getattr(record, field) for field in fields}
    if not isinstance(record, Material):
        result['lines'] = list(record.lines.values())
    return json.loads(json.dumps(result, default=str, ensure_ascii=False))


def _audit(actor, record, action, before):
    ProcurementAudit.objects.create(actor=actor, actor_name=(actor.get_full_name() or actor.get_username())[:150],
        target_type=record._meta.model_name, target_id=record.pk, action=action,
        before=before, after=_snapshot(record))


@transaction.atomic
def save_material(*, actor, data, pk=None, expected_version=None):
    author = _author(actor)
    current = Material.objects.select_for_update().get(pk=pk) if pk else Material()
    if pk and expected_version != record_version(current):
        raise ValidationError('این کالا تغییر کرده است؛ صفحه را تازه کنید.')
    before = _snapshot(current) if pk else {}
    name = _text(data.get('name')).casefold()
    if Material.objects.filter(name__iexact=name).exclude(pk=pk).exists():
        raise ValidationError('کالایی با این نام قبلاً ثبت شده است.')
    base_unit = _text(data.get('base_unit'))
    if pk and base_unit != current.base_unit and (current.purchaseline_lines.exists() or current.wasteline_lines.exists()):
        raise ValidationError('واحد پایهٔ کالای استفاده‌شده قابل تغییر نیست؛ کالای جدید تعریف کنید.')
    current.name = name
    current.base_unit = base_unit
    current.purchase_unit = _text(data.get('purchase_unit'))
    current.units_per_purchase = _number(data.get('units_per_purchase', 1), places=3, label='تعداد در واحد خرید', positive=True, max_digits=9)
    current.default_unit_price = _number(data.get('default_unit_price', 0), places=0, label='قیمت مرجع')
    current.is_active = bool(data.get('is_active', True))
    if current.base_unit == current.purchase_unit and current.units_per_purchase != 1:
        raise ValidationError('وقتی واحد پایه و خرید یکسان‌اند، ضریب تبدیل باید یک باشد.')
    current.full_clean()
    current.save()
    _audit(author, current, 'update' if pk else 'create', before)
    return current


def _materials(lines):
    if not isinstance(lines, (list, tuple)) or not 1 <= len(lines) <= 100:
        raise ValidationError('بین یک تا صد ردیف کالا وارد کنید.')
    identifiers = []
    for line in lines:
        try:
            value = line.get('material', line.get('material_id'))
            identifiers.append(int(getattr(value, 'pk', value)))
        except (TypeError, ValueError, AttributeError):
            raise ValidationError('کالای هر ردیف را انتخاب کنید.')
    materials = {item.pk: item for item in Material.objects.select_for_update().filter(pk__in=identifiers).order_by('pk')}
    if any(pk not in materials or not materials[pk].is_active for pk in identifiers):
        raise ValidationError('یکی از کالاها غیرفعال یا حذف شده است؛ صفحه را تازه کنید.')
    for line, pk in zip(lines, identifiers):
        material = materials[pk]
        expected_version = line.get('material_version')
        catalog_at = line.get('catalog_at')
        # JS can explicitly acknowledge a refreshed selection; the signed form
        # timestamp protects the same meaning for submissions without JS.
        if expected_version:
            changed = expected_version != record_version(material)
        elif catalog_at is not None:
            changed = (not isinstance(catalog_at, datetime) or not timezone.is_aware(catalog_at)
                       or material.updated_at > catalog_at)
        else:
            changed = False  # Internal commands can supply an already reviewed definition.
        if changed:
            raise ValidationError(f'تعریف کالای «{material.name}» تغییر کرده است؛ آن را دوباره انتخاب و واحد، تعداد و قیمت را بررسی کنید.')
    return [(line, materials[pk]) for line, pk in zip(lines, identifiers)]


def _line_values(line, material):
    mode = line.get('unit_mode', 'purchase')
    if mode not in ('base', 'purchase'):
        raise ValidationError('واحد ردیف را انتخاب کنید.')
    quantity = _number(line.get('quantity'), places=3, label='مقدار', positive=True, max_digits=12)
    supplied_factor = line.get('conversion_factor')
    factor = Decimal(1) if mode == 'base' else _number(
        material.units_per_purchase if supplied_factor in (None, '') else supplied_factor,
        places=3, label='ضریب تبدیل', positive=True, max_digits=9)
    if mode == 'purchase' and material.base_unit == material.purchase_unit and factor != 1:
        raise ValidationError('برای واحدهای یکسان، ضریب تبدیل باید یک باشد.')
    return dict(material=material, material_name=material.name, base_unit=material.base_unit,
        unit_label=material.base_unit if mode == 'base' else material.purchase_unit,
        unit_mode=mode, quantity=quantity, conversion_factor=factor, base_quantity=quantity * factor)


def _existing(model, key, actor):
    record = model.objects.filter(submission_key=key).first()
    if record and record.created_by_id != actor.pk:
        raise PermissionDenied
    return record


@transaction.atomic
def create_purchase(*, actor, data, lines, submission_key):
    author = _author(actor)
    key = _key(submission_key)
    previous = _existing(PurchaseInvoice, key, author)
    if previous:
        return previous, False
    materials = _materials(lines)
    invoice = PurchaseInvoice(date=_date(data.get('date')), supplier=_text(data.get('supplier')),
        reference=_text(data.get('reference')), notes=str(data.get('notes') or '').strip(), submission_key=key, created_by=author)
    invoice.full_clean()
    invoice.save()
    total = Decimal(0)
    for line, material in materials:
        values = _line_values(line, material)
        unit_price = _number(line.get('unit_price'), places=0, label='قیمت واحد')
        line_total = (values['quantity'] * unit_price).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        row = PurchaseLine(invoice=invoice, unit_price=unit_price, total=line_total, **values)
        row.full_clean()
        row.save()
        total += line_total
    invoice.total = total
    invoice.full_clean()
    invoice.save(update_fields=['total', 'updated_at'])
    _audit(author, invoice, 'create', {})
    return invoice, True


@transaction.atomic
def create_waste(*, actor, data, lines, submission_key):
    author = _author(actor)
    key = _key(submission_key)
    previous = _existing(WasteEntry, key, author)
    if previous:
        return previous, False
    materials = _materials(lines)
    entry = WasteEntry(date=_date(data.get('date')), reason=data.get('reason', WasteEntry.Reason.WILTED),
        notes=str(data.get('notes') or '').strip(), submission_key=key, created_by=author)
    entry.full_clean()
    entry.save()
    total = Decimal(0)
    for line, material in materials:
        values = _line_values(line, material)
        source = PurchaseLine.objects.filter(material=material, invoice__status='ACTIVE', invoice__date__lte=entry.date).order_by('-invoice__date', '-invoice_id', '-pk').first()
        raw_cost = source.unit_price / source.conversion_factor if source else material.default_unit_price / material.units_per_purchase
        unit_cost = raw_cost.quantize(Decimal('0.000001'), rounding=ROUND_HALF_UP)
        estimated_cost = (raw_cost * values['base_quantity']).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        row = WasteLine(entry=entry, unit_cost=unit_cost, estimated_cost=estimated_cost,
            cost_source='purchase' if source else 'reference', purchase_line=source, **values)
        row.full_clean()
        row.save()
        total += estimated_cost
    entry.estimated_total = total
    entry.full_clean()
    entry.save(update_fields=['estimated_total', 'updated_at'])
    _audit(author, entry, 'create', {})
    return entry, True


def _void(model, *, actor, pk, expected_version, reason):
    author = _author(actor)
    # All commands lock materials before documents, so costing and voiding agree.
    candidate = model.objects.get(pk=pk)
    ids = list(candidate.lines.values_list('material_id', flat=True))
    list(Material.objects.select_for_update().filter(pk__in=ids).order_by('pk'))
    current = model.objects.select_for_update().get(pk=pk)
    if current.status != 'ACTIVE' or record_version(current) != expected_version:
        raise ValidationError('این سند تغییر کرده یا باطل شده است؛ صفحه را تازه کنید.')
    reason = str(reason or '').strip()
    if not reason:
        raise ValidationError('دلیل ابطال را وارد کنید.')
    before = _snapshot(current)
    current.status = 'VOID'
    current.void_reason = reason
    current.voided_at = timezone.now()
    current.voided_by = author
    current.full_clean()
    current.save(update_fields=['status', 'void_reason', 'voided_at', 'voided_by', 'updated_at'])
    _audit(author, current, 'void', before)
    return current


@transaction.atomic
def void_purchase(*, actor, pk, expected_version, reason):
    return _void(PurchaseInvoice, actor=actor, pk=pk, expected_version=expected_version, reason=reason)


@transaction.atomic
def void_waste(*, actor, pk, expected_version, reason):
    return _void(WasteEntry, actor=actor, pk=pk, expected_version=expected_version, reason=reason)
