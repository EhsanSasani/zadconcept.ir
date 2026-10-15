"""Prepare a same-record correction; cleanup and publication use the durable outbox."""
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import Product, StudioProduct, StudioDelivery, TelegramSameDayPost
from .studio_publishing import _daily_configuration, _custom_configuration


def prepare_reclassification(record, target):
    # Called only inside apply_sales_action's permission/version/record/job locks.
    if target not in {StudioProduct.ProductionType.DAILY, StudioProduct.ProductionType.CUSTOM}:
        raise ValidationError('اصلاح نوع فقط بین آماده و سفارشی مجاز است.')
    category, chat_id = _daily_configuration() if target == 'DAILY' else (None, _custom_configuration())
    now = timezone.now()
    old_chat, old_message = record.telegram_chat_id, record.telegram_message_id
    if old_chat and old_message:
        TelegramSameDayPost.objects.update_or_create(telegram_chat_id=old_chat, telegram_message_id=old_message,
            defaults={'product':None,'deleted_at':now})
    # Never delete the catalog row or uploaded image. Reuse it on a reverse correction.
    if target == 'CUSTOM' and record.product_id:
        if not record.image:
            record.image = record.product.cover_image.name
        Product.objects.filter(pk=record.product_id).update(publish_status=Product.PublishStatus.DRAFT,
            stock_status=Product.StockStatus.OUT_OF_STOCK, updated_at=now)
        record.parked_product_id, record.product_id = record.product_id, None
    elif target == 'DAILY':
        public = record.parked_product
        available = record.status == StudioProduct.Status.AVAILABLE
        fields = dict(name=record.get_product_type_display(),price=record.price,
            pricing_type=Product.PricingType.FIXED,cover_image=record.image.name,
            status=Product.Status.AVAILABLE if available else Product.Status.SOLD if record.status=='SOLD' else Product.Status.WITHDRAWN,
            stock_status=Product.StockStatus.IN_STOCK if available else Product.StockStatus.OUT_OF_STOCK,
            publish_status=Product.PublishStatus.PUBLISHED if available else Product.PublishStatus.DRAFT)
        if public:
            Product.objects.filter(pk=public.pk).update(**fields,updated_at=now)
        else:
            public = Product.objects.create(**fields,category=category,catalog_scope=Product.CatalogScope.SAME_DAY,
                slug=f'studio-corrected-{record.pk}',product_code=record.display_id)
        record.product, record.parked_product = public, None
    record.production_type = target
    record.production_type_corrected = True
    record.telegram_chat_id = record.telegram_message_id = None
    record.telegram_file_id = ''
    record.revision_date, record.revision_update_id = 0, -1
    record.deliveries.update(status=StudioDelivery.Status.SENT,outcome='type_corrected',
        locked_at=None,lock_token=None,last_error='',updated_at=now)
    if old_chat and old_message:
        StudioDelivery.objects.update_or_create(record=record,action=StudioDelivery.Action.RECLASS,
            defaults={'chat_id':old_chat,'message_id':old_message,'status':StudioDelivery.Status.PENDING,
                'next_attempt_at':now,'attempts':0,'outcome':'','last_error':'','locked_at':None,'lock_token':None})
    StudioDelivery.objects.update_or_create(record=record,action=StudioDelivery.Action.PUBLISH,
        defaults={'chat_id':chat_id,'message_id':None,'telegram_created_at':None,'sent_at':None,
            'status':StudioDelivery.Status.PENDING,'next_attempt_at':now,'attempts':0,
            'outcome':'type_correction','last_error':'','locked_at':None,'lock_token':None})
