from django.contrib import admin
from django.shortcuts import render
from django.views import defaults as django_defaults


def _admin_styled_error(request, status, title, message):
    """Render a 4xx error inside the admin chrome for logged-in users only;
    anonymous visitors get Django's plain default error page."""
    if not request.user.is_authenticated:
        return None
    context = admin.site.each_context(request)
    context.update({'title': title, 'error_status': status, 'error_message': message})
    return render(request, 'admin/error.html', context, status=status)


def error_400(request, exception=None):
    return (
        _admin_styled_error(request, 400, 'Bad request', 'Your request could not be processed.')
        or django_defaults.bad_request(request, exception)
    )


def error_403(request, exception=None):
    return (
        _admin_styled_error(request, 403, 'Forbidden', 'You do not have permission to access this page.')
        or django_defaults.permission_denied(request, exception)
    )


def error_404(request, exception=None):
    return (
        _admin_styled_error(request, 404, 'Not found', 'The page you requested could not be found.')
        or django_defaults.page_not_found(request, exception)
    )
