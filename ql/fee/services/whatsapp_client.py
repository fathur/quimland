import requests
from django.conf import settings


class WhatsAppAPIError(Exception):
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self.payload = payload
        super().__init__(f'WhatsApp API error {status_code}: {payload}')


def _post_message(payload):
    phone_number_id = settings.WHATSAPP_PHONE_NUMBER_ID
    access_token = settings.WHATSAPP_ACCESS_TOKEN
    api_version = settings.WHATSAPP_API_VERSION

    url = f'https://graph.facebook.com/{api_version}/{phone_number_id}/messages'
    response = requests.post(
        url,
        headers={'Authorization': f'Bearer {access_token}'},
        json={'messaging_product': 'whatsapp', **payload},
        timeout=10,
    )

    if not response.ok:
        raise WhatsAppAPIError(response.status_code, response.json())

    return response.json()


def send_text_message(to, body, preview_url=False):
    """Send a plain-text WhatsApp message via the Meta Cloud API.

    `to` is the recipient's phone number in international format without
    a leading '+' (e.g. '628123456789'). Returns the parsed JSON response,
    which includes the outbound message id (`messages[0]['id']`).

    Only deliverable within the 24-hour customer service window (i.e. the
    recipient messaged this business number recently) — otherwise use
    `send_template_message` with an approved template.
    """
    return _post_message({
        'to': to,
        'type': 'text',
        'text': {'body': body, 'preview_url': preview_url},
    })


def send_template_message(to, template_name, language_code='en_US', body_params=None, header_params=None):
    """Send an approved WhatsApp message template via the Meta Cloud API.

    Required to business-initiate a conversation outside the 24-hour
    customer service window. `body_params` / `header_params` are positional
    text substitutions (`{{1}}`, `{{2}}`, ...) for the template's body and
    header components, respectively — each only needed if that component
    has variables.
    """
    components = []
    if header_params:
        components.append({
            'type': 'header',
            'parameters': [{'type': 'text', 'text': param} for param in header_params],
        })
    if body_params:
        components.append({
            'type': 'body',
            'parameters': [{'type': 'text', 'text': param} for param in body_params],
        })

    template = {'name': template_name, 'language': {'code': language_code}}
    if components:
        template['components'] = components

    return _post_message({'to': to, 'type': 'template', 'template': template})
