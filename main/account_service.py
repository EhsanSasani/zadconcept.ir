import json

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from .account_roles import (MANAGER_PERMISSIONS, ROLE_GROUPS, ROLE_PERMISSIONS, account_snapshot,
                            account_version, editable_account, assigned_manager_permissions)
from .models import Florist


@transaction.atomic
def save_account(*, actor, data, user_id=None):
    User = get_user_model()
    # Stable order also serializes a manager editing their own account.
    locked = {user.pk: user for user in User.objects.select_for_update().filter(
        pk__in=[actor.pk] + ([user_id] if user_id else [])).order_by('pk')}
    author = locked.get(actor.pk)
    if author is None or not author.is_active or not author.has_perm('main.manage_studio_accounts'):
        raise PermissionDenied
    user = locked.get(user_id) if user_id else User()
    if user_id and (user is None or not editable_account(user)):
        raise PermissionDenied
    if user_id and data['version'] != account_version(user):
        raise ValidationError('این حساب در صفحهٔ دیگری تغییر کرده است؛ صفحه را تازه کنید.')
    roles = set(data['roles'])
    if user_id == actor.pk and (not data['is_active'] or 'manager' not in roles):
        raise ValidationError('نمی‌توانید ورود یا دسترسی مدیریت حساب خودتان را غیرفعال کنید.')
    if User.objects.filter(username__iexact=data['username']).exclude(pk=user_id).exists():
        raise ValidationError('این نام کاربری قبلاً استفاده شده است.')
    before = account_snapshot(user) if user_id else {}
    # Saving names/passwords must not silently promote a legacy limited manager.
    retained_manager = None
    if user_id and 'manager' in roles and 'manager' in before['roles']:
        retained_manager = assigned_manager_permissions(user)
    for field in ('username', 'first_name', 'last_name', 'email', 'is_active'):
        setattr(user, field, data[field])
    if data.get('password1'):
        user.set_password(data['password1'])
    user.save()

    # Normalize operational roles from old direct grants and role-only groups.
    # Groups without permissions and unrelated user data remain untouched.
    for group in user.groups.prefetch_related('permissions__content_type'):
        permissions = {f'{p.content_type.app_label}.{p.codename}' for p in group.permissions.all()}
        if permissions and permissions <= ROLE_PERMISSIONS:
            user.groups.remove(group)
    user.user_permissions.remove(*Permission.objects.filter(
        content_type__app_label='main', codename__in=[name.split('.')[1] for name in ROLE_PERMISSIONS]))
    for role, (name, codenames) in ROLE_GROUPS.items():
        if role not in roles:
            continue
        if role == 'manager' and retained_manager is not None and retained_manager != MANAGER_PERMISSIONS:
            user.user_permissions.add(*Permission.objects.filter(
                content_type__app_label='main', codename__in=retained_manager))
            continue
        group, _ = Group.objects.get_or_create(name=name)
        existing = {f'{p.content_type.app_label}.{p.codename}' for p in group.permissions.select_related('content_type')}
        expected = {f'main.{code}' for code in codenames}
        if existing - expected:
            raise ValidationError('گروه دسترسی تنظیمات فنی متفاوتی دارد؛ مدیر فنی باید آن را بررسی کند.')
        permissions = Permission.objects.filter(content_type__app_label='main', codename__in=codenames)
        if permissions.count() != len(codenames):
            raise ValidationError('مجوزهای سیستم کامل نیستند؛ با مدیر فنی هماهنگ کنید.')
        group.permissions.add(*permissions)
        user.groups.add(group)

    selected = data.get('florist') if 'florist' in roles else None
    linked = Florist.objects.select_for_update().filter(user=user).first()
    if selected:
        selected = Florist.objects.select_for_update().filter(pk=selected.pk).first()
        if selected is None or not selected.is_active or selected.user_id not in (None, user.pk):
            raise ValidationError('این پروفایل دیگر برای اتصال در دسترس نیست؛ صفحه را تازه کنید.')
    if 'florist' in roles and selected is None:
        if linked:
            selected = linked
            selected.is_active = True
        else:
            # No products or history are created by granting a role.
            import uuid
            selected = Florist(name=user.get_full_name() or user.username,
                              code='user-' + uuid.uuid4().hex[:18], is_active=True)
    if linked and (selected is None or selected.pk != linked.pk):
        linked.user = None
        linked.save(update_fields=['user', 'updated_at'])
    if selected:
        selected.user = user
        selected.save()
    after = account_snapshot(user)
    LogEntry.objects.create(user_id=author.pk, content_type=ContentType.objects.get_for_model(User),
        object_id=str(user.pk), object_repr=user.username, action_flag=CHANGE if user_id else ADDITION,
        change_message=json.dumps({'source': 'studio_accounts', 'before': before, 'after': after,
                                   'password_changed': bool(data.get('password1'))}, ensure_ascii=False))
    return user
