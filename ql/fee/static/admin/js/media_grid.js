/*
 * Shared by any ModelAdmin using LazyMediaGridAdmin (ql/fee/admin/mixins.py).
 * Generic — knows nothing about Receipt or Asset specifically, only the
 * .media-* class/data-attribute contract that grid fragment templates emit.
 */
(function () {
    'use strict';

    // Fetches each unhydrated box's real image URL and swaps it in — fired
    // immediately for whatever boxes are currently in the DOM (not on scroll),
    // since the point is keeping the storage-backend URL cost off the page's
    // initial render, not deferring until the user scrolls to it. Several
    // boxes' fetches run concurrently, so wall-clock cost is roughly one
    // call, not the sum of all of them.
    function hydrate(root) {
        var thumbs = root.querySelectorAll('.media-thumb[data-url-endpoint]');
        thumbs.forEach(function (thumb) {
            if (thumb.dataset.hydrating) return;
            thumb.dataset.hydrating = '1';

            fetch(thumb.dataset.urlEndpoint, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) throw new Error('bad response');
                    return res.json();
                })
                .then(function (data) {
                    var img = thumb.querySelector('.media-image');
                    var placeholder = thumb.querySelector('.media-placeholder');
                    if (!img || !data.url) throw new Error('no url');
                    img.addEventListener('load', function () {
                        placeholder.remove();
                        img.hidden = false;
                    });
                    img.addEventListener('error', function () {
                        markFailed(thumb);
                    });
                    img.src = data.url;
                })
                .catch(function () {
                    markFailed(thumb);
                });
        });
    }

    function markFailed(thumb) {
        var placeholder = thumb.querySelector('.media-placeholder');
        if (!placeholder) return;
        placeholder.textContent = 'Failed to load';
        placeholder.classList.remove('media-placeholder--loading');
        placeholder.classList.add('media-placeholder--error');
    }

    document.addEventListener('DOMContentLoaded', function () {
        var grid = document.getElementById('media-grid');
        if (!grid) return;

        hydrate(grid);

        var btn = document.getElementById('media-load-more-btn');
        if (!btn) return;

        var nextPage = parseInt(grid.dataset.nextPage, 10) || 2;
        var baseQuery = grid.dataset.queryString || '?';

        btn.addEventListener('click', function () {
            btn.disabled = true;
            var originalText = btn.textContent;
            btn.textContent = 'Loading…';

            var params = new URLSearchParams(baseQuery.replace(/^\?/, ''));
            params.set('p', nextPage);
            var url = grid.dataset.loadMoreUrl + '?' + params.toString();

            fetch(url, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) throw new Error('bad response');
                    return res.json();
                })
                .then(function (data) {
                    var wrapper = document.createElement('div');
                    wrapper.innerHTML = data.html;
                    // Array.from() snapshots the live HTMLCollection first —
                    // appendChild() below moves each node out of wrapper,
                    // which would otherwise shift a live collection's indices
                    // mid-loop and skip every other element.
                    Array.from(wrapper.children).forEach(function (child) {
                        grid.appendChild(child);
                    });
                    hydrate(grid);
                    nextPage += 1;

                    if (data.has_more) {
                        btn.disabled = false;
                        btn.textContent = originalText;
                    } else {
                        btn.remove();
                    }
                })
                .catch(function () {
                    btn.disabled = false;
                    btn.textContent = 'Load more (retry)';
                });
        });
    });
})();
