"""Phone/password customer accounts with database-shared abuse limits."""
import re
import secrets
from ipaddress import ip_address
from datetime import timedelta
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import F
from django.urls import resolve, Resolver404, reverse
from django.utils import timezone
from django.utils.crypto import salted_hmac
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.debug import sensitive_variables
from .customer_models import CustomerLoginRate, CustomerProfile

DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
LOGIN_ERROR = "شماره موبایل یا رمز عبور درست نیست."


def requester_ip(request):
    """Trust Nginx's overwritten real-IP header only on the configured local hop."""
    remote_raw = request.META.get("REMOTE_ADDR", "") or ""
    try:
        remote = ip_address(remote_raw)
    except (ValueError, TypeError):
        remote = None
    local_proxy = not remote_raw or remote is not None and remote.is_loopback
    if getattr(settings, "SHOP_TRUST_PROXY_IP", False) is True and local_proxy:
        try:
            return str(ip_address(request.META.get("HTTP_X_REAL_IP", "")))
        except (ValueError, TypeError):
            pass
    return str(remote) if remote is not None else "unknown"


def normalize_phone(value):
    value = re.sub(r"[\s()\-]", "", str(value).translate(DIGITS))
    if value.startswith("0098"):
        value = "+98" + value[4:]
    if re.fullmatch(r"09[0-9]{9}", value):
        value = "+98" + value[1:]
    if not re.fullmatch(r"\+989[0-9]{9}", value):
        raise ValidationError("شماره موبایل ایران را با ۰۹ یا ‎+۹۸ وارد کنید.")
    return value


def is_customer(user):
    if not (user.is_authenticated and user.is_active) or user.is_staff or user.is_superuser:
        return False
    if user.groups.exists() or user.user_permissions.exists():
        return False
    from .models import Florist
    return (CustomerProfile.objects.filter(user=user).exists()
            and not Florist.objects.filter(user=user).exists())


def safe_destination(request, value):
    allowed = {"shop_home", "shop_cart", "shop_checkout", "shop_order_detail", "customer_account"}
    if value and url_has_allowed_host_and_scheme(value, allowed_hosts=set(), require_https=request.is_secure()):
        try:
            if value.startswith("/") and resolve(value.split("?", 1)[0]).url_name in allowed:
                return value
        except (Resolver404, ValueError):
            pass
    return reverse("customer_account")


def _quota(kind, value, window_seconds, limit, now):
    bucket = int(now.timestamp()) // window_seconds
    key = salted_hmac("zad.customer-rate", f"{kind}:{value}:{bucket}", algorithm="sha256").hexdigest()
    counter, _ = CustomerLoginRate.objects.get_or_create(
        key=key, defaults={"expires_at": now + timedelta(seconds=window_seconds * 2)})
    if not CustomerLoginRate.objects.filter(pk=counter.pk, count__lt=limit).update(count=F("count") + 1):
        raise ValidationError("تعداد تلاش‌ها زیاد شده؛ چند دقیقه بعد دوباره تلاش کنید.")


def _limit(phone, ip, kind):
    with transaction.atomic():
        _quota(kind + "-phone", phone, 300, 10, timezone.now())
        _quota(kind + "-ip", ip, 300, 40, timezone.now())


@sensitive_variables("password")
def register_customer(phone, password, first_name="", ip="unknown"):
    phone = normalize_phone(phone)
    _limit(phone, ip, "register")
    candidate = get_user_model()(username="customer_" + secrets.token_hex(16), first_name=first_name[:150])
    validate_password(password, user=candidate)
    try:
        with transaction.atomic():
            candidate.set_password(password)
            candidate.save()
            CustomerProfile.objects.create(user=candidate, phone=phone)
    except IntegrityError:
        raise ValidationError("ثبت‌نام با این شماره ممکن نیست؛ اگر حساب دارید وارد شوید یا با پشتیبانی تماس بگیرید.") from None
    return candidate


@sensitive_variables("password")
def login_customer(request, phone, password):
    phone = normalize_phone(phone)
    _limit(phone, requester_ip(request), "login")
    profile = CustomerProfile.objects.select_related("user").filter(phone=phone).first()
    username = profile.user.username if profile else "customer_missing_" + secrets.token_hex(16)
    user = authenticate(request=request, username=username, password=password)
    if not user or not is_customer(user):
        raise ValidationError(LOGIN_ERROR)
    return user
