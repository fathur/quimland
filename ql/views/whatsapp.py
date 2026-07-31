import hashlib
import hmac
import logging

from django.conf import settings
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

logger = logging.getLogger('ql.views.whatsapp')


class WhatsAppWebhookView(APIView):
    """Meta Cloud API webhook for WhatsApp Business — verification handshake
    (GET) and inbound message/status events (POST).

    Trust comes from the X-Hub-Signature-256 check, not Django auth/CSRF —
    Meta calls this endpoint directly with no session or CSRF token.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    parser_classes = [JSONParser]

    def get(self, request):
        mode = request.query_params.get('hub.mode')
        token = request.query_params.get('hub.verify_token')
        challenge = request.query_params.get('hub.challenge', '')

        verify_token = settings.WHATSAPP_VERIFY_TOKEN
        if mode == 'subscribe' and verify_token and token == verify_token:
            return Response(int(challenge) if challenge.isdigit() else challenge)

        return Response(status=403)

    def post(self, request):
        if not self._verify_signature(request):
            return Response(status=403)

        logger.info('WhatsApp webhook event: %s', request.data)

        return Response({'status': 'ok'})

    def _verify_signature(self, request):
        """Validate X-Hub-Signature-256 against WHATSAPP_APP_SECRET so only
        Meta-signed deliveries are accepted."""
        secret = settings.WHATSAPP_APP_SECRET
        if not secret:
            return False

        header = request.headers.get('X-Hub-Signature-256', '')
        if not header.startswith('sha256='):
            return False

        expected = hmac.new(secret.encode('utf-8'), request.body, hashlib.sha256).hexdigest()
        return hmac.compare_digest(header[len('sha256='):], expected)
