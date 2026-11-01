"""Customer phone/password pages, independent from staff authentication."""
from django import forms
from django.contrib import messages
from django.contrib.auth import login, logout, update_session_auth_hash
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.debug import sensitive_post_parameters
from . import customer_auth


class PhoneForm(forms.Form):
    phone = forms.CharField(label="شماره موبایل", max_length=32,
        widget=forms.TextInput(attrs={"type": "tel", "autocomplete": "username", "inputmode": "tel", "dir": "ltr"}))

    def clean_phone(self):
        return customer_auth.normalize_phone(self.cleaned_data["phone"])


class LoginForm(PhoneForm):
    password = forms.CharField(label="رمز عبور", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))


class RegistrationForm(PhoneForm):
    first_name = forms.CharField(label="نام", max_length=150, required=False,
        widget=forms.TextInput(attrs={"autocomplete": "given-name"}))
    password1 = forms.CharField(label="رمز عبور", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="حداقل ۸ نویسه؛ از رمز رایج یا کاملاً عددی استفاده نکنید.")
    password2 = forms.CharField(label="تکرار رمز عبور", strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}))

    def clean_password1(self):
        password = self.cleaned_data["password1"]
        validate_password(password)
        return password

    def clean(self):
        data = super().clean()
        if data.get("password1") and data.get("password2") and data["password1"] != data["password2"]:
            self.add_error("password2", "رمزهای عبور یکسان نیستند.")
        return data


def context(**kwargs):
    return {"active_nav": "shop", "meta_title": "حساب مشتری | فروشگاه زاد", "robots_content": "noindex,nofollow", "suppress_default_hero": True, **kwargs}


def _establish_session(request, user, destination):
    cart = request.session.get("shop_cart", {})
    nonce = request.session.get("shop_checkout_nonce")
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    request.session["shop_cart"] = cart
    if nonce:
        request.session["shop_checkout_nonce"] = nonce
    messages.success(request, "وارد حساب فروشگاه شدید.")
    return redirect(destination)


@never_cache
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def login_view(request):
    destination = customer_auth.safe_destination(request, request.POST.get("next", request.GET.get("next")))
    if customer_auth.is_customer(request.user):
        return redirect(destination)
    form = LoginForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            user = customer_auth.login_customer(request, form.cleaned_data["phone"], form.cleaned_data["password"])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _establish_session(request, user, destination)
    return render(request, "main/shop/login.html", context(form=form, next=destination))


@never_cache
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def register(request):
    destination = customer_auth.safe_destination(request, request.POST.get("next", request.GET.get("next")))
    if customer_auth.is_customer(request.user):
        return redirect(destination)
    form = RegistrationForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        try:
            user = customer_auth.register_customer(form.cleaned_data["phone"], form.cleaned_data["password1"],
                form.cleaned_data.get("first_name", ""), customer_auth.requester_ip(request))
        except ValidationError as error:
            form.add_error(None, error)
        else:
            return _establish_session(request, user, destination)
    return render(request, "main/shop/register.html", context(form=form, next=destination))


@never_cache
@require_http_methods(["GET"])
def account(request):
    if not customer_auth.is_customer(request.user):
        return redirect(reverse("customer_login") + "?next=" + reverse("customer_account"))
    from .models import ShopOrder
    orders = ShopOrder.objects.filter(customer=request.user).order_by("-created_at")[:50]
    return render(request, "main/shop/account.html", context(orders=orders, is_shop_customer=True))


@never_cache
@require_POST
def logout_view(request):
    cart = request.session.get("shop_cart", {})
    logout(request)
    request.session["shop_cart"] = cart
    return redirect("shop_home")


@never_cache
@require_http_methods(["GET", "POST"])
@sensitive_post_parameters()
def change_password(request):
    if not customer_auth.is_customer(request.user):
        return redirect("customer_login")
    form = PasswordChangeForm(request.user, request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "رمز عبور تغییر کرد.")
        return redirect("customer_account")
    return render(request, "main/shop/change_password.html", context(form=form, is_shop_customer=True))
