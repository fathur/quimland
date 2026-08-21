from django.contrib import admin, messages
from django.contrib.admin.forms import AdminPasswordChangeForm
from django.contrib.auth import update_session_auth_hash
from django.shortcuts import redirect, render
from django.urls import path


def profile_view(request):
    """
    The currently logged-in user's own account page.

    Shows their identity (name, username, email, linked resident info) and
    lets them change their own password via ``AdminPasswordChangeForm``.
    Linked from the "Welcome, <name>" text in the admin header.
    """
    user = request.user

    if request.method == 'POST':
        form = AdminPasswordChangeForm(user, request.POST)
        if form.is_valid():
            form.save()
            # Saving a new password rotates the session auth hash, which would
            # otherwise log the user out of their own change-password request.
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Your password was updated successfully.')
            return redirect('admin:profile')
    else:
        form = AdminPasswordChangeForm(user)

    name = user.get_full_name() or user.username
    initials = ''.join(part[0].upper() for part in name.split()[:2]) or name[:2].upper()

    context = {
        **admin.site.each_context(request),
        'title': 'My Profile',
        'password_form': form,
        'properties': getattr(user, 'properties', None),
        'display_name': name,
        'avatar_initials': initials,
        'avatar_hue': hash(name) % 360,
    }
    return render(request, 'admin/profile.html', context)


_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path('profile/', admin.site.admin_view(profile_view), name='profile'),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls
