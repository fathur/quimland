"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/6.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import path, include

from ql.fee.services.auth_backends import PhoneOrUsernameAuthForm
from ql.fee.views import serve_secure_media, WhatsAppWebhookView

admin.site.site_header = 'Quim Land'
admin.site.site_title  = 'Quim Land'
admin.site.index_title = 'Quim Land'
admin.site.login_form  = PhoneOrUsernameAuthForm

# debug_toolbar.toolbar.debug_toolbar_urls() no-ops unless DEBUG=True, which
# we deliberately keep False in production. Registering the urls directly
# here instead lets DEBUG_TOOLBAR_ENABLED (see settings.py) control it, with
# visibility further gated to staff by ql.debug_toolbar_hooks.show_toolbar_to_staff.
_debug_toolbar_urls = (
    [path('__debug__/', include('debug_toolbar.urls'))]
    if settings.DEBUG_TOOLBAR_ENABLED else []
)

urlpatterns = [
    path('secure-media/<path:path>', serve_secure_media, name='secure_media'),

    path('api/whatsapp/webhook/', WhatsAppWebhookView.as_view(), name='whatsapp_webhook'),
] + static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT) + _debug_toolbar_urls + [
    # admin.site.urls is mounted at the root '' and its final_catch_all_view
    # matches any remaining path — it MUST stay last, or it swallows every
    # URL listed after it (media/, __debug__/, etc.) before they're ever tried.
    path('', admin.site.urls),
    # path("", include('mcp_server.urls')),
]

handler400 = 'ql.fee.views.error_400'
handler403 = 'ql.fee.views.error_403'
handler404 = 'ql.fee.views.error_404'
