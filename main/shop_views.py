"""Public and staff views for products explicitly assigned to the shop."""
from functools import wraps
from uuid import UUID, uuid4

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .customer_auth import is_customer
from .models import Category, Product, ShopOrder, ShopConfiguration
from .shop_forms import ShopCheckoutForm, ShopProductForm, ShopConfigurationForm
from .page_context import _default_context
from . import shop_service, shop_payments

CART_KEY = "shop_cart"
NONCE_KEY = "shop_checkout_nonce"


def can_manage_shop(user):
    return bool(user.is_authenticated and user.is_active and
                (user.is_superuser or user.has_perm("main.manage_shop")))


def shop_manager_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path(), reverse("studio_login"))
        if not can_manage_shop(request.user):
            raise PermissionDenied
        return view(request, *args, **kwargs)
    return never_cache(wrapped)


def _cart(request):
    value = request.session.get(CART_KEY, {})
    return value if isinstance(value, dict) else {}


def _configuration():
    return ShopConfiguration.objects.filter(pk=1).first() or ShopConfiguration()


def _render(request, template, context=None, status=200):
    context = context or {}
    base = {}
    if template in {"home", "product"}:
        product = context.get("product")
        base = _default_context(request, page_type="shop", active_nav="shop",
            meta_title=context.get("meta_title", "فروشگاه زاد"),
            meta_description=product.seo_description if product else "محصولات فروشگاه زاد؛ بررسی موجودی و قیمت، انتخاب محصول و خرید آنلاین با دریافت حضوری یا ارسال در مشهد.",
            schema_type="CollectionPage" if template == "home" else "WebPage",
            social_image=product.cover_image if product else None, suppress_default_hero=True)
    base.update({"active_nav": "shop", "suppress_default_hero": True,
            "meta_title": "فروشگاه زاد", "page_type": "shop",
            "is_shop_customer": is_customer(request.user), "shop_configuration": _configuration()})
    if request.path.startswith("/panel/"):
        base["robots_content"] = "noindex,nofollow"
    base.update(context)
    return render(request, f"main/shop/{template}.html", base, status=status)


def _customer_redirect(request):
    return redirect_to_login(request.get_full_path(), reverse("customer_login"))


@require_GET
def shop_home(request):
    products = Product.objects.for_shop().published().select_related("category", "shop_inventory")
    categories = Category.objects.filter(products__in=products).distinct().order_by("section", "sort_order", "name")
    query = request.GET.get("q", "").strip()[:100]
    category = request.GET.get("category", "")
    if query:
        products = products.filter(Q(name__icontains=query) | Q(product_code__icontains=query))
    if category.isascii() and category.isdigit() and 0 < len(category) <= 18:
        products = products.filter(category_id=int(category))
    else:
        category = ""
    page = Paginator(products, 18).get_page(request.GET.get("page"))
    return _render(request, "home", {"products": page, "categories": categories,
        "query": query, "selected_category": category, "result_count": page.paginator.count})


@require_GET
def product_detail(request, slug):
    product = get_object_or_404(Product.objects.for_shop().published().select_related("category", "shop_inventory"), slug=slug)
    return _render(request, "product", {"product": product, "meta_title": f"{product.display_name} | فروشگاه زاد"})


@never_cache
@require_GET
def cart(request):
    snapshot = shop_service.cart_snapshot(_cart(request))
    shown_ids = {str(line.product.pk) for line in snapshot.lines}
    unavailable_items = [{"id": key} for key in _cart(request) if key not in shown_ids]
    return _render(request, "cart", {"snapshot": snapshot, "unavailable_items": unavailable_items,
        "meta_title": "سبد خرید | فروشگاه زاد", "robots_content": "noindex,nofollow"})


