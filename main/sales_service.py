"""Sales actions: public-row -> ledger -> delivery locks, then audit in one commit."""
from datetime import timedelta
import hashlib
import json
import re
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone
from .models import Product, StudioProduct, StudioDelivery, StudioSalesAudit, TelegramSameDayPost
from .studio_access import can_use_sales
from .studio_delivery import _lock_record, queue_retirement
from .studio_publishing import _daily_configuration, _clean_failed_file
from .image_pipeline import create_responsive_image_variants

FIELDS = ('factor_code', 'florist_id', 'product_type', 'production_type', 'price', 'status',
          'image', 'notes', 'sold_at', 'withdrawn_at', 'produced_at', 'telegram_chat_id', 'telegram_message_id')


def snapshot(record):
    values = {field: str(getattr(record, field) or '') for field in FIELDS}
    if not values['image'] and record.product_id:
        values['image'] = record.product.cover_image.name
    return values


def version(record):
    data = {**snapshot(record), 'updated_at': record.updated_at.isoformat()}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def _audit(record, actor, action, reason, before):
    StudioSalesAudit.objects.create(record=record, actor=actor, actor_name=actor.get_username(),
                                   action=action, reason=reason, before=before, after=snapshot(record))


def queue_sync(record):
    if not record.telegram_message_id:
        return
    job, _ = StudioDelivery.objects.get_or_create(record=record, action=StudioDelivery.Action.SYNC,
        defaults={'chat_id': record.telegram_chat_id, 'message_id': record.telegram_message_id})
    job.chat_id, job.message_id = record.telegram_chat_id, record.telegram_message_id
    job.status, job.attempts = StudioDelivery.Status.PENDING, 0
    job.next_attempt_at = timezone.now()
    job.locked_at = job.lock_token = None
    job.last_error, job.outcome = '', ''
    job.save()


def forget_absent_message(record):
    """Called only after confirmed absence. Tombstones reject replies to old posts."""
    TelegramSameDayPost.objects.filter(telegram_chat_id=record.telegram_chat_id,
        telegram_message_id=record.telegram_message_id).update(product=None, deleted_at=timezone.now())
    record.telegram_chat_id = record.telegram_message_id = None
    record.telegram_file_id = ''
    record.save(update_fields=['telegram_chat_id','telegram_message_id','telegram_file_id','updated_at'])


def requeue_publication(record):
    _, chat_id = _daily_configuration()
    job, _ = StudioDelivery.objects.get_or_create(record=record, action=StudioDelivery.Action.PUBLISH,
                                                 defaults={'chat_id': chat_id})
    job.chat_id, job.message_id, job.telegram_created_at = chat_id, None, None
    job.status, job.attempts, job.outcome, job.last_error = StudioDelivery.Status.PENDING, 0, '', ''
    job.locked_at = job.lock_token = job.sent_at = None
    job.next_attempt_at = timezone.now()
    job.save()


def ensure_delivery_editable(jobs):
    if any(j.status in {StudioDelivery.Status.SENDING, StudioDelivery.Status.UNCERTAIN} for j in jobs):
        raise ValidationError('ارسال تلگرام در حال انجام یا نیازمند بررسی است؛ پس از تعیین نتیجه دوباره اقدام کنید.')
    if any(j.last_error == 'worker_interrupted' and j.updated_at > timezone.now() - timedelta(seconds=180) for j in jobs):
        raise ValidationError('ارسال قبلی قطع شده است؛ سه دقیقه صبر کنید تا وضعیت صف پایدار شود.')


