"""Atomic portal registration. Network delivery is handled by a separate outbox worker."""
import logging
import re
import uuid
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import IntegrityError, transaction

from .image_pipeline import ImageUploadError, create_responsive_image_variants, normalize_admin_image
from .models import Category, Florist, Product, StudioDelivery, StudioProduct
from .telegram_same_day.price import DIGITS

logger = logging.getLogger(__name__)


def _existing_submission(key, user, florist):
    record = StudioProduct.objects.filter(submission_key=key).first()
    if record is None:
        return None
    if record.created_by_id != user.pk or record.florist_id != florist.pk:
        raise ValidationError({"submission_key": "شناسهٔ ثبت معتبر نیست؛ فرم تازه‌ای باز کنید."})
    return record


def _daily_configuration():
    category_id = str(getattr(settings, "TELEGRAM_SAME_DAY_CATEGORY_ID", ""))
    category = Category.objects.for_general_catalog().filter(
        pk=category_id, section=Category.Section.FLOWERS, is_active=True,
    ).first() if category_id.isdigit() else None
    if not category or category.is_wedding_category:
        raise ValidationError("دستهٔ محصولات روز تنظیم نشده است؛ با مدیر هماهنگ کنید.")
    group_id = str(getattr(settings, "TELEGRAM_SAME_DAY_GROUP_ID", ""))
    if not re.fullmatch(r"-[1-9][0-9]{0,18}", group_id):
        raise ValidationError("گروه آماده‌ها تنظیم نشده است؛ با مدیر هماهنگ کنید.")
    return category, int(group_id)


def _clean_failed_file(record):
    image = record.image
    if not image or not image._committed:
        return
    try:
        if not (StudioProduct.objects.filter(image=image.name).exists()
                or Product.objects.filter(cover_image=image.name).exists()):
            image.storage.delete(image.name)
    except Exception:
        logger.error("portal image rollback cleanup needs review")


def create_portal_record(*, user, florist, image, factor_code, product_type,
                         production_type, price, submission_key, notes=""):
    """Return (record, created); a repeated key never republishes or reuploads."""
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        raise PermissionDenied
    # The authenticated submitter and selected maker are separate identities.
    # Only an active team member may register a product for an active florist.
    uploader = Florist.objects.filter(user_id=user.pk, is_active=True).first()
    if uploader is None:
        raise PermissionDenied
    if not getattr(florist, "pk", None):
        raise ValidationError({"florist": "فلوریست سازنده را انتخاب کنید."})
    try:
        key = uuid.UUID(str(submission_key))
    except (ValueError, TypeError, AttributeError):
        raise ValidationError({"submission_key": "شناسهٔ ثبت معتبر نیست؛ فرم تازه‌ای باز کنید."}) from None
    existing = _existing_submission(key, user, florist)
    if existing:
        return existing, False
    if not Florist.objects.filter(pk=florist.pk, is_active=True).exists():
        raise ValidationError({"florist": "فلوریست انتخاب‌شده دیگر فعال نیست؛ فرد دیگری را انتخاب کنید."})
    factor = str(factor_code or "").translate(DIGITS).strip().upper()
    if not re.fullmatch(r"[A-Z0-9-]{1,40}", factor):
        raise ValidationError({"factor_code": "شماره فاکتور را با عدد یا حروف انگلیسی وارد کنید."})
    try:
        amount = Decimal(str(price))
        valid_price = amount.is_finite() and amount == amount.to_integral_value() and 0 < amount <= 999_999_999_999
    except (InvalidOperation, ValueError):
        valid_price = False
    if not valid_price:
        raise ValidationError({"price": "قیمت را به تومان و با عدد مثبت وارد کنید."})
    if production_type not in StudioProduct.ProductionType.values:
        raise ValidationError({"production_type": "نوع تولید معتبر نیست."})
    if product_type not in StudioProduct.ProductType.values:
        raise ValidationError({"product_type": "نوع محصول معتبر نیست."})
    if not image:
        raise ValidationError({"image": "عکس محصول را انتخاب کنید."})
    if len(notes or "") > 2000:
        raise ValidationError({"notes": "یادداشت باید حداکثر ۲۰۰۰ نویسه باشد."})
    daily = production_type == StudioProduct.ProductionType.DAILY
    category, group_id = _daily_configuration() if daily else (None, None)
    try:
        normalized = normalize_admin_image(image)
    except ImageUploadError as error:
        raise ValidationError({"image": str(error)}) from None
    record = StudioProduct(
        florist=florist, created_by=user, submission_key=key,
        factor_code=factor, product_type=product_type, production_type=production_type,
        price=amount, image=normalized, source=StudioProduct.Source.PORTAL, notes=notes or "",
    )
    try:
        with transaction.atomic():
            # Lock in a stable order when two colleagues register for each other.
            locked = {item.pk: item for item in Florist.objects.select_for_update().filter(
                pk__in={uploader.pk, florist.pk}).order_by("pk")}
            actor = locked.get(uploader.pk)
            if actor is None or not actor.is_active or actor.user_id != user.pk:
                raise PermissionDenied
            owner = locked.get(florist.pk)
            if owner is None or not owner.is_active:
                raise ValidationError({"florist": "فلوریست انتخاب‌شده دیگر فعال نیست؛ فرد دیگری را انتخاب کنید."})
            existing = _existing_submission(key, user, owner)
            if existing:
                return existing, False
            if StudioProduct.objects.filter(factor_code__iexact=factor).exists():
                raise ValidationError({"factor_code": "این شماره فاکتور قبلاً ثبت شده است."})
            record.full_clean()
            record.save()
            if daily:
                # The public projection shares the normalized stored file. Neither
                # the invoice, author, nor private notes enter its public fields.
                product = Product.objects.create(
                    name=record.get_product_type_display(), slug=f"studio-{key.hex}",
                    category=category, catalog_scope=Product.CatalogScope.SAME_DAY,
                    pricing_type=Product.PricingType.FIXED, price=amount,
                    cover_image=record.image.name, publish_status=Product.PublishStatus.PUBLISHED,
                    status=Product.Status.AVAILABLE, stock_status=Product.StockStatus.IN_STOCK,
                )
                record.product = product
                record.save(update_fields=["product", "updated_at"])
                StudioDelivery.objects.create(record=record, action=StudioDelivery.Action.PUBLISH,
                                              chat_id=group_id)
                storage, name = record.image.storage, record.image.name
                transaction.on_commit(lambda: create_responsive_image_variants(storage, name))
    except IntegrityError:
        _clean_failed_file(record)
        # A concurrent retry may win the unique key while this request waited.
        existing = _existing_submission(key, user, florist)
        if existing:
            return existing, False
        raise ValidationError({"factor_code": "این شماره فاکتور قبلاً ثبت شده است."}) from None
    except Exception:
        _clean_failed_file(record)
        raise
    return record, True
