from django import forms
from django.contrib import admin, messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from ql.models import Report
from ql.reports import generate_report_pdf
from ql.utils import render_report_markdown


class ReportAdminForm(forms.ModelForm):
    class Meta:
        model = Report
        fields = ['title', 'content']
        widgets = {
            'content': forms.Textarea(attrs={'rows': 28, 'style': 'font-family: monospace; width: 100%;'}),
        }


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    form = ReportAdminForm
    list_display = ['title', 'fund', 'status', 'creator', 'created_at', 'completed_at', 'preview_link', 'file_link']
    list_filter = ['status', 'fund']
    search_fields = ['title', 'fund__name']
    readonly_fields = ['fund', 'file', 'creator', 'status', 'completed_at', 'created_at', 'updated_at', 'preview_link_field']
    actions = ['generate_pdf_action']

    fieldsets = [
        (None, {'fields': ['title', 'fund', 'status', 'preview_link_field']}),
        ('Content (Markdown)', {'fields': ['content']}),
        ('Generated PDF', {'fields': ['file', 'completed_at']}),
        ('Audit', {'fields': ['creator', 'created_at', 'updated_at'], 'classes': ['collapse']}),
    ]

    def has_add_permission(self, request):  # noqa: ARG002
        return False

    def get_urls(self):
        return [
            path(
                '<int:report_id>/preview/',
                self.admin_site.admin_view(self.preview_view),
                name='ql_report_preview',
            ),
            path(
                '<int:report_id>/generate-pdf/',
                self.admin_site.admin_view(self.generate_pdf_view),
                name='ql_report_generate_pdf',
            ),
        ] + super().get_urls()

    def preview_view(self, request, report_id):
        report = get_object_or_404(Report, pk=report_id)
        if not self.has_view_permission(request, report):
            self.message_user(request, 'You do not have permission to preview this report.', level=messages.ERROR)
            return redirect('admin:ql_report_changelist')
        content_html = render_report_markdown(report.content)
        return render(request, 'admin/ql/report/preview.html', {
            'report': report,
            'content_html': content_html,
        })

    def generate_pdf_view(self, request, report_id):
        report = get_object_or_404(Report, pk=report_id)
        if not self.has_change_permission(request, report):
            self.message_user(request, 'You do not have permission to generate this PDF.', level=messages.ERROR)
            return redirect('admin:ql_report_changelist')
        if report.status == Report.Status.PROCESSING:
            self.message_user(request, 'Laporan masih diproses.', level=messages.ERROR)
            return redirect('admin:ql_report_change', report.pk)
        generate_report_pdf(report)
        self.message_user(request, f'PDF untuk "{report}" berhasil dibuat.')
        return redirect('admin:ql_report_change', report.pk)

    @admin.action(description='Generate PDF from content')
    def generate_pdf_action(self, request, queryset):
        if not self.has_change_permission(request):
            self.message_user(request, 'You do not have permission to generate PDFs.', level=messages.ERROR)
            return
        generated, skipped = 0, 0
        for report in queryset:
            if report.status == Report.Status.PROCESSING:
                skipped += 1
                continue
            generate_report_pdf(report)
            generated += 1
        if generated:
            self.message_user(request, f'{generated} PDF berhasil dibuat.')
        if skipped:
            self.message_user(request, f'{skipped} laporan dilewati karena masih diproses.', level=messages.WARNING)

    @admin.display(description='Preview')
    def preview_link(self, obj):
        url = reverse('admin:ql_report_preview', args=[obj.pk])
        return format_html('<a href="{}" target="_blank">Preview</a>', url)

    @admin.display(description='Preview & generate')
    def preview_link_field(self, obj):
        if not obj.pk:
            return '—'
        preview_url = reverse('admin:ql_report_preview', args=[obj.pk])
        pdf_url = reverse('admin:ql_report_generate_pdf', args=[obj.pk])
        return format_html(
            '<a class="button" href="{}" target="_blank">Preview</a> '
            '<a class="button" href="{}">Generate PDF</a>',
            preview_url, pdf_url,
        )

    @admin.display(description='File')
    def file_link(self, obj):
        if not obj.file:
            return '—'
        return format_html('<a href="{}" target="_blank">View PDF</a>', obj.file.url)
