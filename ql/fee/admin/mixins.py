from django.contrib.admin.options import IncorrectLookupParameters
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404
from django.template.loader import render_to_string
from django.urls import path


class LazyMediaGridAdmin:
    """
    Mix into a ModelAdmin to replace its changelist table with a boxed grid
    that lazy-loads each thumbnail via AJAX instead of rendering it inline for
    every row.

    Why: some storage backends' .url is expensive to compute (e.g. R2/S3
    presigned URLs — see ql/fee/admin/receipt.py for measured numbers, ~100ms
    each). Rendering that inline in list_display multiplies the cost by the
    page size. This mixin moves it off the page-render path: the grid ships
    placeholders first, then JS fetches each box's real URL (and each further
    "Load more" batch) asynchronously, off the critical path and in parallel.

    Usage:
        @admin.register(MyModel)
        class MyModelAdmin(LazyMediaGridAdmin, admin.ModelAdmin):
            list_per_page = 12
            grid_fragment_template = 'admin/fee/mymodel/_grid_items.html'

            def get_grid_image_url(self, obj):
                # The (possibly expensive) URL to lazy-load for this row, or
                # None if there's nothing previewable (skips the AJAX call
                # for that row entirely — render a static placeholder in the
                # fragment template instead, see receipt/_grid_items.html).
                return obj.image.url if obj.image else None

    Also needs:
      - admin/<app_label>/<model_name>/change_list.html, extending
        "admin/_media_grid_change_list.html" and filling its "grid_items"
        block (see templates/admin/fee/receipt/change_list.html).
      - grid_fragment_template itself: renders a batch of objects as
        <a class="media-box"> markup (see .media-* classes in
        admin/css/media_grid.css) — shared by both the initial page and every
        "Load more" append, so give each object a data-url-endpoint pointing
        at {% url 'admin:<app_label>_<model_name>_url_image' obj.pk %}
        (skip that attribute entirely for objects with nothing to preview).
    """

    #: Set on the subclass — see docstring above.
    grid_fragment_template = None

    def get_grid_image_url(self, obj):
        raise NotImplementedError(
            f'{type(self).__name__} must implement get_grid_image_url(obj) to use LazyMediaGridAdmin.'
        )

    def get_urls(self):
        opts = self.model._meta
        prefix = f'{opts.app_label}_{opts.model_name}'
        return [
            path(
                '<int:object_id>/url-image/',
                self.admin_site.admin_view(self.url_image_view),
                name=f'{prefix}_url_image',
            ),
            path(
                'load-more/',
                self.admin_site.admin_view(self.load_more_view),
                name=f'{prefix}_load_more',
            ),
        ] + super().get_urls()

    def url_image_view(self, request, object_id):
        if not self.has_view_permission(request):
            return JsonResponse({'error': 'forbidden'}, status=403)
        obj = get_object_or_404(self.get_queryset(request), pk=object_id)
        url = self.get_grid_image_url(obj)
        if not url:
            raise Http404('Nothing to preview for this object.')
        return JsonResponse({'url': url})

    def load_more_view(self, request):
        if not self.has_view_permission(request):
            return JsonResponse({'error': 'forbidden'}, status=403)
        try:
            cl = self.get_changelist_instance(request)
        except IncorrectLookupParameters:
            # e.g. a page number past the end — stale tab, tampered URL.
            return JsonResponse({'html': '', 'has_more': False})
        html = render_to_string(
            self.grid_fragment_template,
            {'object_list': cl.result_list},
            request=request,
        )
        has_more = cl.page_num < cl.paginator.num_pages
        return JsonResponse({'html': html, 'has_more': has_more})
