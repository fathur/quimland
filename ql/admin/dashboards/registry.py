from django.contrib import admin
from django.urls import path

from .earmarked import earmarked_dashboard_view
from .funds import funds_dashboard_view
from .income import income_dashboard_view
from .leaderboard import leaderboard_dashboard_view
from .outstanding import outstanding_dashboard_view
from .wallets import wallet_dashboard_view


# ---------------------------------------------------------------------------
# URL registration
# ---------------------------------------------------------------------------
_original_get_urls = admin.site.get_urls


def _get_urls():
    return [
        path(
            'income-dashboard/',
            admin.site.admin_view(income_dashboard_view),
            name='income_dashboard',
        ),
        path(
            'income-dashboard/outstanding',
            admin.site.admin_view(outstanding_dashboard_view),
            name='outstanding_dashboard',
        ),
        path(
            'leaderboard-dashboard/',
            admin.site.admin_view(leaderboard_dashboard_view),
            name='leaderboard_dashboard',
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
        # path(
        #     'earmarked-dashboard/',
        #     admin.site.admin_view(earmarked_dashboard_view),
        #     name='earmarked_dashboard',
        # ),
    ] + _original_get_urls()


admin.site.get_urls = _get_urls


# ---------------------------------------------------------------------------
# Sidebar injection
# ---------------------------------------------------------------------------
def _dashboard_app(request):
    models = []
    if request.user.has_perm('ql.view_alltransaction'):
        models.append({
            'name': 'Tariff Income Overview',
            'object_name': 'IncomeDashboard',
            'admin_url': '/income-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        })

    if request.user.has_perm('ql.view_alltransaction'):
        models.append({
            'name': 'Leaderboard',
            'object_name': 'LeaderboardDashboard',
            'admin_url': '/leaderboard-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        })

    if request.user.has_perm('ql.view_fund'):
        models.append({
            'name': 'Funds overview',
            'object_name': 'FundsDashboard',
            'admin_url': '/funds-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        })

    if request.user.has_perm('ql.view_wallet'):
        models.append({
            'name': 'Wallets overview',
            'object_name': 'WalletDashboard',
            'admin_url': '/wallet-dashboard/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        })

    models += [
        
    
        # {
        #     'name': 'Earmarked funds',
        #     'object_name': 'EarmarkedDashboard',
        #     'admin_url': '/earmarked-dashboard/',
        #     'add_url': None,
        #     'view_only': True,
        #     'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        # },
    ]
    if request.user.has_perm('ql.add_receipt') and request.user.has_perm('ql.add_incometransaction'):
        models.append({
            'name': 'Scan Receipt',
            'object_name': 'ReceiptScan',
            'admin_url': '/receipt-scan/',
            'add_url': None,
            'view_only': True,
            'perms': {'add': False, 'change': True, 'delete': False, 'view': True},
        })
    return {
        'name': 'Dashboard',
        'app_label': 'ql_dashboard',
        'app_url': '/income-dashboard/',
        'has_module_perms': True,
        'models': models,
    }


_TRANSACTIONS_MODELS = [
    # name, object_name, model_name, view_only
    ('Income',           'IncomeTransaction',  'incometransaction',  False),
    ('Expenses',         'ExpenseTransaction', 'expensetransaction', False),
    ('All Transactions', 'AllTransaction',     'alltransaction',     True),
]


def _model_perms(user, model_name):
    add    = user.has_perm(f'ql.add_{model_name}')
    change = user.has_perm(f'ql.change_{model_name}')
    delete = user.has_perm(f'ql.delete_{model_name}')
    view   = user.has_perm(f'ql.view_{model_name}') or change
    return {'add': add, 'change': change, 'delete': delete, 'view': view}


def _transactions_app(request):
    models = []
    for name, object_name, model_name, view_only in _TRANSACTIONS_MODELS:
        perms = _model_perms(request.user, model_name)
        if not any(perms.values()):
            continue
        models.append({
            'name': name,
            'object_name': object_name,
            'admin_url': f'/ql/{model_name}/',
            'add_url': f'/ql/{model_name}/add/' if perms['add'] and not view_only else None,
            'view_only': view_only,
            'perms': perms,
        })
    return {
        'name': 'Transactions',
        'app_label': 'ql_transactions',
        'app_url': '/ql/incometransaction/',
        'has_module_perms': bool(models),
        'models': models,
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

    injected = [_dashboard_app(request)]
    transactions_app = _transactions_app(request)
    if transactions_app['models']:
        injected.append(transactions_app)

    ctx['available_apps'] = injected + filtered_apps
    return ctx


admin.site.__class__.each_context = _each_context
