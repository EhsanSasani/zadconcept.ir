"""Sales corrections preserve publication identity and accountable history."""
import tempfile
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Permission
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone

from main.models import Category, Florist, Product, StudioDelivery, StudioProduct, StudioSalesAudit, TelegramSameDayPost
from main.sales_service import apply_sales_action, version
from main.studio_access import can_manage_studio, can_use_sales
from main.studio_delivery import process_next_delivery
from main.studio_publishing import create_portal_record
from main.studio_transport import TelegramDeliveryError
from .test_telegram_same_day import image_file


@override_settings(STUDIO_ADMIN_NOTIFICATIONS_ENABLED=False,
    TELEGRAM_SAME_DAY_GROUP_ID='-5595039112', TELEGRAM_STUDIO_CUSTOM_GROUP_ID='-5182713369',
    TELEGRAM_CHANNEL_ID='', TELEGRAM_DISCUSSION_GROUP_ID='',
    PASSWORD_HASHERS=['django.contrib.auth.hashers.MD5PasswordHasher'])
class SalesWorkspaceTests(TestCase):
    def setUp(self):
        media = tempfile.TemporaryDirectory()
        self.addCleanup(media.cleanup)
        category = Category.objects.create(name='گل', slug='sales-test', section='flowers')
        config = override_settings(MEDIA_ROOT=media.name, TELEGRAM_SAME_DAY_CATEGORY_ID=str(category.pk))
        config.enable()
        self.addCleanup(config.disable)
        self.actor = get_user_model().objects.create_user('sales-only')
        self.actor.user_permissions.add(Permission.objects.get(codename='use_sales_workspace'))
        self.maker = get_user_model().objects.create_user('sales-maker')
        self.florist = Florist.objects.create(name='فلوریست', code='sales', user=self.maker)
        self.send = self.mock('main.studio_transport.send_photo', side_effect=self.message)
        self.edit = self.mock('main.studio_transport.edit_photo', return_value=True)
        self.delete = self.mock('main.studio_transport.delete_message', return_value=True)
        self.sequence = 800

    def mock(self, target, **kwargs):
        mocker = patch(target, **kwargs)
        self.addCleanup(mocker.stop)
        return mocker.start()

    def message(self, chat_id, *_):
        self.sequence += 1
        return {'message_id': self.sequence, 'chat': {'id': chat_id, 'type': 'group'},
                'date': int(timezone.now().timestamp()), 'from': {'id': 99, 'is_bot': True},
                'photo': [{'file_id': 'mock-photo', 'width': 100, 'height': 100}]}

    def create(self, production='DAILY', publish=True):
        record, _ = create_portal_record(user=self.maker, florist=self.florist, image=image_file(),
            factor_code='S-' + uuid.uuid4().hex[:12].upper(), product_type='box',
            production_type=production, price=2500000, submission_key=uuid.uuid4())
        if publish:
            self.assertEqual(process_next_delivery().status, StudioDelivery.Status.SENT)
        record.refresh_from_db()
        return record

    def act(self, record, action, **kwargs):
        record.refresh_from_db()
        return apply_sales_action(pk=record.pk, actor=self.actor, expected_version=version(record),
                                  action=action, reason='اصلاح درخواست مشتری', **kwargs)

    def test_sales_permission_does_not_grant_manager_and_unauthorized_action_fails(self):
        self.assertTrue(can_use_sales(self.actor))
        self.assertFalse(can_manage_studio(self.actor))
        record = self.create()
        with self.assertRaises(PermissionDenied):
            apply_sales_action(pk=record.pk, actor=self.maker, expected_version=version(record),
                               action='sell', reason='test')
        self.assertFalse(StudioSalesAudit.objects.exists())

    def test_stale_version_cannot_overwrite_new_sale(self):
        record = self.create()
        old = version(record)
        self.act(record, 'sell')
        with self.assertRaises(ValidationError):
            apply_sales_action(pk=record.pk, actor=self.actor, expected_version=old,
                               action='withdraw', reason='stale')
        record.refresh_from_db()
        self.assertEqual(record.status, 'SOLD')
        self.assertEqual(record.sales_audits.count(), 1)

    def test_blank_reason_rolls_back(self):
        record = self.create()
        with self.assertRaises(ValidationError):
            apply_sales_action(pk=record.pk, actor=self.actor, expected_version=version(record),
                               action='sell', reason='  ')
        record.refresh_from_db()
        self.assertEqual(record.status, 'AVAILABLE')
        self.assertFalse(record.sales_audits.exists())

    def test_restore_during_grace_keeps_message_and_cancels_retirement(self):
        record = self.create()
        original = record.telegram_message_id
        self.act(record, 'sell')
        self.act(record, 'restore')
        record.refresh_from_db()
        record.product.refresh_from_db()
        self.assertEqual(record.status, 'AVAILABLE')
        self.assertEqual(record.product.status, Product.Status.AVAILABLE)
        self.assertIsNone(record.sold_at)
        self.assertEqual(record.telegram_message_id, original)
        retirement = record.deliveries.get(action='RETIRE')
        self.assertEqual((retirement.status, retirement.outcome), ('SENT', 'restored'))
        job = record.deliveries.get(action='SYNC')
        self.assertEqual((job.status, job.message_id), ('PENDING', original))
        self.assertEqual(process_next_delivery().status, 'SENT')
        self.edit.assert_called_once()
        self.assertEqual(self.send.call_count, 1)
        self.delete.assert_not_called()

    def test_restore_after_deleted_message_tombstones_and_republishes_once(self):
        record = self.create()
        original = record.telegram_message_id
        self.act(record, 'sell')
        StudioProduct.objects.filter(pk=record.pk).update(sold_at=timezone.now()-timedelta(minutes=46))
        record.deliveries.filter(action='RETIRE').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(process_next_delivery().outcome, 'deleted')
        self.act(record, 'restore')
        record.refresh_from_db()
        self.assertIsNone(record.telegram_message_id)
        old = TelegramSameDayPost.objects.get(telegram_message_id=original, telegram_chat_id=-5595039112)
        self.assertIsNone(old.product_id)
        self.assertIsNotNone(old.deleted_at)
        self.assertEqual(record.deliveries.get(action='PUBLISH').status, 'PENDING')
        self.assertEqual(process_next_delivery().status, 'SENT')
        record.refresh_from_db()
        self.assertNotEqual(record.telegram_message_id, original)
        self.assertIsNone(process_next_delivery())
        self.assertEqual(self.send.call_count, 2)

    def test_custom_cannot_restore_and_keeps_message(self):
        record = self.create('CUSTOM')
        original = record.telegram_message_id
        with self.assertRaises(ValidationError):
            self.act(record, 'restore')
        record.refresh_from_db()
        self.assertEqual(record.status, 'SOLD')
        self.assertEqual(record.telegram_message_id, original)
        self.assertFalse(record.deliveries.filter(action='RETIRE').exists())
        self.assertFalse(record.sales_audits.exists())

    def test_audit_preserves_original_sale_and_resale_uses_new_date(self):
        record = self.create()
        first_sale = timezone.now()-timedelta(days=1)
        with patch('main.sales_service.timezone.now', return_value=first_sale):
            self.act(record, 'sell')
        self.act(record, 'restore')
        restore = record.sales_audits.get(action='restore')
        self.assertEqual(restore.before['sold_at'], str(first_sale))
        self.assertEqual(restore.after['sold_at'], '')
        self.assertEqual(restore.actor, self.actor)
        self.assertEqual(restore.actor_name, self.actor.username)
        self.assertEqual(restore.reason, 'اصلاح درخواست مشتری')
        self.act(record, 'sell')
        record.refresh_from_db()
        self.assertGreater(record.sold_at, first_sale)
        self.assertEqual(record.sales_audits.filter(action='sell').count(), 2)
        retirement = record.deliveries.get(action='RETIRE')
        self.assertEqual(retirement.status, 'RETRY')
        self.assertEqual(retirement.next_attempt_at, record.sold_at+timedelta(minutes=45))

    def test_withdraw_restore_clears_withdrawal_date(self):
        record = self.create()
        self.act(record, 'withdraw')
        self.act(record, 'restore')
        record.refresh_from_db()
        self.assertIsNone(record.withdrawn_at)
        self.assertEqual(record.sales_audits.get(action='restore').before['status'], 'WITHDRAWN')

    def test_edit_updates_projection_and_queues_media_sync(self):
        record = self.create()
        florist = Florist.objects.create(name='دوم', code='second')
        self.act(record, 'edit', values={'factor_code':'S-UPDATED', 'florist':florist,
            'product_type':'jar', 'price':3200000, 'image':image_file(), 'notes':'اصلاح'})
        record.refresh_from_db()
        record.product.refresh_from_db()
        self.assertEqual(record.florist_id, florist.pk)
        self.assertEqual(record.product.price, 3200000)
        self.assertEqual(record.product.cover_image.name, record.image.name)
        audit = record.sales_audits.get()
        self.assertEqual(audit.before['price'], '2500000')
        self.assertEqual(audit.after['factor_code'], 'S-UPDATED')
        self.assertEqual(process_next_delivery().outcome, 'updated')
        self.assertIn('S-UPDATED', self.edit.call_args.args[3])
        self.assertIn('3,200,000', self.edit.call_args.args[3])

    def test_sending_or_uncertain_jobs_block_corrections(self):
        record = self.create()
        for status in ('SENDING', 'UNCERTAIN'):
            with self.subTest(status=status):
                record.deliveries.filter(action='PUBLISH').update(status=status)
                with self.assertRaises(ValidationError):
                    self.act(record, 'edit', values={'price':4000000})
                record.refresh_from_db()
                self.assertEqual(record.price, 2500000)
                self.assertFalse(record.sales_audits.exists())

    def test_sync_confirmed_absence_requeues_available_daily_only(self):
        record = self.create()
        original = record.telegram_message_id
        self.act(record, 'edit', values={'price':3200000})
        self.edit.side_effect = TelegramDeliveryError('message_not_found')
        self.assertEqual(process_next_delivery().outcome, 'already_absent')
        record.refresh_from_db()
        self.assertIsNone(record.telegram_message_id)
        self.assertEqual(record.deliveries.get(action='PUBLISH').status, 'PENDING')
        old = TelegramSameDayPost.objects.get(telegram_chat_id=-5595039112, telegram_message_id=original)
        self.assertIsNotNone(old.deleted_at)
        self.assertIsNone(old.product_id)

    def test_sync_transport_failure_does_not_duplicate_publication(self):
        record = self.create()
        original = record.telegram_message_id
        self.act(record, 'edit', values={'price':3200000})
        self.edit.side_effect = TelegramDeliveryError('transport_unavailable', retryable=True)
        self.assertEqual(process_next_delivery().status, 'RETRY')
        record.refresh_from_db()
        self.assertEqual(record.telegram_message_id, original)
        self.assertEqual(record.deliveries.get(action='PUBLISH').status, 'SENT')
        self.assertEqual(self.send.call_count, 1)

    def test_failed_edit_keeps_original_photo_and_projection(self):
        record = self.create()
        image_name, storage = record.image.name, record.image.storage
        with self.assertRaises(ValidationError):
            self.act(record, 'edit', values={'price':-1, 'image':image_file()})
        record.refresh_from_db()
        record.product.refresh_from_db()
        self.assertEqual(record.image.name, image_name)
        self.assertTrue(storage.exists(image_name))
        self.assertEqual(record.product.price, 2500000)
        self.assertFalse(record.sales_audits.exists())

    def test_missing_custom_message_never_creates_duplicate_publication(self):
        record = self.create('CUSTOM')
        self.act(record, 'edit', values={'price':3200000})
        self.edit.side_effect = TelegramDeliveryError('message_not_found')
        self.assertEqual(process_next_delivery().outcome, 'already_absent')
        self.assertEqual(record.deliveries.get(action='PUBLISH').status, 'SENT')
        self.assertEqual(self.send.call_count, 1)
        self.assertIsNone(process_next_delivery())

    def test_type_correction_cannot_escalate_status_or_forge_message_identity(self):
        record = self.create()
        self.act(record, 'edit', values={'status':'DELETED', 'production_type':'CUSTOM',
            'telegram_message_id':12345, 'price':3200000})
        record.refresh_from_db()
        self.assertEqual(record.status, 'AVAILABLE')
        self.assertEqual(record.production_type, 'CUSTOM')
        self.assertNotEqual(record.telegram_message_id, 12345)

    def test_routes_render_for_sales_and_deny_unrelated_user(self):
        record = self.create()
        paths = ['/sales/', '/sales/history/', f'/sales/products/{record.pk}/']
        for path in paths:
            self.assertEqual(self.client.get(path).status_code, 302)
        self.client.force_login(self.maker)
        for path in paths:
            if path == '/sales/':
                self.assertRedirects(self.client.get(path), '/panel/', fetch_redirect_response=False)
            else:
                self.assertEqual(self.client.get(path).status_code, 403)
        self.client.force_login(self.actor)
        for path in paths:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 200, path)
            self.assertIn('no-store', response.headers.get('Cache-Control',''))
        self.assertRedirects(self.client.get('/studio/'), '/panel/', fetch_redirect_response=False)
        self.assertEqual(self.client.get('/sales/products/99999999/').status_code, 404)

    def test_manager_can_read_history_but_needs_sales_role_to_edit(self):
        record = self.create()
        self.act(record, 'sell')
        manager = get_user_model().objects.create_user('audit-manager')
        manager.user_permissions.add(Permission.objects.get(codename='view_studioproduct'))
        self.client.force_login(manager)
        self.assertEqual(self.client.get('/sales/history/').status_code, 200)
        self.assertEqual(self.client.get(f'/sales/products/{record.pk}/').status_code, 403)
        self.assertEqual(self.client.post(f'/sales/products/{record.pk}/',
            {'action':'restore','reason':'test','version':version(record)}).status_code,403)
        record.refresh_from_db()
        self.assertEqual(record.status, 'SOLD')

    def test_login_sales_destination_and_safe_next(self):
        self.actor.set_password('strong-test-password')
        self.actor.save()
        record = self.create()
        for target, expected in [('https://untrusted.example/', '/sales/'),
                ('/studio/', '/sales/'), ('/team/', '/sales/'),
                (f'/sales/products/{record.pk}/', f'/sales/products/{record.pk}/')]:
            self.client.logout()
            response = self.client.post('/studio/login/', {'username':self.actor.username,
                'password':'strong-test-password','next':target})
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, expected)

    def test_csrf_rejects_mutation(self):
        from django.test import Client
        record = self.create()
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.actor)
        response = client.post(f'/sales/products/{record.pk}/',
            {'action':'sell','reason':'test','version':version(record)})
        self.assertEqual(response.status_code,403)
        record.refresh_from_db()
        self.assertEqual(record.status, 'AVAILABLE')

    def test_view_validates_reason_version_and_price(self):
        record = self.create()
        self.client.force_login(self.actor)
        url = f'/sales/products/{record.pk}/'
        for data in [{'action':'sell','reason':'','version':version(record)},
                     {'action':'sell','reason':'test','version':'stale'},
                     {'action':'edit','reason':'test','version':version(record),
                      'factor_code':record.factor_code,'florist':self.florist.pk,
                      'product_type':'box','price':'-1'}]:
            self.assertEqual(self.client.post(url,data).status_code,400)
        record.refresh_from_db()
        self.assertEqual(record.status,'AVAILABLE')
        self.assertFalse(record.sales_audits.exists())
        response=self.client.post(url,{'action':'edit','reason':'اصلاح قیمت','version':version(record),
                      'factor_code':record.factor_code,'florist':self.florist.pk,
                      'product_type':'box','price':'۳٬۲۰۰٬۰۰۰'})
        self.assertEqual(response.status_code,302)
        record.refresh_from_db()
        self.assertEqual(record.price,3200000)

    def test_republished_product_resale_retires_new_message_only(self):
        record = self.create()
        old = record.telegram_message_id
        self.act(record,'sell')
        StudioProduct.objects.filter(pk=record.pk).update(sold_at=timezone.now()-timedelta(minutes=46))
        record.deliveries.filter(action='RETIRE').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(process_next_delivery().outcome,'deleted')
        self.act(record,'restore')
        self.assertEqual(process_next_delivery().status,'SENT')
        record.refresh_from_db()
        new = record.telegram_message_id
        self.act(record,'sell')
        StudioProduct.objects.filter(pk=record.pk).update(sold_at=timezone.now()-timedelta(minutes=46))
        record.deliveries.filter(action='RETIRE').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(process_next_delivery().outcome,'deleted')
        self.assertNotEqual(old,new)
        self.assertEqual(self.delete.call_args.args,(-5595039112,new))
        self.assertEqual(self.delete.call_count,2)

    def reply(self, record, message_id, date, update_id):
        from main.telegram_same_day.service import process_update
        return process_update('message', {'message_id':message_id+10000,
            'chat':{'id':record.telegram_chat_id,'type':'group'},'date':date,
            'from':{'id':702,'is_bot':False},'text':'فروخته شد',
            'reply_to_message':{'message_id':message_id,'chat':{'id':record.telegram_chat_id,'type':'group'},
                'date':date-60,'from':{'id':99,'is_bot':True},
                'photo':[{'file_id':'mock-photo','width':100,'height':100}]}},update_id)

    def test_stale_group_reply_cannot_resell_restored_product(self):
        record = self.create()
        old_date = int(timezone.now().timestamp())-60
        self.act(record,'sell')
        self.act(record,'restore')
        record.refresh_from_db()
        result=self.reply(record,record.telegram_message_id,old_date,900001)
        self.assertEqual(result,'stale_before_restore_ignored')
        record.refresh_from_db()
        self.assertEqual(record.status,'AVAILABLE')

    def test_reply_to_deleted_old_message_cannot_sell_new_publication(self):
        record = self.create()
        old = record.telegram_message_id
        self.act(record,'sell')
        StudioProduct.objects.filter(pk=record.pk).update(sold_at=timezone.now()-timedelta(minutes=46))
        record.deliveries.filter(action='RETIRE').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        process_next_delivery()
        self.act(record,'restore')
        process_next_delivery()
        record.refresh_from_db()
        result=self.reply(record,old,int(timezone.now().timestamp())+2,900002)
        self.assertEqual(result,'admin_deleted_ignored')
        record.refresh_from_db()
        self.assertEqual(record.status,'AVAILABLE')

    def test_claim_serializes_sync_and_retirement_for_same_product(self):
        from main.studio_delivery import claim_delivery
        record = self.create()
        self.act(record,'edit',values={'price':3200000})
        self.act(record,'sell')
        StudioProduct.objects.filter(pk=record.pk).update(sold_at=timezone.now()-timedelta(minutes=46))
        record.deliveries.filter(action='RETIRE').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        first=claim_delivery()
        self.assertIsNotNone(first)
        self.assertIsNone(claim_delivery())
        self.assertEqual(record.deliveries.filter(status='SENDING').count(),1)
        with self.assertRaises(ValidationError):
            self.act(record,'restore')

    def test_old_sync_lease_cannot_edit_after_reclaim(self):
        from main.studio_delivery import claim_delivery, _sync_message
        record=self.create()
        self.act(record,'edit',values={'price':3200000})
        old=claim_delivery()
        StudioDelivery.objects.filter(pk=old.pk).update(locked_at=timezone.now()-timedelta(minutes=10))
        new=claim_delivery()
        self.assertNotEqual(old.lock_token,new.lock_token)
        _sync_message(old)
        self.edit.assert_not_called()
        new.refresh_from_db()
        self.assertEqual(new.status,'SENDING')
        _sync_message(new)
        self.edit.assert_called_once()
        new.refresh_from_db()
        self.assertEqual(new.status,'SENT')

    def test_sale_confirmation_changes_price_status_projection_and_audit_atomically(self):
        from django.urls import reverse
        record=self.create()
        self.client.force_login(self.actor)
        url=reverse('sales_detail',args=[record.pk])
        response=self.client.get(url)
        self.assertContains(response,'name="sale_price"')
        payload={'action':'sell','version':version(record),'reason':'فروش با تخفیف هماهنگ‌شده','sale_price':'۱٬۸۰۰٬۰۰۰'}
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,302)
        record.refresh_from_db(); record.product.refresh_from_db()
        self.assertEqual((record.price,record.status),(1800000,'SOLD'))
        self.assertEqual(record.product.price,1800000)
        self.assertEqual(record.product.status,'SOLD')
        audit=record.sales_audits.get()
        self.assertNotEqual(audit.before['price'],audit.after['price'])
        self.assertEqual(audit.after['price'],'1800000')
        self.assertEqual(audit.action,'sell')
        self.assertEqual(record.deliveries.get(action='SYNC').status,'PENDING')
        # Repeated requests cannot duplicate a sale or overwrite its price.
        response=self.client.post(url,payload)
        self.assertEqual(response.status_code,400)
        self.assertEqual(record.sales_audits.count(),1)

    def test_invalid_final_sale_price_or_reason_never_partially_updates_product(self):
        from django.urls import reverse
        record=self.create()
        self.client.force_login(self.actor)
        original=record.price
        for price,reason in [('0','اصلاح'),('NaN','اصلاح'),('1.5','اصلاح'),('2000000','')]:
            with self.subTest(price=price,reason=reason):
                response=self.client.post(reverse('sales_detail',args=[record.pk]),
                    {'action':'sell','version':version(record),'reason':reason,'sale_price':price})
                self.assertEqual(response.status_code,400)
                record.refresh_from_db(); record.product.refresh_from_db()
                self.assertEqual(record.status,'AVAILABLE')
                self.assertEqual(record.price,original)
                self.assertEqual(record.product.price,original)
                self.assertFalse(record.sales_audits.exists())

    def test_price_corrections_remain_available_in_all_allowed_statuses(self):
        for status in ['AVAILABLE','SOLD','WITHDRAWN']:
            record=self.create()
            if status!='AVAILABLE': self.act(record,'sell' if status=='SOLD' else 'withdraw')
            self.act(record,'edit',values={'price':2700000})
            record.refresh_from_db()
            self.assertEqual((record.status,record.price),(status,2700000))
            self.assertEqual(record.sales_audits.filter(action='edit').count(),1)

    def test_sale_date_edit_moves_totals_and_preserves_time_projection_and_audit(self):
        from zoneinfo import ZoneInfo
        from django.urls import reverse
        from django.test import RequestFactory
        from main.persian_dates import format_persian_date
        from main.studio_views import _period, _activity, _stats
        record = self.create()
        self.act(record, 'sell')
        record.refresh_from_db()
        original = record.sold_at
        zone = ZoneInfo('Asia/Tehran')
        day = original.astimezone(zone).date() - timedelta(days=2)
        produced_at = record.produced_at
        retirement_due = record.deliveries.get(action='RETIRE').next_attempt_at
        self.client.force_login(self.actor)
        url = reverse('sales_detail', args=[record.pk])
        self.assertContains(self.client.get(url), 'name="sold_date"')
        response = self.client.post(url, {'action':'edit', 'version':version(record),
            'factor_code':record.factor_code, 'florist':self.florist.pk,
            'product_type':record.product_type, 'price':record.price, 'notes':record.notes,
            'sold_date':format_persian_date(day), 'reason':'اصلاح تاریخ فروش'})
        self.assertEqual(response.status_code, 302)
        record.refresh_from_db()
        self.assertEqual(record.sold_at.astimezone(zone).date(), day)
        self.assertEqual(record.sold_at.astimezone(zone).time(), original.astimezone(zone).time())
        self.assertEqual(record.produced_at, produced_at)
        self.assertEqual(record.deliveries.get(action='RETIRE').next_attempt_at, retirement_due)
        self.assertEqual(TelegramSameDayPost.objects.get(product=record.product).sold_at, record.sold_at)
        audit = record.sales_audits.get(action='edit')
        self.assertEqual(audit.before['sold_at'], str(original))
        from datetime import datetime
        self.assertEqual(datetime.fromisoformat(audit.after['sold_at']), record.sold_at)
        for reporting_day, expected in [(day, record.price), (original.astimezone(zone).date(), 0)]:
            period = _period(RequestFactory().get('/', {'period':'custom', 'start':reporting_day, 'end':reporting_day}))
            self.assertEqual(_stats(_activity(period), period)['sold_value'], expected)
        self.assertEqual(self.client.get(reverse('sales_home')).context['stats']['value'], 0)

    def test_sale_date_cannot_be_added_to_unsold_record_or_set_in_future(self):
        record = self.create()
        day = timezone.localdate()
        self.client.force_login(self.actor)
        from django.urls import reverse
        self.assertNotContains(self.client.get(reverse('sales_detail', args=[record.pk])), 'name="sold_date"')
        with self.assertRaises(ValidationError):
            self.act(record, 'edit', values={'sold_date': day})
        self.act(record, 'sell')
        record.refresh_from_db()
        original = record.sold_at
        for invalid in [day + timedelta(days=1), None, 'invalid']:
            with self.subTest(invalid=invalid), self.assertRaises(ValidationError):
                self.act(record, 'edit', values={'sold_date': invalid, 'price': 1})
        record.refresh_from_db()
        self.assertEqual((record.sold_at, record.price), (original, 2500000))
        self.assertFalse(record.sales_audits.filter(action='edit').exists())

    def finish_transfer(self):
        self.assertEqual(process_next_delivery().action,'RECLASS')
        return process_next_delivery()

    def test_correct_ready_to_custom_preserves_identity_status_and_moves_group_after_cleanup(self):
        from django.urls import reverse
        record=self.create()
        original_pk,public_pk,old_message=record.pk,record.product_id,record.telegram_message_id
        self.client.force_login(self.actor)
        self.assertContains(self.client.get(reverse('sales_detail',args=[record.pk])), 'name="production_type"')
        response=self.client.post(reverse('sales_detail',args=[record.pk]),{
            'action':'edit','version':version(record),'reason':'ثبت اشتباه در آماده‌ها',
            'factor_code':record.factor_code,'florist':self.florist.pk,'product_type':record.product_type,
            'production_type':'CUSTOM','price':record.price,'notes':record.notes})
        self.assertEqual(response.status_code,302)
        record.refresh_from_db()
        self.assertEqual((record.pk,record.production_type,record.status),(original_pk,'CUSTOM','AVAILABLE'))
        self.assertIsNone(record.product_id)
        self.assertEqual(record.parked_product_id,public_pk)
        self.assertEqual(Product.objects.get(pk=public_pk).publish_status,'draft')
        self.assertIsNone(record.telegram_message_id)
        self.assertIsNotNone(TelegramSameDayPost.objects.get(telegram_chat_id=-5595039112,telegram_message_id=old_message).deleted_at)
        self.assertEqual(self.send.call_count,1)
        self.assertEqual(self.finish_transfer().status,'SENT')
        self.delete.assert_called_once_with(-5595039112,old_message)
        record.refresh_from_db()
        self.assertEqual(record.telegram_chat_id,-5182713369)
        self.assertEqual(self.send.call_args.args[0],-5182713369)
        self.assertEqual(StudioProduct.objects.count(),1)
        audit=record.sales_audits.get()
        self.assertEqual((audit.before['production_type'],audit.after['production_type']),('DAILY','CUSTOM'))

    def test_reverse_correction_reuses_catalog_and_keeps_original_source(self):
        record=self.create()
        public_pk=record.product_id
        StudioProduct.objects.filter(pk=record.pk).update(source='TELEGRAM_DAILY')
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.finish_transfer()
        self.act(record,'edit',values={'production_type':'DAILY'})
        self.finish_transfer()
        record.refresh_from_db();record.full_clean()
        self.assertEqual(record.source,'TELEGRAM_DAILY')
        self.assertEqual(record.product_id,public_pk)
        self.assertIsNone(record.parked_product_id)
        record.product.refresh_from_db()
        self.assertEqual(record.product.publish_status,'published')
        self.assertEqual(Product.objects.count(),1)
        self.assertEqual(record.telegram_chat_id,-5595039112)
        self.assertEqual(self.delete.call_count,2)

    def test_correction_of_sold_product_moves_sales_split_without_changing_sale_date(self):
        from django.test import RequestFactory
        from main.studio_views import _stats,_activity,_period
        record=self.create('CUSTOM')
        original_sold=record.sold_at
        self.act(record,'edit',values={'production_type':'DAILY'})
        record.refresh_from_db()
        self.assertEqual((record.status,record.sold_at),('SOLD',original_sold))
        self.assertEqual(record.product.publish_status,'draft')
        period=_period(RequestFactory().get('/'))
        stats=_stats(_activity(period),period)
        self.assertEqual((stats['daily_sales'],stats['custom_sales'],stats['sold_value']),(record.price,0,record.price))
        job=self.finish_transfer()
        self.assertEqual((job.status,job.outcome),('SENT','not_available'))
        self.assertEqual(self.send.call_count,1)  # Already-sold ready stock is never advertised.

    def test_failed_old_group_cleanup_blocks_new_send_and_further_edits(self):
        record=self.create()
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.delete.side_effect=TelegramDeliveryError('rate_limited',retryable=True,retry_after=60)
        self.assertEqual(process_next_delivery().status,'RETRY')
        self.assertIsNone(process_next_delivery())
        self.assertEqual(self.send.call_count,1)
        with self.assertRaises(ValidationError):
            self.act(record,'edit',values={'production_type':'DAILY'})
        self.delete.side_effect=None
        record.deliveries.filter(action='RECLASS').update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.finish_transfer().status,'SENT')

    def test_old_message_delete_forbidden_uses_caption_tombstone_then_moves(self):
        record=self.create()
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.delete.side_effect=TelegramDeliveryError('message_cannot_be_deleted')
        caption=self.mock('main.studio_transport.edit_caption',return_value=True)
        cleanup=process_next_delivery()
        self.assertEqual(cleanup.outcome,'caption_marked')
        self.assertIn('دیگر مرجع',caption.call_args.args[2])
        self.assertEqual(process_next_delivery().status,'SENT')

    def test_uncertain_destination_send_is_not_duplicated(self):
        record=self.create()
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.assertEqual(process_next_delivery().action,'RECLASS')
        self.send.side_effect=TelegramDeliveryError('transport_uncertain',uncertain=True)
        self.assertEqual(process_next_delivery().status,'UNCERTAIN')
        self.assertIsNone(process_next_delivery())
        with self.assertRaises(ValidationError):self.act(record,'edit',values={'price':1})
        self.assertEqual(self.send.call_count,2)

    def test_invalid_destination_or_missing_configuration_rolls_back_projection_and_audit(self):
        record=self.create()
        original_product=record.product_id
        for destination in ['MISC','invalid']:
            with self.subTest(destination=destination), self.assertRaises(ValidationError):
                self.act(record,'edit',values={'production_type':destination})
        with override_settings(TELEGRAM_STUDIO_CUSTOM_GROUP_ID=''),self.assertRaises(ValidationError):
            self.act(record,'edit',values={'production_type':'CUSTOM'})
        record.refresh_from_db()
        self.assertEqual((record.production_type,record.product_id),('DAILY',original_product))
        self.assertFalse(record.sales_audits.exists())
        self.assertFalse(record.deliveries.filter(action='RECLASS').exists())

    def test_old_custom_message_cannot_reimport_or_update_corrected_product(self):
        from main.studio_ingestion import process_custom
        record=self.create('CUSTOM')
        old_message=record.telegram_message_id
        self.act(record,'edit',values={'production_type':'DAILY'})
        message={'message_id':old_message,'chat':{'id':-5182713369,'type':'supergroup'},
            'from':{'id':666,'is_bot':False},'date':int(timezone.now().timestamp()),
            'photo':[{'file_id':'old'}],'caption':'invalid'}
        self.assertEqual(process_custom(message,1000,[])['result'],'corrected_message_ignored')
        message.update(message_id=old_message+100,text='قیمت: 1',reply_to_message={
            'message_id':old_message,'chat':{'id':-5182713369}},photo=[])
        self.assertEqual(process_custom(message,1001,[])['result'],'corrected_message_ignored')
        record.refresh_from_db()
        self.assertEqual((record.production_type,record.price),('DAILY',2500000))
        self.assertEqual(StudioProduct.objects.count(),1)

    def test_corrected_telegram_daily_source_accepts_reply_in_new_custom_group(self):
        from main.studio_ingestion import process_custom
        record=self.create()
        StudioProduct.objects.filter(pk=record.pk).update(source='TELEGRAM_DAILY')
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.finish_transfer()
        record.refresh_from_db()
        message={'message_id':9999,'chat':{'id':-5182713369,'type':'supergroup'},
            'from':{'id':666,'is_bot':False},'date':int(timezone.now().timestamp()),
            'text':'قیمت: 3000000','reply_to_message':{'message_id':record.telegram_message_id,
                'chat':{'id':-5182713369}}}
        self.assertEqual(process_custom(message,1000,[])['result'],'price_updated')
        record.refresh_from_db()
        self.assertEqual((record.price,record.source),(3000000,'TELEGRAM_DAILY'))

    def test_unpublished_correction_sends_once_and_future_ready_sale_requeues_retirement(self):
        record=self.create(publish=False)
        self.act(record,'edit',values={'production_type':'CUSTOM'})
        self.assertFalse(record.deliveries.filter(action='RECLASS').exists())
        self.assertEqual(process_next_delivery().status,'SENT')
        self.assertEqual(self.send.call_count,1)
        self.act(record,'edit',values={'production_type':'DAILY'})
        self.finish_transfer()
        record.refresh_from_db()
        # Emulate a cancelled retirement from an earlier terminal lifecycle.
        StudioDelivery.objects.update_or_create(record=record,action='RETIRE',defaults={
            'chat_id':-5182713369,'message_id':123,'status':'SENT','outcome':'type_corrected'})
        self.act(record,'sell')
        retirement=record.deliveries.get(action='RETIRE')
        self.assertEqual((retirement.status,retirement.chat_id,retirement.message_id),
            ('RETRY',-5595039112,record.telegram_message_id))
