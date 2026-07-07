// payment_inline.js — disabled, kept for reference
/*
(function ($) {
    'use strict';

    const TARIFF_URL = '/admin/ql/paymentbatch/tariff-lookup/';

    function getUserId() {
        return $('#id_user').val();
    }

    function fetchAndFill(row) {
        const kind = row.find('select[name$="-kind"]').val();
        const period = row.find('input[name$="-period"]').val();
        const userId = getUserId();
        const nominalInput = row.find('input[name$="-nominal"]');

        if (!kind || !period || !userId) return;

        $.getJSON(TARIFF_URL, { user_id: userId, kind: kind, period: period }, function (data) {
            if (data.nominal !== null) {
                nominalInput.val(data.nominal);
                nominalInput.closest('td').show();
            }
            if (data.warning) {
                alert('Tariff warning: ' + data.warning);
            }
        });
    }

    function isNewRow(row) {
        return row.find('input[name$="-id"]').val() === '';
    }

    function initRow(row) {
        if (isNewRow(row)) {
            row.find('input[name$="-nominal"]').closest('td').hide();
        }
        row.find('select[name$="-kind"], input[name$="-period"]').on('change', function () {
            fetchAndFill(row);
        });
    }

    $(document).ready(function () {
        $('.dynamic-payments').each(function () {
            initRow($(this));
        });
    });

    // Django 4.1+: native CustomEvent (jQuery .on() does not catch this)
    document.addEventListener('formset:added', function (event) {
        const detail = event.detail || {};
        const formsetName = detail.formsetName;
        if (!formsetName || formsetName === 'payments') {
            initRow($(detail.row || event.target));
        }
    });

    // Older Django: jQuery-triggered event fallback
    $(document).on('formset:added', function (event, $row, formsetName) {
        if (!formsetName || formsetName === 'payments') {
            initRow($row);
        }
    });

}(django.jQuery));
*/
