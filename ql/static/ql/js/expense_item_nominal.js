// Keeps a transaction item's readonly nominal field in sync with price × quantity.
// Uses event delegation on document so newly added inline rows are covered
// without needing to hook Django's formset:added event.
(function () {
    'use strict';

    function recalc(input) {
        var match = input.name.match(/^(.*)-(price|quantity)$/);
        if (!match) return;

        var prefix = match[1];
        var priceInput    = document.querySelector('[name="' + prefix + '-price"]');
        var quantityInput = document.querySelector('[name="' + prefix + '-quantity"]');
        var nominalInput  = document.querySelector('[name="' + prefix + '-nominal"]');
        if (!priceInput || !nominalInput) return;

        var price    = parseFloat(priceInput.value);
        var quantity = quantityInput && quantityInput.value !== '' ? parseFloat(quantityInput.value) : 1;
        if (isNaN(price) || isNaN(quantity)) {
            nominalInput.value = '';
            return;
        }
        nominalInput.value = (price * quantity).toFixed(2);
    }

    document.addEventListener('input', function (event) {
        recalc(event.target);
    });
}());
