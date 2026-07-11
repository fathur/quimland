from django.contrib import admin
from django.db.models import Count
from django.utils.html import format_html

from ..models import DueNote, DueNoteProof


class DueNoteProofInline(admin.TabularInline):
    model = DueNoteProof
    extra = 3
    fields = ['image', 'preview']
    readonly_fields = ['preview']

    @admin.display(description='Preview')
    def preview(self, obj):
        if not obj or not obj.image:
            return '—'
        return format_html(
            '<a href="{}" target="_blank">'
            '<img src="{}" style="max-height:90px;border-radius:6px;"></a>',
            obj.image.url, obj.image.url,
        )


@admin.register(DueNote)
class DueNoteAdmin(admin.ModelAdmin):
    list_display  = ['user', 'fund', 'period', 'reason', 'note_short', 'proof_icon', 'creator', 'updated_at']
    list_filter   = ['reason', 'fund', 'period']
    search_fields = ['user__username', 'user__first_name', 'user__last_name', 'note']
    autocomplete_fields = ['user', 'fund']
    readonly_fields = ['creator', 'created_at', 'updated_at']
    inlines = [DueNoteProofInline]

    def get_queryset(self, request):
        return super().get_queryset(request).annotate(_proof_count=Count('proofs'))

    def get_fields(self, request, obj=None):
        fields = ['user', 'fund', 'period', 'reason', 'note']
        if obj:
            fields += ['creator', 'created_at', 'updated_at']
        return fields

    def save_model(self, request, obj, form, change):
        if not obj.creator_id:
            obj.creator = request.user
        super().save_model(request, obj, form, change)

    @admin.display(description='Note')
    def note_short(self, obj):
        return (obj.note[:60] + '…') if len(obj.note) > 60 else obj.note

    @admin.display(description='Proof', ordering='_proof_count')
    def proof_icon(self, obj):
        count = getattr(obj, '_proof_count', 0)
        if not count:
            return '—'
        return format_html('📎 {}', count)
