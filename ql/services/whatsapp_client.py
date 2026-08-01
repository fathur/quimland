import requests
from django.conf import settings


class WhatsAppAPIError(Exception):
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f'WhatsApp API error {status_code}: {payload}')


def send_text_message(to, body, preview_url=False):
    """Send a plain-text WhatsApp message via the Meta Cloud API.

    `to` is the recipient's phone number in international format without
    a leading '+' (e.g. '628123456789'). Returns the parsed JSON response,
    which includes the outbound message id (`messages[0]['id']`).
    """
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    api_version = settings.WHATSAPP_API_VERSION

    url = f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages'
    response = requests.post(
        url,
        headers={'Authorization': f'Bearer {access_token}'},
        json={
            'messaging_product': 'whatsapp',
            'to': to,
            'type': 'text',
            'text': {'body': body, 'preview_url': preview_url},
        },
        timeout=10,
    )

    if not response.ok:
        raise WhatsAppAPIError(response.status_code, response.json())

    return response.json()