@never_cache
@require_POST
def cart_update(request):
    current = _cart(request).copy()
    action = request.POST.get("action", "set")
    if action == "clear":
        request.session[CART_KEY] = {}
        request.session.pop(NONCE_KEY, None)
        messages.success(request, "سبد خرید خالی شد.")
        return redirect("shop_cart")
    try:
        product_id = str(int(request.POST.get("product_id", "")))
        quantity = int(request.POST.get("quantity", "1").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")))
        if action not in {"add", "set", "remove"} or quantity < 0 or quantity > 99:
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        messages.error(request, "تعداد معتبر بین ۱ تا ۹۹ وارد کنید.")
        return redirect("shop_cart")
    if action == "remove" or quantity == 0:
        current.pop(product_id, None)
    else:
        if action == "add":
            try:
                quantity += int(current.get(product_id, 0))
            except (ValueError, TypeError):
                pass
        proposed = {**current, product_id: quantity}
        snapshot = shop_service.cart_snapshot(proposed)
        if snapshot.errors:
            for error in snapshot.errors:
                messages.error(request, error)
            return redirect("shop_cart")
        current = proposed
    request.session[CART_KEY] = current
    request.session.pop(NONCE_KEY, None)
    messages.success(request, "سبد خرید به‌روز شد.")
    return redirect("shop_cart")


def _nonce(request):
    try:
        nonce = UUID(str(request.session[NONCE_KEY]))
        existing = ShopOrder.objects.filter(nonce=nonce, customer=request.user).first()
        if existing and (existing.status == "cancelled" or existing.released_at):
            request.session.pop(NONCE_KEY, None)
            raise ValueError
        return nonce
    except (KeyError, ValueError, TypeError, AttributeError):
        nonce = uuid4()
        request.session[NONCE_KEY] = str(nonce)
        return nonce


@never_cache
@require_http_methods(["GET", "POST"])
def checkout(request):
    if not is_customer(request.user):
        return _customer_redirect(request)
    current_nonce = _nonce(request)
    completed = ShopOrder.objects.filter(nonce=current_nonce, customer=request.user, status="paid").first()
    if completed:
        return redirect("shop_order_detail", order_id=completed.pk)
    snapshot = shop_service.cart_snapshot(_cart(request))
    if not snapshot.lines or snapshot.errors:
        for error in snapshot.errors:
            messages.error(request, error)
        return redirect("shop_cart")
    configuration = _configuration()
    selected_mode = request.POST.get("fulfillment", request.GET.get("fulfillment", "pickup" if configuration.pickup_enabled else "delivery"))
    shipping_fee = 0
    quote_error = None
    try:
        shipping_fee = shop_service.fulfillment_quote(selected_mode)
    except shop_service.ShopError as error:
        quote_error = str(error)
    total_toman = snapshot.total_toman + shipping_fee
    initial = {"expected_total": total_toman, "recipient_phone": request.user.customer_profile.phone,
               "recipient_name": request.user.get_full_name(), "fulfillment": selected_mode}
    form = ShopCheckoutForm(request.POST or None, initial=initial, configuration=configuration)
    enabled = shop_payments.payment_enabled()
    is_review = request.method == "POST" and request.POST.get("action") == "review"
    if is_review:
        # A quote needs only a fulfillment choice. Keep the draft without
        # validating personal fields or calling order/payment services.
        draft = {name: request.POST.get(name, initial.get(name, "")) for name in form.fields}
        draft["expected_total"] = total_toman
        form = ShopCheckoutForm(initial=draft, configuration=configuration)
    elif request.method == "POST" and form.is_valid():
        if quote_error:
            form.add_error(None, quote_error)
        elif form.cleaned_data["expected_total"] != total_toman:
            form.add_error(None, "مبلغ سفارش یا روش دریافت تغییر کرده است. مبلغ نهایی زیر را بررسی کنید و دوباره ادامه دهید.")
            form.data = form.data.copy()
            form.data["expected_total"] = total_toman
        elif not enabled:
            form.add_error(None, "پرداخت آنلاین فعلاً در دسترس نیست. برای هماهنگی خرید با زاد تماس بگیرید.")
        else:
            try:
                order = shop_service.create_order(customer=request.user, cart=_cart(request), nonce=_nonce(request),
                    expected_total=form.cleaned_data["expected_total"],
                    recipient_name=form.cleaned_data["recipient_name"],
                    recipient_phone=form.cleaned_data["recipient_phone"],
                    customer_note=form.cleaned_data["customer_note"], fulfillment=form.cleaned_data["fulfillment"],
                    recipient_address=form.cleaned_data["recipient_address"], recipient_city="مشهد")
            except shop_service.ShopError as error:
                form.add_error(None, str(error))
                if error.code == "price_changed":
                    # Show the current amount and require another explicit submit.
                    snapshot = shop_service.cart_snapshot(_cart(request))
                    try:
                        shipping_fee = shop_service.fulfillment_quote(form.cleaned_data["fulfillment"])
                    except shop_service.ShopError as quote_failure:
                        quote_error = str(quote_failure)
                        form.add_error(None, quote_error)
                        shipping_fee = 0
                    total_toman = snapshot.total_toman + shipping_fee
                    form.data = form.data.copy()
                    form.data["expected_total"] = total_toman
            else:
                try:
                    payment_url = shop_payments.start_payment(order=order, callback_url=request.build_absolute_uri(reverse("payment_verify")))
                except shop_service.ShopError as error:
                    messages.error(request, str(error))
                    return redirect("shop_order_detail", order_id=order.pk)
                return redirect(payment_url)
    _nonce(request)
    return _render(request, "checkout", {"snapshot": snapshot, "form": form, "payment_enabled": enabled,
        "shipping_fee_toman": shipping_fee, "total_toman": total_toman, "selected_fulfillment": selected_mode,
        "quote_error": quote_error,
        "quote_reviewed": is_review and not quote_error,
        "meta_title": "بررسی و پرداخت | فروشگاه زاد", "robots_content": "noindex,nofollow"})


@never_cache
@require_GET
def order_detail(request, order_id):
    if not is_customer(request.user):
        return _customer_redirect(request)
    order = get_object_or_404(ShopOrder.objects.prefetch_related("lines"), pk=order_id, customer=request.user)
    return _render(request, "order", {"order": order, "meta_title": "پیگیری سفارش | فروشگاه زاد",
        "robots_content": "noindex,nofollow"})


@never_cache
@require_POST
def order_cancel(request, order_id):
    if not is_customer(request.user):
        return _customer_redirect(request)
    get_object_or_404(ShopOrder, pk=order_id, customer=request.user)
    try:
        order = shop_service.cancel_order(customer=request.user, order_id=order_id)
        if request.session.get(NONCE_KEY) == str(order.nonce):
            request.session.pop(NONCE_KEY, None)
        messages.success(request, "سفارش لغو شد.")
    except shop_service.ShopError as error:
        messages.error(request, str(error))
    return redirect("shop_order_detail", order_id=order_id)


@never_cache
@require_GET
def payment_callback(request):
    try:
        order = shop_payments.verify_payment(authority=request.GET.get("Authority", ""), callback_status=request.GET.get("Status", ""))
    except shop_service.ShopError as error:
        return _render(request, "payment_result", {"result_error": str(error), "robots_content": "noindex,nofollow"})
    if is_customer(request.user) and order.customer_id == request.user.pk:
        if order.status == "paid":
            # A delayed/replayed callback must not discard newer selections.
            if request.session.get(NONCE_KEY) == str(order.nonce):
                ordered_cart = {str(line.product_id): line.quantity for line in order.lines.all()}
                if _cart(request) == ordered_cart:
                    request.session[CART_KEY] = {}
                request.session.pop(NONCE_KEY, None)
        return redirect("shop_order_detail", order_id=order.pk)
    return redirect_to_login(reverse("shop_order_detail", kwargs={"order_id": order.pk}), reverse("customer_login"))


@shop_manager_required
@require_GET
def shop_manage(request):
    products = Product.objects.for_shop().select_related("category", "shop_inventory")
    query = request.GET.get("q", "").strip()[:100]
    if query:
        products = products.filter(Q(name__icontains=query) | Q(product_code__icontains=query))
    return _render(request, "manage", {"products": Paginator(products, 30).get_page(request.GET.get("page")),
        "query": query, "active": "products"})


@shop_manager_required
@require_http_methods(["GET", "POST"])
def shop_manage_product(request, pk=None):
    product = get_object_or_404(Product.objects.for_shop().select_related("shop_inventory"), pk=pk) if pk else None
    form = ShopProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                product = form.save()
                shop_service.adjust_inventory(actor=request.user, product_id=product.pk,
                    quantity=form.cleaned_data["inventory_quantity"], expected_version=form.cleaned_data["inventory_version"],
                    reason=form.cleaned_data["inventory_reason"] or ("ذخیره اطلاعات محصول؛ بدون تغییر تعداد" if pk else "ثبت اولیه محصول فروشگاه"))
        except shop_service.ShopError as error:
            form.add_error(None, str(error))
        else:
            messages.success(request, "محصول و موجودی فروشگاه ذخیره شد.")
            return redirect("shop_manage_product", pk=product.pk)
    history = product.shop_stock_audits.select_related("actor")[:15] if product and product.pk else []
    return _render(request, "manage_product", {"form": form, "product": product, "history": history, "active": "products"})


@shop_manager_required
@require_GET
def shop_manage_orders(request):
    orders = ShopOrder.objects.select_related("customer").prefetch_related("lines").order_by("-created_at")
    status = request.GET.get("status", "")
    if status in {"pending", "paid", "cancelled", "review"}:
        orders = orders.filter(status=status)
    else:
        status = ""
    return _render(request, "manage_orders", {"orders": Paginator(orders, 30).get_page(request.GET.get("page")),
        "selected_status": status, "active": "orders"})


@shop_manager_required
@require_http_methods(["GET", "POST"])
def shop_manage_settings(request):
    configuration = _configuration()
    form = ShopConfigurationForm(request.POST or None, instance=configuration)
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            # Order creation locks this same row before quoting fulfillment.
            current, _ = ShopConfiguration.objects.select_for_update().get_or_create(pk=1)
            form = ShopConfigurationForm(request.POST, instance=current)
            if form.is_valid():
                form.save()
                messages.success(request, "روش‌های دریافت و هزینه ارسال ذخیره شد.")
                return redirect("shop_manage_settings")
    return _render(request, "manage_settings", {"form": form, "active": "settings"})
