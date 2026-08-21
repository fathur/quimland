(function () {
    'use strict';

    // Fetches each unloaded box's real image URL and swaps it in — fired
    // immediately for whatever boxes are currently in the DOM (not on scroll),
    // since the point is keeping the R2 signed-URL cost off the page's initial
    // render, not deferring until the user scrolls to it. Several boxes'
    // fetches run concurrently, so wall-clock cost is roughly one call, not
    // the sum of all of them.
    function hydrate(root) {
        var thumbs = root.querySelectorAll('.receipt-thumb[data-url-endpoint]');
        thumbs.forEach(function (thumb) {
            if (thumb.dataset.hydrating) return;
            thumb.dataset.hydrating = '1';

            fetch(thumb.dataset.urlEndpoint, { credentials: 'same-origin' })
                .then(function (res) {
                    if (!res.ok) throw new Error('bad response');
                    return res.json();
                })
                .then(function (data) {
                    var img = thumb.querySelector('.receipt-image');
                    var placeholder = thumb.querySelector('.receipt-placeholder');
                    if (!img || !data.url) throw new Error('no url');
                    img.addEventListener('load', function () {
                        placeholder.hidden = true;
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
        var placeholder = thumb.querySelector('.receipt-placeholder');
        if (!placeholder) return;
        placeholder.textContent = 'Failed to load';
        placeholder.classList.add('receipt-placeholder--error');
        var spinner = placeholder.querySelector('.receipt-spinner');
        if (spinner) spinner.remove();
    }

    document.addEventListener('DOMContentLoaded', function () {
        var grid = document.getElementById('receipt-grid');
        if (!grid) return;

        hydrate(grid);

        var btn = document.getElementById('receipt-load-more-btn');
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
                    Array.prototype.forEach.call(wrapper.children, function (child) {
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
