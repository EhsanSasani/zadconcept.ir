"""Business invariants for the 2026-10 panel information architecture changes."""
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.contrib.admin.models import LogEntry
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from main.account_roles import account_version
from main.account_service import save_technical_florist_link
from main.models import Florist, PurchaseInvoice, StudioProduct
from main.procurement_queries import report
from main.studio_access import get_active_florist
from main.studio_views import _chart, _period
from django.test import RequestFactory


class SupplierReportTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user('report-manager')
        self.user.user_permissions.add(Permission.objects.get(codename='view_studioproduct'))
        self.client.force_login(self.user)
        self.today = timezone.localdate()

    def receipt(self, supplier, total, **extra):
        return PurchaseInvoice.objects.create(date=extra.pop('date',self.today), supplier=supplier,
            total=total, created_by=self.user, submission_key=uuid4(), **extra)

    def test_supplier_typography_grouping_does_not_rewrite_history_or_merge_aliases(self):
        original = self.receipt('  گالري   ايده آل ', 100)
        self.receipt('گالری ایده\u200cآل',200)
        self.receipt('ایده آل',50)
        self.receipt('گالری ایده آل',900,status='VOID',voided_at=timezone.now(),void_reason='تکراری')
        self.receipt('گالری ایده آل',900,date=self.today-timedelta(days=1))
        data=report({'start':self.today,'end':self.today})
        self.assertEqual(data['purchase_total'],350)
        group=data['supplier_breakdown'][0]
        self.assertEqual((group['amount'],group['count']), (300,2))
        self.assertEqual(group['share'],Decimal('85.7'))
        self.assertEqual(len(group['variants']),2)
        original.refresh_from_db()
        self.assertEqual(original.supplier,'  گالري   ايده آل ')
        selected=report({'start':self.today,'end':self.today},supplier='گالری ایده آل')
        self.assertEqual(selected['purchase_total'],300)

    def test_totals_cover_every_page_and_supplier_filter_and_exclude_void(self):
        for _ in range(27): self.receipt('عالمی',100)
        self.receipt('دیگری',900)
        self.receipt('عالمی',9900,status='VOID',voided_at=timezone.now(),void_reason='باطل')
        response=self.client.get(reverse('studio_procurement'),{'supplier':'عالمی','invoice_page':2})
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.context['report']['purchase_total'],2700)
        self.assertEqual(len(response.context['invoice_page']),7)
        self.assertContains(response,'جمع خرید معتبر · تمام نتایج فیلترشده')
        self.assertNotContains(response,'کجا بیشتر هزینه می‌کنیم؟')
        response=self.client.get(reverse('procurement_purchases'),{'supplier':'عالمی','page':2})
        self.assertEqual(response.context['filtered_total'],2700)
        self.assertEqual(response.context['page'].paginator.count,28)


class TechnicalFloristLinkTests(TestCase):
    def setUp(self):
        User=get_user_model()
        self.technical=User.objects.create_superuser('technical-link-admin',password='private-test')
        self.target=User.objects.create_user('protected-account',is_staff=True)
        self.target.user_permissions.add(Permission.objects.get(codename='view_studioproduct'))
        self.manager=User.objects.create_user('operational-manager')
        self.manager.user_permissions.add(Permission.objects.get(codename='manage_studio_accounts'))

    def data(self, **changes):
        return dict(version=account_version(self.target),enabled=True,florist=None,**changes)

    def test_link_preserves_security_identity_and_writes_audit(self):
        before=(self.target.password,self.target.is_staff,self.target.is_superuser,list(self.target.user_permissions.values_list('pk',flat=True)))
        save_technical_florist_link(actor=self.technical,user_id=self.target.pk,data=self.data())
        self.target.refresh_from_db()
        self.assertIsNotNone(get_active_florist(self.target))
        self.assertEqual(before,(self.target.password,self.target.is_staff,self.target.is_superuser,list(self.target.user_permissions.values_list('pk',flat=True))))
        self.assertIn('technical_florist_link',LogEntry.objects.get().change_message)
        self.client.force_login(self.technical)
        self.assertEqual(self.client.get(reverse('studio_account_edit',args=[self.target.pk])).status_code,403)

    def test_operational_manager_cannot_use_service_or_direct_url(self):
        with self.assertRaises(PermissionDenied):
            save_technical_florist_link(actor=self.manager,user_id=self.target.pk,data=self.data())
        self.client.force_login(self.manager)
        url=reverse('studio_account_florist_link',args=[self.target.pk])
        self.assertEqual(self.client.get(url).status_code,403)
        self.assertEqual(self.client.post(url,{}).status_code,403)
        self.assertFalse(Florist.objects.exists())

    def test_stale_version_and_taken_profile_are_rejected(self):
        payload=self.data()
        self.target.first_name='Changed'
        self.target.save()
        with self.assertRaises(ValidationError):
            save_technical_florist_link(actor=self.technical,user_id=self.target.pk,data=payload)
        taken=Florist.objects.create(name='تولیدکننده',code='taken',user=self.manager)
        payload=self.data(); payload['florist']=taken
        with self.assertRaises(ValidationError):
            save_technical_florist_link(actor=self.technical,user_id=self.target.pk,data=payload)
        self.assertIsNone(get_active_florist(self.target))

    def test_detach_preserves_producer_and_product_history(self):
        florist=Florist.objects.create(name='سازنده',code='keep',user=self.target)
        product=StudioProduct.objects.create(florist=florist,image='history.jpg',price=100,
            production_type='DAILY',product_type='box',produced_at=timezone.now())
        payload=self.data(); payload['enabled']=False
        save_technical_florist_link(actor=self.technical,user_id=self.target.pk,data=payload)
        florist.refresh_from_db(); product.refresh_from_db()
        self.assertIsNone(florist.user_id)
        self.assertEqual(product.florist_id,florist.pk)


class ChartRangeTests(TestCase):
    def test_chart_covers_custom_range_and_keeps_first_day(self):
        today=timezone.localdate(); first=today-timedelta(days=59)
        request=RequestFactory().get('/',{'period':'custom','start':first.isoformat(),'end':today.isoformat()})
        period=_period(request)
        chart=_chart(StudioProduct.objects.none(),period)
        self.assertEqual(len(chart),60)
        self.assertEqual(chart[0]['label'],first.isoformat())
        self.assertEqual(chart[-1]['label'],today.isoformat())
