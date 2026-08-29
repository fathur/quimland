from django.contrib import admin

from ql.fee.admin.filters import SoftDeleteAdminMixin, SoftDeleteFilter, make_select_related_filter
from ql.messaging.models import Message


@admin.register(Message)
class MessageAdmin(SoftDeleteAdminMixin, admin.ModelAdmin):
    list_display   = ['id', 'recipient', 'preview', 'created_at']
    list_filter    = [SoftDeleteFilter, ('recipient', make_select_related_filter('properties'))]
    search_fields  = [
        'recipient__username', 'recipient__first_name', 'recipient__last_name',
        'content',
    ]
    ordering       = ['-created_at']
    autocomplete_fields = ['recipient']
    readonly_fields = ['created_at', 'updated_at', 'deleted_at']
    actions        = ['restore_selected']

    fieldsets = [
        (None, {'fields': ['recipient', 'content']}),
        ('Audit', {'fields': ['created_at', 'updated_at', 'deleted_at'], 'classes': ['collapse']}),
    ]

    def get_queryset(self, request):
        return super().get_queryset(request).select_related('recipient', 'recipient__properties')

    @admin.display(description='Content')
    def preview(self, obj):
        text = obj.content.replace('\n', ' ')
        return text if len(text) <= 80 else f'{text[:80]}…'

    @admin.action(description='Restore selected')
    def restore_selected(self, request, queryset):
        restored = queryset.restore()
        self.message_user(request, f'{restored} message(s) restored.')
