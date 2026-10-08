"""Read models for purchasing spend and estimated waste, never stock or profit."""
from decimal import Decimal

from django.db.models import Count, Sum

from .models import Material, PurchaseInvoice, PurchaseLine, WasteEntry, WasteLine


def summary(period):
    """Small dashboard projection including incomplete cost coverage."""
    bounds = (period['start'], period['end'])
    purchases = PurchaseInvoice.objects.filter(status='ACTIVE', date__range=bounds).aggregate(amount=Sum('total'), count=Count('pk'))
    wastes = WasteEntry.objects.filter(status='ACTIVE', date__range=bounds).aggregate(amount=Sum('estimated_total'), count=Count('pk'))
    unpriced_count = WasteLine.objects.filter(entry__status='ACTIVE', entry__date__range=bounds,
        cost_source='reference', unit_cost=0).count() if wastes['count'] else 0
    return dict(purchase_total=purchases['amount'] or Decimal(0), invoice_count=purchases['count'],
                waste_estimated_total=wastes['amount'] or Decimal(0), waste_count=wastes['count'],
                unpriced_count=unpriced_count)


def report(period):
    start, end = period['start'], period['end']
    invoices = PurchaseInvoice.objects.filter(status='ACTIVE', date__range=(start, end))
    wastes = WasteEntry.objects.filter(status='ACTIVE', date__range=(start, end))
    purchased = PurchaseLine.objects.filter(invoice__in=invoices)
    wasted = WasteLine.objects.filter(entry__in=wastes)
    zero = Decimal(0)
    purchase_totals = invoices.aggregate(total=Sum('total'), count=Count('pk'))
    waste_totals = wastes.aggregate(total=Sum('estimated_total'), count=Count('pk'))
    materials = {}
    def material_row(row):
        key = (row['material_id'], row['base_unit'])
        if key not in materials:
            materials[key] = dict(material_id=row['material_id'], name=row['material__name'], base_unit=row['base_unit'],
                purchased_quantity=zero, purchase_total=zero, waste_quantity=zero, waste_estimated_total=zero)
        return materials[key]
    for row in purchased.values('material_id', 'material__name', 'base_unit').annotate(quantity=Sum('base_quantity'), amount=Sum('total')).order_by():
        item = material_row(row)
        item['purchased_quantity'] += row['quantity']
        item['purchase_total'] += row['amount']
    for row in wasted.values('material_id', 'material__name', 'base_unit').annotate(quantity=Sum('base_quantity'), amount=Sum('estimated_cost')).order_by():
        item = material_row(row)
        item['waste_quantity'] += row['quantity']
        item['waste_estimated_total'] += row['amount']
    days = {}
    for rows, amount_key in ((invoices.values('date').annotate(amount=Sum('total')).order_by('date'), 'purchase_total'),
                            (wastes.values('date').annotate(amount=Sum('estimated_total')).order_by('date'), 'waste_estimated_total')):
        for row in rows:
            days.setdefault(row['date'], dict(date=row['date'], purchase_total=zero, waste_estimated_total=zero))[amount_key] = row['amount']
    return dict(invoice_count=purchase_totals['count'], purchase_total=purchase_totals['total'] or zero,
        waste_count=waste_totals['count'], waste_estimated_total=waste_totals['total'] or zero,
        reference_cost_count=wasted.filter(cost_source='reference').count(),
        unpriced_count=wasted.filter(cost_source='reference', unit_cost=0).count(),
        active_material_count=Material.objects.filter(is_active=True).count(),
        material_breakdown=sorted(materials.values(), key=lambda row: (-row['waste_estimated_total'], -row['purchase_total'], row['name'])),
        day_breakdown=[days[day] for day in sorted(days)], invoices=invoices, wastes=wastes)
