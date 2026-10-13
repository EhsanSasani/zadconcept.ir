from datetime import date
from decimal import Decimal
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from main.models import Material, MaterialDailyPrice, ProcurementAudit
from main.procurement_catalog import INITIAL_PRICES, PACKAGE_MATERIALS

class Command(BaseCommand):
    help = 'Install the explicitly supplied 2026-10-13 flower prices with a confirmed unit.'
    def add_arguments(self, parser):
        parser.add_argument('--date', required=True)
    @transaction.atomic
    def handle(self, *args, **options):
        try: day = date.fromisoformat(options['date'])
        except ValueError: raise CommandError('Use YYYY-MM-DD.')
        if day != date(2026, 10, 13): raise CommandError('This price list is approved only for 2026-10-13.')
        changed = 0
        for name, amount in INITIAL_PRICES:
            unit = 'بسته' if name in PACKAGE_MATERIALS else 'شاخه'
            material, created = Material.objects.get_or_create(name=name, defaults=dict(base_unit=unit, purchase_unit=unit, units_per_purchase=1, default_unit_price=0))
            if material.base_unit != unit: raise CommandError(f'Existing unit for {name} differs; no changes saved.')
            price, new = MaterialDailyPrice.objects.get_or_create(material=material, date=day, defaults=dict(price=Decimal(amount),base_unit=unit))
            if not new and (price.price != amount or price.base_unit != unit): raise CommandError(f'Existing daily price for {name} differs; no changes saved.')
            if new:
                ProcurementAudit.objects.create(actor_name='ثبت قیمت‌های اعلام‌شده زاد',target_type='materialdailyprice',target_id=price.pk,action='price',before={},after=dict(price=str(amount),base_unit=unit,date=day.isoformat(),source='user-approved-20261013'))
                changed += 1
        self.stdout.write(f'Created {changed} prices; {len(INITIAL_PRICES)} verified for {day.isoformat()}.')
