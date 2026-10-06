from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods

from .account_forms import AccountForm
from .account_roles import ROLE_CHOICES, assigned_roles, editable_account
from .account_service import save_account
from .studio_access import require_studio_permission
from .studio_views import _base


@never_cache
@login_required(login_url='studio_login')
@require_GET
def index(request):
    require_studio_permission(request, 'manage_studio_accounts')
    users = get_user_model().objects.order_by('username').prefetch_related('groups__permissions', 'user_permissions')
    query = request.GET.get('q', '').strip()[:100]
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query)
                             | Q(last_name__icontains=query) | Q(email__icontains=query))
    page = Paginator(users, 20).get_page(request.GET.get('page'))
    labels = dict(ROLE_CHOICES)
    rows = [{'account': user, 'roles': [labels[role] for role in assigned_roles(user)],
             'editable': editable_account(user)} for user in page]
    return render(request, 'main/pages/accounts/index.html', {
        **_base(request, 'accounts'), 'rows': rows, 'page': page, 'q': query})


@never_cache
@login_required(login_url='studio_login')
@require_http_methods(['GET', 'POST'])
def edit(request, pk=None):
    require_studio_permission(request, 'manage_studio_accounts')
    user = get_object_or_404(get_user_model(), pk=pk) if pk else None
    if user and not editable_account(user):
        raise PermissionDenied
    form = AccountForm(request.POST if request.method == 'POST' else None, user=user)
    if request.method == 'POST' and form.is_valid():
        try:
            saved = save_account(actor=request.user, data=form.cleaned_data, user_id=pk)
        except ValidationError as error:
            form.add_error(None, error)
        except IntegrityError:
            form.add_error(None, 'اطلاعات با ثبت دیگری تداخل دارد؛ نام کاربری و پروفایل را بررسی کنید.')
        else:
            if saved.pk == request.user.pk and form.cleaned_data.get('password1'):
                update_session_auth_hash(request, saved)
            messages.success(request, 'تغییرات حساب ذخیره شد.' if pk else 'حساب کاربری ساخته شد.')
            return redirect('studio_accounts')
    return render(request, 'main/pages/accounts/form.html', {
        **_base(request, 'accounts'), 'form': form, 'account': user})
