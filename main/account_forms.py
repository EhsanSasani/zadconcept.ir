from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.db.models import Q

from .account_roles import ROLE_CHOICES, account_version, assigned_roles
from .models import Florist


class AccountForm(forms.Form):
    version = forms.CharField(required=False, widget=forms.HiddenInput)
    username = forms.CharField(label='نام کاربری', max_length=150,
        widget=forms.TextInput(attrs={'dir': 'ltr', 'autocapitalize': 'none', 'autocomplete': 'off'}))
    first_name = forms.CharField(label='نام', max_length=150)
    last_name = forms.CharField(label='نام خانوادگی', max_length=150, required=False)
    email = forms.EmailField(label='ایمیل', max_length=254, required=False, widget=forms.EmailInput(attrs={'dir': 'ltr'}))
    roles = forms.MultipleChoiceField(label='فضاهای کاری', choices=ROLE_CHOICES,
        widget=forms.CheckboxSelectMultiple, required=False)
    florist = forms.ModelChoiceField(label='پروفایل فلوریست', required=False,
        queryset=Florist.objects.none(), empty_label='ساخت پروفایل جدید با نام این کاربر')
    is_active = forms.BooleanField(label='ورود به حساب فعال باشد', required=False, initial=True)
    password1 = forms.CharField(label='رمز عبور', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'dir': 'ltr'}))
    password2 = forms.CharField(label='تکرار رمز عبور', required=False, strip=False,
        widget=forms.PasswordInput(attrs={'autocomplete': 'new-password', 'dir': 'ltr'}))

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        if user:
            kwargs['initial'] = {**{field: getattr(user, field) for field in
                ('username', 'first_name', 'last_name', 'email', 'is_active')},
                'roles': assigned_roles(user), 'version': account_version(user),
                'florist': Florist.objects.filter(user=user, is_active=True).first()}
        super().__init__(*args, **kwargs)
        if user and 'manager' in assigned_roles(user):
            from .account_roles import MANAGER_PERMISSIONS, assigned_manager_permissions
            if assigned_manager_permissions(user) != MANAGER_PERMISSIONS:
                self.fields['roles'].help_text = 'دسترسی مدیریتی این حساب محدود است؛ با حفظ گزینهٔ مدیر، همان مجوزهای فعلی حفظ می‌شوند.'
        available = Q(user__isnull=True)
        if user:
            available |= Q(user=user)
        self.fields['florist'].queryset = Florist.objects.filter(available, is_active=True)
        if not user:
            self.fields['password1'].required = self.fields['password2'].required = True

    def clean_username(self):
        name = get_user_model().normalize_username(self.cleaned_data['username'])
        for validator in get_user_model()._meta.get_field('username').validators:
            validator(name)
        existing = get_user_model().objects.filter(username__iexact=name)
        if self.user:
            existing = existing.exclude(pk=self.user.pk)
        if existing.exists():
            raise ValidationError('این نام کاربری قبلاً استفاده شده است.')
        return name

    def clean(self):
        data = super().clean()
        if data.get('is_active') and not data.get('roles'):
            self.add_error('roles', 'برای حساب فعال، حداقل یک دسترسی انتخاب کنید.')
        password = data.get('password1')
        if password != data.get('password2'):
            self.add_error('password2', 'تکرار رمز عبور یکسان نیست.')
        if password:
            candidate = get_user_model()(**{key: data.get(key, '') for key in
                ('username', 'first_name', 'last_name', 'email')})
            try:
                validate_password(password, candidate)
            except ValidationError as error:
                self.add_error('password1', error)
        if self.user and not data.get('version'):
            raise ValidationError('صفحه را تازه کنید و دوباره تلاش کنید.')
        return data
