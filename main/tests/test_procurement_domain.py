from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from main.models import Material, ProcurementAudit, PurchaseInvoice, PurchaseLine, WasteEntry, WasteLine
from main.procurement_queries import report, summary
from main.procurement_service import (create_purchase, create_waste, record_version,
                                      save_material, void_purchase, void_waste)


class ProcurementDomainTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.actor = get_user_model().objects.create_user('buyer')
        cls.permission = Permission.objects.get(codename='use_procurement_workspace')
        cls.actor.user_permissions.add(cls.permission)
        cls.material = Material.objects.create(name='رز', base_unit='شاخه', purchase_unit='بسته',
            units_per_purchase=10, default_unit_price=100000)
        cls.today = timezone.localdate()

    def purchase(self, **kwargs):
        arguments = dict(actor=self.actor, data={'date': self.today, 'supplier': 'گلستان'},
            lines=[{'material': self.material, 'unit_mode': 'purchase', 'quantity': Decimal('2'), 'unit_price': Decimal('100000')}],
            submission_key=uuid4())
        arguments.update(kwargs)
        return create_purchase(**arguments)[0]

    def waste(self, **kwargs):
        arguments = dict(actor=self.actor, data={'date': self.today, 'reason': 'wilted'},
            lines=[{'material': self.material, 'unit_mode': 'base', 'quantity': Decimal('3')}], submission_key=uuid4())
        arguments.update(kwargs)
        return create_waste(**arguments)[0]

    def material_data(self, **kwargs):
        data = dict(name='رز', base_unit='شاخه', purchase_unit='بسته', units_per_purchase=10, default_unit_price=100000, is_active=True)
        data.update(kwargs)
        return data

    def test_purchase_snapshots_variable_pack_and_rounded_line_totals(self):
        invoice = self.purchase(lines=[dict(material=self.material, unit_mode='purchase', quantity=Decimal('1.5'),
                                            conversion_factor=20, unit_price=100001)])
        row = invoice.lines.get()
        self.assertEqual(row.base_quantity, 30)
        self.assertEqual(row.unit_label, 'بسته')
        self.assertEqual(row.total, 150002)
        self.assertEqual(invoice.total, 150002)
        self.assertEqual(invoice.total_amount, 150002)
        self.material.refresh_from_db()
        self.assertEqual(self.material.units_per_purchase, 10)

    def test_base_unit_purchase_always_has_one_conversion(self):
        invoice = self.purchase(lines=[dict(material=self.material, unit_mode='base', quantity=4, conversion_factor=20, unit_price=10000)])
        self.assertEqual(invoice.lines.get().base_quantity, 4)
        self.assertEqual(invoice.total, 40000)

    def test_waste_cost_uses_latest_eligible_purchase_and_its_conversion(self):
        self.purchase(data={'date': self.today - timedelta(days=2)}, lines=[dict(material=self.material, quantity=1, conversion_factor=10, unit_price=100000)])
        newest = self.purchase(data={'date': self.today - timedelta(days=1)}, lines=[dict(material=self.material, quantity=1, conversion_factor=20, unit_price=300000)])
        self.purchase(lines=[dict(material=self.material, quantity=1, conversion_factor=10, unit_price=900000)])
        entry = self.waste(data={'date': self.today - timedelta(days=1), 'reason': 'damaged'})
        row = entry.lines.get()
        self.assertEqual(row.purchase_line.invoice, newest)
        self.assertEqual(row.unit_cost, 15000)
        self.assertEqual(row.estimated_cost, 45000)
        self.assertEqual(entry.estimated_total, 45000)

    def test_fallback_reference_cost_is_explicit(self):
        row = self.waste().lines.get()
        self.assertEqual(row.cost_source, 'reference')
        self.assertIsNone(row.purchase_line)
        self.assertEqual(row.estimated_cost, 30000)

    def test_waste_purchase_mode_uses_its_variable_ratio(self):
        row = self.waste(lines=[dict(material=self.material, unit_mode='purchase', quantity='0.5', conversion_factor=20)]).lines.get()
        self.assertEqual(row.base_quantity, 10)
        self.assertEqual(row.estimated_cost, 100000)

    def test_void_purchase_is_excluded_from_future_costing_and_reports(self):
        purchase = self.purchase()
        old_waste = self.waste()
        void_purchase(actor=self.actor, pk=purchase.pk, expected_version=record_version(purchase), reason='فاکتور تکراری')
        new_waste = self.waste()
        self.assertEqual(new_waste.lines.get().cost_source, 'reference')
        old_waste.refresh_from_db()
        self.assertEqual(old_waste.lines.get().cost_source, 'purchase')
        self.assertEqual(old_waste.estimated_total, 30000)
        self.assertEqual(report({'start': self.today, 'end': self.today})['purchase_total'], 0)

    def test_material_edits_preserve_old_names_units_and_costs(self):
        invoice = self.purchase()
        entry = self.waste()
        save_material(actor=self.actor, pk=self.material.pk, expected_version=record_version(self.material),
            data=self.material_data(name='رز هلندی', purchase_unit='دسته', units_per_purchase=20, default_unit_price=400000))
        self.assertEqual(invoice.lines.get().material_name, 'رز')
        self.assertEqual(invoice.lines.get().unit_label, 'بسته')
        self.assertEqual(entry.lines.get().unit_cost, 10000)

    def test_used_base_unit_cannot_change(self):
        self.purchase()
        with self.assertRaises(ValidationError):
            save_material(actor=self.actor, pk=self.material.pk, expected_version=record_version(self.material), data=self.material_data(base_unit='کیلو'))

    def test_material_update_version_required_and_stale_rejected(self):
        version = record_version(self.material)
        save_material(actor=self.actor, pk=self.material.pk, expected_version=version, data=self.material_data(name='رز جدید'))
        with self.assertRaises(ValidationError):
            save_material(actor=self.actor, pk=self.material.pk, expected_version=version, data=self.material_data())

    def test_material_normalizes_arabic_letters_spaces_and_duplicate_names(self):
        value = save_material(actor=self.actor, data=self.material_data(name='  ياس   سفيد  '))
        self.assertEqual(value.name, 'یاس سفید')
        with self.assertRaises(ValidationError):
            save_material(actor=self.actor, data=self.material_data(name='یاس سفید'))

    def test_equal_units_require_one_conversion(self):
        with self.assertRaises(ValidationError):
            save_material(actor=self.actor, data=self.material_data(name='لاله', purchase_unit='شاخه'))

    def test_archived_material_rejects_new_purchase_and_waste(self):
        save_material(actor=self.actor, pk=self.material.pk, expected_version=record_version(self.material), data=self.material_data(is_active=False))
        with self.assertRaises(ValidationError):
            self.purchase()
        with self.assertRaises(ValidationError):
            self.waste()

    def test_idempotency_is_actor_bound_and_does_not_create_second_audit(self):
        key = uuid4()
        record = self.purchase(submission_key=key)
        retried, created = create_purchase(actor=self.actor, data={}, lines=[], submission_key=key)
        self.assertEqual(retried.pk, record.pk)
        self.assertFalse(created)
        self.assertEqual(PurchaseInvoice.objects.count(), 1)
        self.assertEqual(ProcurementAudit.objects.filter(target_type='purchaseinvoice').count(), 1)
        other = get_user_model().objects.create_user('other_buyer')
        other.user_permissions.add(self.permission)
        with self.assertRaises(PermissionDenied):
            self.purchase(actor=other, submission_key=key)

    def test_waste_idempotency(self):
        key = uuid4()
        record = self.waste(submission_key=key)
        retried, created = create_waste(actor=self.actor, data={}, lines=[], submission_key=key)
        self.assertEqual(record.pk, retried.pk)
        self.assertFalse(created)
        self.assertEqual(WasteLine.objects.count(), 1)

    def test_permission_is_rechecked_after_cached_grant_is_revoked(self):
        self.assertTrue(self.actor.has_perm('main.use_procurement_workspace'))
        self.actor.user_permissions.remove(self.permission)
        for operation in (lambda: self.purchase(), lambda: self.waste(), lambda: save_material(actor=self.actor, data=self.material_data(name='میخک'))):
            with self.assertRaises(PermissionDenied):
                operation()

    def test_inactive_actor_rejected(self):
        get_user_model().objects.filter(pk=self.actor.pk).update(is_active=False)
        with self.assertRaises(PermissionDenied):
            self.purchase()

    def test_invalid_lines_roll_back_entire_document(self):
        with self.assertRaises(ValidationError):
            self.purchase(lines=[dict(material=self.material, quantity=1, unit_price=100), dict(material=self.material, quantity=-1, unit_price=100)])
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(PurchaseLine.objects.exists())
        self.assertFalse(ProcurementAudit.objects.exists())

    def test_zero_negative_fractional_money_and_overflow_rejected(self):
        invalid = [dict(quantity=0), dict(quantity=-1), dict(quantity='0.0001'), dict(unit_price='1.1'),
                   dict(conversion_factor=0), dict(unit_price='NaN'), dict(quantity='1000000000'), dict(unit_price='1000000000000000')]
        for extra in invalid:
            with self.subTest(extra=extra), self.assertRaises(ValidationError):
                self.purchase(lines=[dict(material=self.material, quantity=1, unit_price=100, **{k:v for k,v in extra.items() if k not in ('quantity','unit_price')}) | extra])

    def test_document_total_overflow_rejected_cleanly(self):
        with self.assertRaises(ValidationError):
            self.purchase(lines=[dict(material=self.material, quantity='999999999.999', unit_price='999999999999999')])

    def test_future_date_rejected(self):
        for method in (self.purchase, self.waste):
            with self.assertRaises(ValidationError):
                method(data={'date': self.today + timedelta(days=1)})

    def test_void_requires_reason_and_fresh_version(self):
        invoice = self.purchase()
        for version, reason in ((record_version(invoice), ''), ('stale', 'اشتباه')):
            with self.assertRaises(ValidationError):
                void_purchase(actor=self.actor, pk=invoice.pk, expected_version=version, reason=reason)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, 'ACTIVE')

    def test_void_records_actor_reason_audit_and_excludes_waste(self):
        entry = self.waste()
        old_version = record_version(entry)
        void_waste(actor=self.actor, pk=entry.pk, expected_version=old_version, reason='ثبت تکراری')
        entry.refresh_from_db()
        self.assertEqual(entry.status, 'VOID')
        self.assertEqual(entry.voided_by, self.actor)
        self.assertEqual(entry.void_reason, 'ثبت تکراری')
        audit = ProcurementAudit.objects.get(target_type='wasteentry', action='void')
        self.assertEqual(audit.before['status'], 'ACTIVE')
        self.assertEqual(audit.after['status'], 'VOID')
        self.assertEqual(audit.after['lines'][0]['material_name'], 'رز')
        self.assertEqual(report({'start': self.today, 'end': self.today})['waste_estimated_total'], 0)
        with self.assertRaises(ValidationError):
            void_waste(actor=self.actor, pk=entry.pk, expected_version=old_version, reason='تکرار ابطال')

    def test_report_boundary_material_and_day_totals(self):
        self.purchase(data={'date': self.today - timedelta(days=1)})
        self.purchase()
        self.waste()
        result = report({'start': self.today, 'end': self.today})
        self.assertEqual(result['invoice_count'], 1)
        self.assertEqual(result['purchase_total'], 200000)
        self.assertEqual(result['waste_count'], 1)
        self.assertEqual(result['waste_estimated_total'], 30000)
        row = result['material_breakdown'][0]
        self.assertEqual(row['purchased_quantity'], 20)
        self.assertEqual(row['waste_quantity'], 3)
        self.assertEqual(row['purchase_total'], 200000)
        self.assertEqual(result['day_breakdown'][0]['date'], self.today)

    def test_report_unknown_reference_cost_is_counted(self):
        Material.objects.filter(pk=self.material.pk).update(default_unit_price=0)
        self.waste()
        result = report({'start': self.today, 'end': self.today})
        self.assertEqual(result['unpriced_count'], 1)
        self.assertEqual(result['reference_cost_count'], 1)

    def test_database_checks_reject_invalid_quantities_and_voids(self):
        invoice = self.purchase()
        with self.assertRaises(IntegrityError), transaction.atomic():
            invoice.lines.update(quantity=0)
        with self.assertRaises(IntegrityError), transaction.atomic():
            PurchaseInvoice.objects.filter(pk=invoice.pk).update(status='VOID')

    def test_database_protects_material_and_financial_links(self):
        from django.db.models.deletion import ProtectedError
        invoice = self.purchase()
        self.waste()
        with self.assertRaises(ProtectedError):
            self.material.delete()
        with self.assertRaises(ProtectedError):
            invoice.delete()

    def test_deleted_creator_does_not_prevent_audited_correction(self):
        original = get_user_model().objects.create_user('former_buyer')
        original.user_permissions.add(self.permission)
        invoice = self.purchase(actor=original)
        original.delete()
        invoice.refresh_from_db()
        self.assertIsNone(invoice.created_by)
        voided = void_purchase(actor=self.actor, pk=invoice.pk, expected_version=record_version(invoice), reason='اصلاح ثبت قدیمی')
        self.assertEqual(voided.status, 'VOID')
        self.assertEqual(ProcurementAudit.objects.get(target_type='purchaseinvoice', action='create').actor_name, 'former_buyer')

    def test_fractional_base_cost_rounds_only_final_amount(self):
        self.purchase(lines=[dict(material=self.material, quantity=1, conversion_factor=3, unit_price=100)])
        entry = self.waste(lines=[dict(material=self.material, unit_mode='base', quantity=3)])
        self.assertEqual(entry.lines.get().unit_cost, Decimal('33.333333'))
        self.assertEqual(entry.estimated_total, 100)

    def test_small_conversion_large_unit_cost_is_supported(self):
        self.purchase(lines=[dict(material=self.material, quantity='0.001', conversion_factor='0.001', unit_price='999999999999999')])
        entry = self.waste(lines=[dict(material=self.material, unit_mode='base', quantity='0.001')])
        self.assertEqual(entry.estimated_total, Decimal('999999999999999'))

    def test_stale_material_version_rejects_purchase_and_waste_atomically(self):
        previous_version = record_version(self.material)
        save_material(actor=self.actor, pk=self.material.pk, expected_version=previous_version,
            data=self.material_data(purchase_unit='دسته', units_per_purchase=20))
        for method in (self.purchase, self.waste):
            with self.subTest(method=method.__name__), self.assertRaises(ValidationError):
                method(lines=[dict(material=self.material, material_version=previous_version,
                    quantity=2, unit_price=100000)])
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(WasteEntry.objects.exists())
        self.assertFalse(ProcurementAudit.objects.exclude(target_type='material').exists())

    def test_fresh_material_version_accepts_reviewed_definition(self):
        current = save_material(actor=self.actor, pk=self.material.pk, expected_version=record_version(self.material),
            data=self.material_data(purchase_unit='دسته', units_per_purchase=20))
        # A newly selected material overrides the original form catalog time.
        invoice = self.purchase(lines=[dict(material=current, material_version=record_version(current),
            catalog_at=current.updated_at - timedelta(days=1), quantity=2, unit_price=100000)])
        self.assertEqual(invoice.lines.get().base_quantity, 40)
        self.assertEqual(invoice.lines.get().unit_label, 'دسته')

    def test_catalog_timestamp_fallback_rejects_changed_definition_without_js(self):
        catalog_at = self.material.updated_at
        save_material(actor=self.actor, pk=self.material.pk, expected_version=record_version(self.material),
            data=self.material_data(units_per_purchase=20))
        for method in (self.purchase, self.waste):
            with self.subTest(method=method.__name__), self.assertRaises(ValidationError):
                method(lines=[dict(material=self.material, catalog_at=catalog_at, quantity=2, unit_price=100000)])
        self.assertFalse(PurchaseInvoice.objects.exists())
        self.assertFalse(WasteEntry.objects.exists())

    def test_catalog_timestamp_fallback_accepts_unchanged_definition(self):
        invoice = self.purchase(lines=[dict(material=self.material, catalog_at=self.material.updated_at,
            quantity=2, unit_price=100000)])
        self.assertEqual(invoice.lines.get().base_quantity, 20)

    def test_summary_counts_unpriced_rows_only_in_active_in_period_documents(self):
        Material.objects.filter(pk=self.material.pk).update(default_unit_price=0)
        self.waste(data={'date': self.today - timedelta(days=1)})
        self.waste()
        voided = self.waste()
        void_waste(actor=self.actor, pk=voided.pk, expected_version=record_version(voided), reason='ثبت تکراری')
        result = summary({'start': self.today, 'end': self.today})
        self.assertEqual(result['unpriced_count'], 1)
        self.assertEqual(result['waste_count'], 1)
        self.assertEqual(result['waste_estimated_total'], 0)
