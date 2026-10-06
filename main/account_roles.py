"""Three operational roles; technical/admin permissions are outside this editor."""
import hashlib
import json

from .models import Florist

MANAGER_PERMISSIONS = frozenset({
    "view_studioproduct", "add_studioproduct", "change_studioproduct",
    "view_florist", "add_florist", "change_florist", "manage_studio_accounts",
    "change_studioingestionissue",
})
SALES_PERMISSIONS = frozenset({"use_sales_workspace"})
ROLE_PERMISSIONS = {f"main.{name}" for name in MANAGER_PERMISSIONS | SALES_PERMISSIONS}
ROLE_GROUPS = {"manager": ("Studio managers", MANAGER_PERMISSIONS),
               "sales": ("Studio sales", SALES_PERMISSIONS)}
ROLE_CHOICES = [("manager", "مدیر"), ("sales", "فروش"), ("florist", "فلوریست")]


def assigned_roles(user):
    # Show assigned roles even when login is disabled.
    permissions = set(user.user_permissions.values_list('content_type__app_label', 'codename'))
    permissions.update(user.groups.values_list('permissions__content_type__app_label', 'permissions__codename'))
    roles = []
    if user.is_superuser or ('main', 'view_studioproduct') in permissions:
        roles.append('manager')
    if user.is_superuser or ('main', 'use_sales_workspace') in permissions:
        roles.append('sales')
    if Florist.objects.filter(user=user, is_active=True).exists():
        roles.append('florist')
    return roles


def editable_account(user):
    if user.is_staff or user.is_superuser:
        return False
    permissions = {f'{app}.{code}' for app, code in user.user_permissions.values_list(
        'content_type__app_label', 'codename')}
    permissions.update(f'{app}.{code}' for app, code in user.groups.values_list(
        'permissions__content_type__app_label', 'permissions__codename') if code)
    return not (permissions - ROLE_PERMISSIONS)


def account_snapshot(user):
    return {"username": user.username, "first_name": user.first_name, "last_name": user.last_name,
            "email": user.email, "is_active": user.is_active, "roles": assigned_roles(user),
            "florist": Florist.objects.filter(user=user).values_list('pk', flat=True).first()}


def account_version(user):
    data = {**account_snapshot(user), 'password': user.password, 'staff': user.is_staff,
            'superuser': user.is_superuser, 'groups': list(user.groups.order_by('pk').values_list('pk', flat=True)),
            'permissions': list(user.user_permissions.order_by('pk').values_list('pk', flat=True))}
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()
