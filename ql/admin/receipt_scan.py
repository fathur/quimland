import base64
import json
import os
from decimal import Decimal, InvalidOperation

from django.contrib import admin
from django.contrib.auth.models import User
from django.db import transaction as db_transaction
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import render
from django.urls import path, reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from ..models import Receipt, Transaction

# ---------------------------------------------------------------------------
# Prompt placeholder — edit this constant to tune extraction behavior.
# ---------------------------------------------------------------------------
RECEIPT_EXTRACTION_PROMPT = (
    "You are a receipt data extraction assistant. Analyze the bank transfer receipt image "
    "and extract structured information accurately.\n\n"
    "Extract these fields:\n"
    "- bank_name: The sending bank short name (e.g. BCA, BNI, BRI, Mandiri, GoPay, OVO, Dana)\n"
    "- sender: Full name of the sender as shown on the receipt\n"
    "- receiver: Full name of the receiver as shown on the receipt\n"
    "- nominal: Transfer amount as a decimal number with two decimal places (e.g. 150000.00)\n"
    "- sent_at: Transfer date and time formatted as yyyy-MM-dd HH:mm:ss using 24-hour clock\n\n"
    "Rules:\n"
    "- Return ONLY a raw JSON object. No markdown, no backticks, no explanation.\n"
    "- Use null for any field that cannot be determined from the image.\n"
    "- Start your response with { and end with }.\n\n"
    'Example: {"bank_name": "BCA", "sender": "Budi Santoso", "receiver": "Quim Land", '
    '"nominal": 500000.00, "sent_at": "2026-06-15 09:30:00"}'
)

CLAUDE_MODEL = 'claude-haiku-4-5'

_MEDIA_TYPES = {
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.png': 'image/png',
    '.gif': 'image/gif',
    '.webp': 'image/webp',
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _search_users(sender_name):
    if not sender_name:
        return []
    parts = [p for p in sender_name.split() if p]
    if not parts:
        return []
    qs = User.objects.filter(is_active=True)
    for part in parts:
        qs = qs.filter(Q(first_name__icontains=part) | Q(last_name__icontains=part))
    return list(qs[:10])


# ---------------------------------------------------------------------------
# Views
# ---------------------------------------------------------------------------
def receipt_scan_page(request):
    users = list(
        User.objects.filter(is_active=True)
        .select_related('properties')
        .order_by('first_name', 'last_name')
    )
    context = {
        **admin.site.each_context(request),
        'title': 'Scan Receipt',
        'users': users,
    }
    return render(request, 'admin/receipt_scan.html', context)


def extract_receipt_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    image_file = request.FILES.get('file')
    if not image_file:
        return JsonResponse({'error': 'No image file provided'}, status=400)

    image_data = base64.standard_b64encode(image_file.read()).decode('utf-8')
    ext = os.path.splitext(image_file.name)[1].lower()
    media_type = _MEDIA_TYPES.get(ext, 'image/jpeg')

    from anthropic import Anthropic
    client = Anthropic(api_key=os.environ['CLAUDE_API_KEY'])

    api_response = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=512,
        system=[{
            'type': 'text',
            'text': RECEIPT_EXTRACTION_PROMPT,
            'cache_control': {'type': 'ephemeral'},
        }],
        messages=[
            {
                'role': 'user',
                'content': [{
                    'type': 'image',
                    'source': {
                        'type': 'base64',
                        'media_type': media_type,
                        'data': image_data,
                    },
                }],
            },
            {'role': 'assistant', 'content': '{'},
        ],
    )

    try:
        extracted = json.loads('{' + api_response.content[0].text)
    except (json.JSONDecodeError, IndexError) as exc:
        return JsonResponse({'error': f'Could not parse Claude response: {exc}'}, status=502)

    matched = _search_users(extracted.get('sender') or '')
    extracted['matched_users'] = [
        {'id': u.id, 'name': u.get_full_name() or u.username}
        for u in matched
    ]

    return JsonResponse(extracted)


def user_search_view(request):
    q = request.GET.get('q', '').strip()
    users = _search_users(q)
    return JsonResponse({'users': [
        {'id': u.id, 'name': u.get_full_name() or u.username}
        for u in users
    ]})


def save_transaction_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    errors = {}

    user_id = request.POST.get('user_id', '').strip()
    if not user_id:
        errors['user_id'] = 'User is required.'

    paid_at_raw = request.POST.get('paid_at', '').strip()
    paid_at = None
    if not paid_at_raw:
        errors['paid_at'] = 'Paid at is required.'
    else:
        normalized = paid_at_raw.replace('T', ' ')
        if len(normalized) == 16:
            normalized += ':00'
        paid_at = parse_datetime(normalized)
        if paid_at is None:
            errors['paid_at'] = 'Invalid date/time.'
        elif timezone.is_naive(paid_at):
            paid_at = timezone.make_aware(paid_at)

    nominal_raw = request.POST.get('nominal', '').strip()
    nominal = None
    if not nominal_raw:
        errors['nominal'] = 'Nominal is required.'
    else:
        try:
            nominal = Decimal(nominal_raw)
        except InvalidOperation:
            errors['nominal'] = 'Invalid amount.'

    if errors:
        return JsonResponse({'errors': errors}, status=400)

    try:
        with db_transaction.atomic():
            # Receipt first — its save() compresses the image before storage.
            receipt_obj = None
            receipt_file = request.FILES.get('receipt')
            if receipt_file:
                receipt_obj = Receipt(user_id=user_id, image=receipt_file)
                receipt_obj.save()

            # Header-only Transaction (direction=IN). Fund/period line items are
            # added afterwards on the change page via the existing inline.
            trx = Transaction.objects.create(
                direction=Transaction.Direction.IN,
                nominal=nominal,
                occurred_at=paid_at,
                user_id=user_id,
                creator=request.user,
                receipt=receipt_obj,
            )
    except Exception as exc:
        return JsonResponse({'errors': {'__all__': str(exc)}}, status=400)

    return JsonResponse({
        'redirect': reverse('admin:ql_transaction_change', args=[trx.id]),
    })


# ---------------------------------------------------------------------------
# URL registration
# ---------------------------------------------------------------------------
_original_get_urls = admin.site.get_urls


def _get_urls():
    custom = [
        path(
            'receipt-scan/',
            admin.site.admin_view(receipt_scan_page),
            name='receipt_scan',
        ),
        path(
            'receipt-scan/extract/',
            admin.site.admin_view(extract_receipt_view),
            name='receipt_scan_extract',
        ),
        path(
            'receipt-scan/user-search/',
            admin.site.admin_view(user_search_view),
            name='receipt_scan_user_search',
        ),
        path(
            'receipt-scan/save/',
            admin.site.admin_view(save_transaction_view),
            name='receipt_scan_save',
        ),
    ]
    return custom + _original_get_urls()


admin.site.get_urls = _get_urls
