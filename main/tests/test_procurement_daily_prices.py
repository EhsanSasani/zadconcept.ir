from decimal import Decimal
from tempfile import TemporaryDirectory
from uuid import uuid4
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone
from django.core.exceptions import ValidationError
from main.models import Material, MaterialDailyPrice, PurchaseInvoice, WasteEntry
from main.procurement_service import create_waste, create_receipt
from main.tests.test_telegram_same_day import image_file
from main.persian_dates import format_persian_date
from django.core.management import call_command, CommandError
from main.procurement_catalog import SUPPLIERS

class DailyPricingTests(TestCase):
    def setUp(self):
        self.actor = get_user_model().objects.create_user('price-editor')
        self.actor.user_permissions.add(Permission.objects.get(codename='use_procurement_workspace'))
        self.material = Material.objects.create(name='رز', base_unit='شاخه', purchase_unit='بسته', units_per_purchase=10, default_unit_price=999999)
        self.today = timezone.localdate()
        self.client.force_login(self.actor)
        self.media = TemporaryDirectory()
        self.addCleanup(self.media.cleanup)
        settings = override_settings(MEDIA_ROOT=self.media.name)
        settings.enable()
        self.addCleanup(settings.disable)
    def waste(self, price=12000):
        return create_waste(actor=self.actor, data={'date':self.today,'reason':'wilted'}, lines=[{'material':self.material,'unit_mode':'base','quantity':3,'unit_price':price}], submission_key=uuid4())[0]
    def test_missing_or_invalid_manual_price_rolls_back_entire_entry(self):
        for price in [None, '', -1, 'NaN', '1.5', '1000000000000000']:
            with self.subTest(price=price), self.assertRaises(ValidationError): self.waste(price)
        self.assertFalse(WasteEntry.objects.exists())
    def test_manual_snapshot_ignores_daily_and_material_prices(self):
        MaterialDailyPrice.objects.create(material=self.material, date=self.today, price=999, base_unit='شاخه')
        entry=self.waste()
        self.assertEqual(entry.estimated_total,36000)
        row=entry.lines.get()
        self.assertIsNone(row.purchase_line)
        self.assertIsNone(row.daily_price)
        self.assertEqual(row.cost_source,'manual')
        self.assertEqual(row.manual_unit_price,12000)
        MaterialDailyPrice.objects.all().update(price=15000)
        entry.refresh_from_db()
        self.assertEqual(entry.estimated_total,36000)
        self.assertEqual(self.waste(15000).estimated_total,45000)
    def test_pack_price_snapshot_keeps_exact_entered_amount_and_rounds_final_total(self):
        entry, _ = create_waste(actor=self.actor, data={'date':self.today,'reason':'wilted'},
            lines=[{'material':self.material,'unit_mode':'purchase','conversion_factor':3,
                'quantity':'1.5','unit_price':101}], submission_key=uuid4())
        row=entry.lines.get()
        self.assertEqual(row.manual_unit_price,101)
        self.assertEqual(row.unit_cost,Decimal('33.666667'))
        self.assertEqual(entry.estimated_total,152)
        self.assertContains(self.client.get(reverse('procurement_waste_detail',args=[entry.pk])), 'قیمت واردشده هنگام ثبت')
    def test_legacy_waste_snapshot_remains_readable(self):
        entry=self.waste()
        source=MaterialDailyPrice.objects.create(material=self.material,date=self.today,price=12000,base_unit='شاخه')
        entry.lines.update(cost_source='daily',daily_price=source,manual_unit_price=None)
        response=self.client.get(reverse('procurement_waste_detail',args=[entry.pk]))
        self.assertEqual(response.status_code,200)
        entry.refresh_from_db()
        self.assertEqual(entry.estimated_total,36000)
    def test_purchase_form_and_list_need_no_material_lines(self):
        response=self.client.get(reverse('procurement_purchase_add'))
        self.assertEqual(set(response.context['form'].fields),{'token','date','supplier','total','image'})
        for supplier in SUPPLIERS:
            self.assertContains(response, supplier)
        data={'token':response.context['form']['token'].value(),'date':format_persian_date(self.today),'supplier':'تأمین‌کننده تست','total':'۲۵۰٬۰۰۰','image':image_file()}
        response=self.client.post(reverse('procurement_purchase_add'),data)
        self.assertEqual(response.status_code,302)
        invoice=PurchaseInvoice.objects.get()
        self.assertEqual(invoice.total,250000)
        self.assertEqual(invoice.lines.count(),0)
        self.assertTrue(invoice.image)
        self.assertEqual(self.client.get(reverse('procurement_purchase_detail',args=[invoice.pk])).status_code,200)
        self.assertContains(self.client.get(reverse('procurement_purchases')),'تأمین‌کننده تست')
    def test_receipt_retry_keeps_one_invoice(self):
        key=uuid4()
        data={'date':self.today,'supplier':'تست','total':100000,'image':image_file()}
        first,_=create_receipt(actor=self.actor,data=data,submission_key=key)
        second,created=create_receipt(actor=self.actor,data=data,submission_key=key)
        self.assertFalse(created)
        self.assertEqual(first.pk,second.pk)
    def test_daily_price_section_is_removed_and_waste_price_input_is_required(self):
        self.assertEqual(self.client.get('/procurement/prices/').status_code,404)
        for name in ['procurement_home','procurement_waste_add','procurement_purchases','procurement_materials']:
            response=self.client.get(reverse(name))
            self.assertNotContains(response,'قیمت‌های روز')
            self.assertNotContains(response,'/procurement/prices/')
        response=self.client.get(reverse('procurement_waste_add'))
        self.assertTrue(response.context['formset'].forms[0].fields['unit_price'].required)
        self.assertContains(response,'name="lines-0-unit_price"')

class InitialPriceInstallationTests(TestCase):
    def test_confirmed_units_prices_and_repeat_are_preserved(self):
        call_command('install_procurement_prices_20261013', date='2026-10-13')
        call_command('install_procurement_prices_20261013', date='2026-10-13')
        self.assertEqual(MaterialDailyPrice.objects.count(), 20)
        self.assertEqual(Material.objects.filter(base_unit='بسته').count(), 9)
        self.assertEqual(Material.objects.filter(base_unit='شاخه').count(), 11)
        self.assertEqual(MaterialDailyPrice.objects.get(material__name='میخک').price, 350000)
        self.assertEqual(MaterialDailyPrice.objects.get(material__name='آلسترومریا').price, 60000)

    def test_conflicting_price_rolls_back_other_new_records(self):
        material = Material.objects.create(name='تاج خروس', base_unit='بسته', purchase_unit='بسته', units_per_purchase=1)
        MaterialDailyPrice.objects.create(material=material, date='2026-10-13', price=1, base_unit='بسته')
        with self.assertRaises(CommandError):
            call_command('install_procurement_prices_20261013', date='2026-10-13')
        self.assertEqual(Material.objects.count(), 1)
        self.assertEqual(MaterialDailyPrice.objects.count(), 1)