def apply_sales_action(*, pk, actor, expected_version, action, reason, values=None):
    if not can_use_sales(actor):
        raise PermissionDenied
    reason = (reason or '').strip()
    if not reason or len(reason) > 500:
        raise ValidationError('علت عملیات را بنویسید (حداکثر ۵۰۰ نویسه).')
    if action not in {'edit','sell','withdraw','restore'}:
        raise ValidationError('عملیات معتبر نیست.')
    current = None
    try:
        with transaction.atomic():
            current = _lock_record(pk)
            if current.production_type == "MISC":
                raise ValidationError("فروش شاخه و متفرقه را از فرم مخصوص آن اصلاح کنید.")
            if version(current) != expected_version:
                raise ValidationError('محصول پس از بازکردن صفحه تغییر کرده است؛ صفحه را تازه کنید و دوباره بررسی کنید.')
            if current.status == StudioProduct.Status.DELETED:
                raise ValidationError('محصول حذف مدیریتی شده؛ اصلاح آن از پنل فروش مجاز نیست.')
            jobs = list(current.deliveries.select_for_update())
            ensure_delivery_editable(jobs)
            before = snapshot(current)
            now = timezone.now()
            if action == 'edit':
                values = values or {}
                for name in ('factor_code', 'florist', 'product_type', 'price', 'notes'):
                    if name in values:
                        setattr(current, name, values[name])
                if not re.fullmatch(r'[A-Z0-9-]{1,40}', current.factor_code):
                    raise ValidationError('شماره فاکتور باید عدد، حروف انگلیسی یا خط تیره باشد.')
                if values.get('image'):
                    current.image = values['image']
                current.full_clean()
                current.save()
                if current.product_id:
                    updates = dict(price=current.price,
                                   pricing_type=Product.PricingType.FIXED, updated_at=now)
                    if before['product_type'] != current.product_type:
                        updates['name'] = current.get_product_type_display()
                    if values.get('image'):
                        updates['cover_image'] = current.image.name
                    Product.objects.filter(pk=current.product_id).update(**updates)
                if values.get('image'):
                    storage, name = current.image.storage, current.image.name
                    transaction.on_commit(lambda: create_responsive_image_variants(storage, name))
                queue_sync(current)
            elif action in {'sell','withdraw'}:
                if current.status != StudioProduct.Status.AVAILABLE:
                    raise ValidationError('این محصول دیگر موجود نیست؛ صفحه را تازه کنید.')
                current.status = StudioProduct.Status.SOLD if action == 'sell' else StudioProduct.Status.WITHDRAWN
                current.sold_at = now if action == 'sell' else None
                current.withdrawn_at = now if action == 'withdraw' else None
                current.save(update_fields=['status','sold_at','withdrawn_at','updated_at'])
                if current.product_id:
                    Product.objects.filter(pk=current.product_id).update(status=Product.Status.SOLD if action=='sell' else Product.Status.WITHDRAWN,
                        stock_status=Product.StockStatus.OUT_OF_STOCK, updated_at=now)
                    TelegramSameDayPost.objects.filter(product_id=current.product_id).update(sold_at=current.sold_at,
                        withdrawn_at=current.withdrawn_at, updated_at=now)
                # Legacy incoming posts have no outbound publication. Keep their existing behavior.
                queue_retirement(current)
            else:
                if current.production_type != StudioProduct.ProductionType.DAILY:
                    raise ValidationError('سفارش اختصاصی به موجودی عمومی برنمی‌گردد.')
                if current.status not in {StudioProduct.Status.SOLD, StudioProduct.Status.WITHDRAWN, StudioProduct.Status.CANCELLED}:
                    raise ValidationError('فقط محصول خارج‌شده از موجودی قابل بازگشت است.')
                retirement = next((j for j in jobs if j.action == StudioDelivery.Action.RETIRE), None)
                absent = retirement and retirement.status == StudioDelivery.Status.SENT and retirement.outcome in {'deleted','already_absent'}
                if absent:
                    forget_absent_message(current)
                if retirement:
                    retirement.status, retirement.outcome = StudioDelivery.Status.SENT, 'restored'
                    retirement.locked_at = retirement.lock_token = None
                    retirement.save()
                current.sales_reopened_at = now
                current.status = StudioProduct.Status.AVAILABLE
                current.sold_at = current.withdrawn_at = None
                current.save(update_fields=['status','sold_at','withdrawn_at','sales_reopened_at','updated_at'])
                if current.product_id:
                    Product.objects.filter(pk=current.product_id).update(status=Product.Status.AVAILABLE,
                        stock_status=Product.StockStatus.IN_STOCK, publish_status=Product.PublishStatus.PUBLISHED, updated_at=now)
                    TelegramSameDayPost.objects.filter(product_id=current.product_id).update(sold_at=None,withdrawn_at=None,
                        deleted_at=None,updated_at=now)
                else:
                    category, chat_id = _daily_configuration()
                    public = Product.objects.create(name=current.get_product_type_display(),
                        slug=f'studio-restored-{current.pk}',category=category,
                        catalog_scope=Product.CatalogScope.SAME_DAY,price=current.price,
                        pricing_type=Product.PricingType.FIXED,cover_image=current.image.name,
                        status=Product.Status.AVAILABLE,stock_status=Product.StockStatus.IN_STOCK,
                        publish_status=Product.PublishStatus.PUBLISHED)
                    current.product = public
                    current.save(update_fields=['product','updated_at'])
                    if current.telegram_message_id:
                        TelegramSameDayPost.objects.filter(telegram_chat_id=current.telegram_chat_id,
                            telegram_message_id=current.telegram_message_id).update(product=public,
                                sold_at=None,withdrawn_at=None,deleted_at=None)
                if current.telegram_message_id:
                    queue_sync(current)
                else:
                    requeue_publication(current)
            _audit(current, actor, action, reason, before)
            return current
    except Exception:
        if current and action == 'edit' and (values or {}).get('image'):
            _clean_failed_file(current)
        raise
