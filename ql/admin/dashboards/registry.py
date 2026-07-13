from django.contrib import admin
from django.urls import path

from .earmarked import earmarked_dashboard_view
from .funds import funds_dashboard_view
from .payments import payments_dashboard_view
from .wallets import wallet_dashboard_view


# ---------------------------------------------------------------------------
# URL registration
# ---------------------------------------------------------------------------
_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path(
            'payments-dashboard/',
            admin.site.admin_view(payments_dashboard_view),
            name='payments_dashboard',
        ),
        path(
            'funds-dashboard/',
            admin.site.admin_view(funds_dashboard_view),
            name='funds_dashboard',
        ),
        path(
            'wallet-dashboard/',
            admin.site.admin_view(wallet_dashboard_view),
            name='wallet_dashboard',
        ),
        path(
            'earmarked-dashboard/',
            admin.site.admin_view(earmarked_dashboard_view),
            name='earmarked_dashboard',
        ),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls


# ---------------------------------------------------------------------------
# Sidebar injection
# ---------------------------------------------------------------------------
_DASHBOARD_APP = {
    'name': 'Dashboard',
    'app_label': 'ql_dashboard',
    'app_url': '/admin/payments-dashboard/',
    'has_module_perms': True,
    'models': [
        {
            'name': 'Transactions',
            'object_name': 'TransactionsDashboard',
            'admin_url': '/admin/payments-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Funds overview',
            'object_name': 'FundsDashboard',
            'admin_url': '/admin/funds-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Wallets overview',
            'object_name': 'WalletDashboard',
            'admin_url': '/admin/wallet-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Earmarked funds',
            'object_name': 'EarmarkedDashboard',
            'admin_url': '/admin/earmarked-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
        {
            'name': 'Scan Receipt',
            'object_name': 'ReceiptScan',
            'admin_url': '/admin/receipt-scan/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        },
    ],
}

_TRANSACTIONS_APP = {
    'name': 'Transactions',
    'app_label': 'ql_transactions',
    'app_url': '/admin/ql/incometransaction/',
    'has_module_perms': True,
    'models': [
        {
            'name': 'Income',
            'object_name': 'IncomeTransaction',
            'admin_url': '/admin/ql/incometransaction/',
            'add_url': '/admin/ql/incometransaction/add/',
            'perms': {'add': True, 'change': True, 'delete': True, 'view': True},
        },
        {
            'name': 'Expenses',
            'object_name': 'ExpenseTransaction',
            'admin_url': '/admin/ql/expensetransaction/',
            'add_url': '/admin/ql/expensetransaction/add/',
            'perms': {'add': True, 'change': True, 'delete': True, 'view': True},
        },
        {
            'name': 'All Transactions',
            'object_name': 'AllTransaction',
            'admin_url': '/admin/ql/alltransaction/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': False, 'delete': False, 'view': True},
        },
    ],
}

_original_each_context = admin.site.__class__.each_context


def _each_context(self, request):
    ctx = _original_each_context(self, request)
    filtered_apps = []
    proxy_labels = {'incometransaction', 'expensetransaction', 'transfertransaction', 'alltransaction'}
    for app in ctx.get('available_apps', []):
        if app.get('app_label') == 'ql':
            models = [m for m in app['models'] if m['object_name'].lower() not in proxy_labels]
            if models:
                filtered_apps.append({**app, 'models': models})
        else:
            filtered_apps.append(app)
    ctx['available_apps'] = [_DASHBOARD_APP, _TRANSACTIONS_APP] + filtered_apps
    return ctx


admin.site.__class__.each_context = _each_context
