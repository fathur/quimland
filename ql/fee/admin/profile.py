from django import forms
from django.contrib import admin, messages
from django.contrib.admin.forms import AdminPasswordChangeForm
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.shortcuts import redirect, render
from django.urls import path

from ql.fee.models import UserProperty
from ql.fee.services.utils import normalize_phone

User = get_user_model()


class AccountForm(forms.ModelForm):
    """The logged-in user editing their own identity fields.

    ``phone`` lives on the linked ``UserProperty`` — the field is only shown
    when the user actually has one, and is written back to it on save.
    """

    phone = forms.CharField(
        required=False, label='Phone number',
        help_text='Include country code, e.g. +628123456789',
    )

    class Meta:
        model = User
        fields = ['username', 'first_name', 'last_name', 'email']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._properties = getattr(self.instance, 'properties', None)
        if self._properties is None:
            self.fields.pop('phone')
        else:
            self.fields['phone'].initial = self._properties.phone
        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', 'vTextField')
            if name in ('username', 'email'):
                field.required = True

    def clean_email(self):
        return self.cleaned_data['email'].strip()

    def clean_phone(self):
        raw = (self.cleaned_data.get('phone') or '').strip()
        if not raw:
            return ''
        phone = normalize_phone(raw)
        clash = (
            UserProperty.objects
            .filter(phone=phone)
            .exclude(pk=self._properties.pk)
            .exists()
        )
        if clash:
            raise forms.ValidationError('That phone number is already used by another resident.')
        return phone

    def save(self, commit=True):
        user = super().save(commit=commit)
        if self._properties is not None and 'phone' in self.cleaned_data:
            new_phone = self.cleaned_data['phone']
            if new_phone != self._properties.phone:
                self._properties.phone = new_phone
                self._properties.save(update_fields=['phone'])
        return user


def _profile_context(request, **extra):
    user = request.user
    name = user.get_full_name() or user.username
    initials = ''.join(part[0].upper() for part in name.split()[:2]) or name[:2].upper()
    return {
        **admin.site.each_context(request),
        'properties': getattr(user, 'properties', None),
        'display_name': name,
        'avatar_initials': initials,
        'avatar_hue': hash(name) % 360,
        **extra,
    }


def profile_view(request):
    """
    The currently logged-in user's own account overview.

    Shows their identity (name, username, email, linked resident info). Editing
    is split off into /profile/account/ and /profile/change-password/.
    Linked from the "Welcome, <name>" text in the admin header.
    """
    context = _profile_context(request, title='My Profile', profile_section='overview')
    return render(request, 'admin/profile.html', context)


def change_password_view(request):
    """Let the logged-in user change their own password."""
    user = request.user

    if request.method == 'POST':
        form = AdminPasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            # Saving a new password rotates the session auth hash, which would
            # otherwise log the user out of their own change-password request.
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password was updated successfully.')
            return redirect('admin:profile_change_password')
    else:
        form = AdminPasswordChangeForm(user)

    context = _profile_context(
        request, title='Change password', password_form=form, profile_section='password',
    )
    return render(request, 'admin/profile_change_password.html', context)


def account_view(request):
    """Let the logged-in user edit their own username, name, email and phone."""
    user = request.user

    if request.method == 'POST':
        form = AccountForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, 'Your account information was updated successfully.')
            return redirect('admin:profile_account')
    else:
        form = AccountForm(instance=user)

    context = _profile_context(
        request, title='Account settings', form=form, profile_section='account',
    )
    return render(request, 'admin/profile_account.html', context)


_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path('profile/', admin.site.admin_view(profile_view), name='profile'),
        path('profile/account/', admin.site.admin_view(account_view), name='profile_account'),
        path('profile/change-password/', admin.site.admin_view(change_password_view), name='profile_change_password'),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls
