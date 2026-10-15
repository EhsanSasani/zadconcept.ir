from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from .account_forms import AccountForm, TechnicalFloristLinkForm
from .account_roles import ROLE_CHOICES, assigned_roles, editable_account
from .account_service import save_account, save_technical_florist_link, archive_account
from .account_roles import ROLE_PERMISSIONS
from .models import StudioAccountArchive
from .studio_access import require_studio_permission
from .studio_views import _base


@never_cache
@login_required(login_url='studio_login')
@require_GET
def index(request):
    require_studio_permission(request, 'manage_studio_accounts')
    users = get_user_model().objects.order_by('username').prefetch_related('groups__permissions', 'user_permissions')
    archived = request.GET.get('archived') == '1'
    users = users.filter(studio_archive__isnull=not archived)
    query = request.GET.get('q', '').strip()[:100]
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query)
                             | Q(last_name__icontains=query) | Q(email__icontains=query))
    page = Paginator(users, 20).get_page(request.GET.get('page'))
    labels = dict(ROLE_CHOICES)
    rows = [{'account': user, 'roles': [labels[role] for role in assigned_roles(user)],
             'editable': editable_account(user) and not archived,
             'technical': not editable_account(user),
             'protection': protection_details(user)} for user in page]
    return render(request, 'main/pages/accounts/index.html', {
        **_base(request, 'accounts'), 'rows': rows, 'page': page, 'q': query, 'archived':archived,
        'operational_rows':[row for row in rows if not row['technical']],
        'technical_rows':[row for row in rows if row['technical']]})


def protection_details(user):
    if user.is_superuser:
        return {'title':'مدیر کل سایت','description':'به همهٔ مجوزهای سایت و پنل مدیریت فنی دسترسی دارد. نقش‌های مدیریتی، فروش و خرید به‌صورت سراسری در دسترس‌اند؛ ورود فلوریست نیازمند پروفایل فعال است.'}
    permissions = {f'{p.content_type.app_label}.{p.codename}':str(p.name)
        for p in user.user_permissions.select_related('content_type')}
    for group in user.groups.prefetch_related('permissions__content_type'):
        permissions.update({f'{p.content_type.app_label}.{p.codename}':str(p.name) for p in group.permissions.all()})
    special = [label for key,label in sorted(permissions.items()) if key not in ROLE_PERMISSIONS]
    return {'title':'دسترسی به مدیریت فنی' if user.is_staff else 'حساب دارای مجوز ویژه',
        'description':'اجازهٔ ورود به Django Admin دارد؛ عملیات مجاز را مجوزهای اختصاص‌داده‌شده تعیین می‌کنند.' if user.is_staff else 'مجوزهایی خارج از نقش‌های معمول پنل دارد؛ ویرایش آن نیازمند مدیریت فنی است.',
        'permissions':special}


@never_cache
@login_required(login_url='studio_login')
@require_http_methods(['GET', 'POST'])
def edit(request, pk=None):
    require_studio_permission(request, 'manage_studio_accounts')
    user = get_object_or_404(get_user_model(), pk=pk) if pk else None
    if user and (not editable_account(user) or StudioAccountArchive.objects.filter(user=user).exists()):
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


@never_cache
@login_required(login_url='studio_login')
@require_POST
def delete(request, pk):
    require_studio_permission(request, 'manage_studio_accounts')
    user = get_object_or_404(get_user_model(), pk=pk)
    if not editable_account(user):
        raise PermissionDenied
    error = None
    try:
        if request.POST.get('confirm') != 'yes':
            raise ValidationError('حذف حساب و بستن ورود را تأیید کنید.')
        archive_account(actor=request.user,user_id=pk,expected_version=request.POST.get('version',''),
            reason=request.POST.get('reason',''))
    except ValidationError as exc:
        error = ' '.join(exc.messages)
    else:
        messages.success(request, 'حساب از فهرست جاری حذف و ورود آن بسته شد؛ سوابق در بایگانی محفوظ‌اند.')
        return redirect('studio_accounts')
    return render(request,'main/pages/accounts/form.html',{
        **_base(request,'accounts'),'account':user,'form':AccountForm(user=user),'delete_error':error},status=400)


@never_cache
@login_required(login_url='studio_login')
@require_http_methods(['GET','POST'])
def technical_florist_link(request, pk):
    require_studio_permission(request, 'manage_studio_accounts')
    if not request.user.is_superuser:
        raise PermissionDenied
    user = get_object_or_404(get_user_model(), pk=pk)
    if editable_account(user):
        raise PermissionDenied
    form = TechnicalFloristLinkForm(request.POST if request.method == 'POST' else None, user=user)
    if request.method == 'POST' and form.is_valid():
        try:
            save_technical_florist_link(actor=request.user, user_id=user.pk, data=form.cleaned_data)
        except (ValidationError, IntegrityError) as error:
            form.add_error(None, error if isinstance(error,ValidationError) else 'اتصال پروفایل تغییر کرده؛ صفحه را تازه کنید.')
        else:
            messages.success(request, 'اتصال فلوریست ذخیره شد؛ مجوزها و اطلاعات فنی حساب محفوظ‌اند.')
            return redirect('studio_accounts')
    return render(request, 'main/pages/accounts/florist_link.html', {
        **_base(request,'accounts'), 'form':form, 'account':user}, status=400 if form.is_bound and form.errors else 200)
