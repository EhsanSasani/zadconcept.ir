"""A command for an uncertain photo send must not hold up unrelated Telegram updates."""
from contextvars import ContextVar
from datetime import datetime, timezone as utc_timezone
import logging
from django.core.exceptions import ValidationError
from django.db import transaction, DatabaseError
from django.utils import timezone
from .models import StudioDelivery, StudioPendingReply

logger=logging.getLogger(__name__)
_occurred_at=ContextVar('telegram_pending_event_time',default=None)


def command_time():
    return _occurred_at.get() or timezone.now()


def retain_pending_reply(*,update_id,kind,message,delivery_id):
    delivery=StudioDelivery.objects.get(pk=delivery_id)
    reply=message.get('reply_to_message',{})
    if (kind not in {'message','edited_message'} or delivery.action!='PUBLISH'
            or message.get('chat',{}).get('id')!=delivery.chat_id
            or reply.get('chat',{}).get('id')!=delivery.chat_id or not reply.get('message_id')):
        raise ValidationError('invalid_pending_reply')
    StudioPendingReply.objects.get_or_create(update_id=update_id,defaults={
        'delivery':delivery,'kind':kind,'message':message,'reply_message_id':reply['message_id']})


def _process_pending_reply():
    from .telegram_same_day.service import process_update, SyncConfigurationError, InvalidSource
    from .telegram_same_day.client import TelegramTransportError
    # Only an already-established mapping may unlock a retained command.
    candidate=StudioPendingReply.objects.filter(state='WAITING',delivery__status='SENT',
        delivery__message_id__isnull=False).order_by('update_id').first()
    if candidate is None:
        return None
    with transaction.atomic():
        item=StudioPendingReply.objects.select_for_update().get(pk=candidate.pk)
        if item.state!='WAITING':
            return None
        delivery=StudioDelivery.objects.select_related('record').get(pk=item.delivery_id)
        record=delivery.record
        if (delivery.message_id!=item.reply_message_id or record.telegram_message_id!=item.reply_message_id
                or record.telegram_chat_id!=delivery.chat_id):
            item.state='REVIEW'
        else:
            try:
                with transaction.atomic():
                    occurred_at=min(datetime.fromtimestamp(item.message['date'],tz=utc_timezone.utc),item.received_at)
                    if record.sales_audits.filter(created_at__gt=occurred_at).exists():
                        raise ValidationError('newer_manual_correction_requires_review')
                    token=_occurred_at.set(occurred_at)
                    try:
                        process_update(item.kind,item.message,item.update_id)
                    finally:
                        _occurred_at.reset(token)
            except (ValidationError,SyncConfigurationError,InvalidSource,TelegramTransportError,OSError,ValueError,KeyError,OverflowError):
                item.state='REVIEW'
                logger.warning('Retained Telegram command requires review; other queues remain available')
            else:
                item.state='APPLIED'
                item.applied_at=timezone.now()
        item.save(update_fields=['state','applied_at'])
        return item


def process_pending_reply():
    try:
        return _process_pending_reply()
    except DatabaseError:
        logger.warning('Pending Telegram command database retry required')
        return None
