/* global $, toastr, GlpNumber */
(function () {
    'use strict';

    const URL_MAP = {
        get_glp_purchase_invoice_modal: () => window.GLP_URLS.invoiceModal,
        get_glp_purchase_programming_modal: () => window.GLP_URLS.programmingModal,
        get_glp_purchase_warehouse_modal: () => window.GLP_URLS.warehouseModal,
        get_glp_purchase_expense_modal: () => window.GLP_URLS.expenseModal,
    };

    const fmt = (v, d) => window.GlpNumber.fmt(v, d);
    const parseNum = (v) => window.GlpNumber.parse(v);

    window.showGlpModal = function (route, params) {
        const url = URL_MAP[route] ? URL_MAP[route]() : '/inventory/' + route + '/';
        $.ajax({
            url: url,
            type: 'GET',
            data: params || {},
            success: function (r) {
                $('#add-modal').html(r.form);
                $('#add-modal').modal('show');
                bindModalHandlers(route);
            },
            error: function (xhr) {
                toastr.error(xhr.responseJSON?.error || 'Error al cargar modal');
            },
        });
    };

    function bindAmtFields(selector, onWeightChange) {
        $(selector + ':not(.bound)').each(function () {
            const $el = $(this);
            const dec = parseInt($el.data('dec'), 10) || 2;
            $el.addClass('bound');
            $el.on('focus', function () {
                $el.val(parseNum($el.val()));
                this.select();
            });
            $el.on('blur', function () {
                const r = parseNum($el.val());
                $el.val(r === '' || isNaN(parseFloat(r)) ? '' : fmt(r, dec));
                if (onWeightChange) onWeightChange();
            });
            if ($el.hasClass('wh-w')) {
                $el.on('input', onWeightChange);
            }
        });
    }

    function bindModalHandlers(route) {
        if (route === 'get_glp_purchase_invoice_modal') bindInvoiceModal();
        if (route === 'get_glp_purchase_programming_modal') bindProgrammingModal();
        if (route === 'get_glp_purchase_warehouse_modal') bindWarehouseModal();
        if (route === 'get_glp_purchase_expense_modal') bindExpenseModal();
    }

    const IGV_RATE = 0.18;

    window.showPurchaseSummary = function (pk) {
        $.ajax({
            url: window.GLP_URLS.summaryModal,
            type: 'GET',
            data: { pk: pk },
            success: function (r) {
                $('#add-modal').html(r.form);
                $('#add-modal').modal('show');
            },
            error: function (xhr) {
                toastr.error(xhr.responseJSON?.error || 'Error al cargar resumen');
            },
        });
    };

    function getInvoiceCurrency() {
        return $('#inv-currency').val() || 'PEN';
    }

    function getExchangeRate() {
        if (getInvoiceCurrency() !== 'USD') return 1;
        const tc = parseFloat(parseNum($('#inv-exchange').val()));
        return tc > 0 ? tc : 0;
    }

    function toggleCurrencyFields() {
        const isUsd = getInvoiceCurrency() === 'USD';
        const curr = isUsd ? 'USD' : 'PEN';
        $('#inv-exchange-wrap').toggle(isUsd);
        $('.inv-cond-payment').toggleClass('glp-span-2', isUsd).toggleClass('glp-span-3', !isUsd);
        $('.inv-terminal-field').toggleClass('glp-span-3', isUsd).toggleClass('glp-span-4', !isUsd);
        $('#inv-detail-currency-label, .inv-curr-suffix').text(curr);
        if (!isUsd) {
            $('#inv-exchange').val('');
            $('#inv-pen-equiv').addClass('d-none');
        }
    }

    function calcInvoicePrices() {
        const qty = parseFloat(parseNum($('#inv-qty').val())) || 0;
        const total = parseFloat(parseNum($('#inv-total').val())) || 0;
        let igv = parseFloat(parseNum($('#inv-igv').val()));
        const isUsd = getInvoiceCurrency() === 'USD';
        const fx = getExchangeRate();

        if (qty > 0 && total > 0) {
            if (isNaN(igv) || igv === 0) {
                igv = total * IGV_RATE / (1 + IGV_RATE);
                if (!$('#inv-igv').is(':focus')) {
                    $('#inv-igv').val(fmt(igv, 2));
                }
            }
            const subtotal = total - igv;
            const unitExcl = subtotal / qty;
            const unitIncl = total / qty;

            $('#inv-unit-excl').text(fmt(unitExcl, 6));
            $('#inv-unit-incl').text(fmt(unitIncl, 6));
            $('#inv-subtotal').text(fmt(subtotal, 2));

            if (isUsd) {
                $('#inv-pen-equiv').removeClass('d-none');
                if (fx > 0) {
                    $('#inv-unit-excl-pen').text('S/ ' + fmt(unitExcl * fx, 6));
                    $('#inv-unit-incl-pen').text('S/ ' + fmt(unitIncl * fx, 6));
                    $('#inv-subtotal-pen').text('S/ ' + fmt(subtotal * fx, 2));
                    $('#inv-total-pen').text('S/ ' + fmt(total * fx, 2));
                } else {
                    $('#inv-unit-excl-pen, #inv-unit-incl-pen, #inv-subtotal-pen, #inv-total-pen').text('Ingrese T/C');
                }
            } else {
                $('#inv-pen-equiv').addClass('d-none');
            }
        } else {
            $('#inv-unit-excl, #inv-unit-incl, #inv-subtotal').text('—');
            if (isUsd) {
                $('#inv-pen-equiv').removeClass('d-none');
                $('#inv-unit-excl-pen, #inv-unit-incl-pen, #inv-subtotal-pen, #inv-total-pen').text('—');
            } else {
                $('#inv-pen-equiv').addClass('d-none');
            }
        }
    }

    function bindInvoiceModal() {
        bindAmtFields('.inv-amt');

        function updateDocPreview() {
            const s = ($('#inv-series').val() || 'FXXX').toUpperCase();
            const n = $('#inv-number').val() || '00000000';
            $('#inv-doc-preview').text(s + '-' + n);
        }
        $('#inv-series, #inv-number').on('input', updateDocPreview);
        updateDocPreview();

        toggleCurrencyFields();
        $('#inv-currency').off('change.invcurr').on('change.invcurr', function () {
            toggleCurrencyFields();
            calcInvoicePrices();
        });
        $('#inv-exchange').off('input.invcalc blur.invcalc')
            .on('input.invcalc blur.invcalc', calcInvoicePrices);

        $('#inv-qty, #inv-total, #inv-igv').off('input.invcalc blur.invcalc')
            .on('input.invcalc blur.invcalc', calcInvoicePrices);
        calcInvoicePrices();

        $('#btn-save-invoice-header').off('click').on('click', function () {
            const $btn = $(this);
            const supplier = $('#inv-supplier').val();
            const scop = $('#inv-scop').val().trim();
            const series = $('#inv-series').val().trim();
            const number = $('#inv-number').val().trim();
            const qty = parseNum($('#inv-qty').val());
            const total = parseNum($('#inv-total').val());
            const currency = getInvoiceCurrency();
            const exchangeRate = getExchangeRate();
            if (!supplier || !scop || !series || !number) {
                toastr.warning('Complete proveedor, SCOP, serie y número');
                return;
            }
            if (currency === 'USD' && exchangeRate <= 0) {
                toastr.warning('Ingrese el tipo de cambio para facturas en dólares');
                $('#inv-exchange').focus();
                return;
            }
            if (!qty || parseFloat(qty) <= 0 || !total || parseFloat(total) <= 0) {
                toastr.warning('Ingrese cantidad KG e importe total');
                return;
            }
            $btn.prop('disabled', true);
            $.ajax({
                url: window.GLP_URLS.saveHeader,
                type: 'POST',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': window.GLP_URLS.csrf },
                data: JSON.stringify({
                    product_id: parseInt($('#inv-product-id').val(), 10),
                    purchase: {
                        supplier_id: parseInt(supplier, 10),
                        scop_number: scop,
                        series: series,
                        number: number,
                        issue_date: $('#inv-date').val(),
                        currency: currency,
                        exchange_rate: currency === 'USD' ? exchangeRate : 1,
                        payment_terms: $('#inv-payment').val(),
                        terminal: $('#inv-terminal').val(),
                        sales_order: $('#inv-sales-order').val(),
                    },
                    detail: {
                        quantity: qty,
                        total: total,
                        igv: parseNum($('#inv-igv').val()) || '',
                    },
                }),
                success: function (r) {
                    toastr.success(r.message);
                    $('#add-modal').modal('hide');
                    if (typeof loadPurchases === 'function') loadPurchases();
                    if (r.purchase_id) showPurchaseSummary(r.purchase_id);
                },
                error: function (xhr) {
                    toastr.error(xhr.responseJSON?.error || 'Error');
                },
                complete: function () {
                    $btn.prop('disabled', false);
                },
            });
        });
    }

    function bindProgrammingModal() {
        let purchasesData = [];
        try {
            purchasesData = JSON.parse($('#prog-purchases-data').text() || '[]');
        } catch (e) {
            purchasesData = [];
        }

        const tripLines = [];
        const $select = $('#prog-purchase-select');
        $select.empty().append('<option value="">— Seleccione factura —</option>');
        purchasesData.forEach(function (p) {
            $select.append(
                '<option value="' + p.id + '" data-available="' + p.available_kg + '" data-doc="' + p.document + '" data-scop="' + p.scop + '">' +
                p.document + ' — saldo ' + fmt(p.available_kg, 3) + ' KG</option>'
            );
        });

        bindAmtFields('.prog-amt');

        function refreshAvailableMap() {
            const used = {};
            tripLines.forEach(function (l) {
                used[l.purchase_id] = (used[l.purchase_id] || 0) + parseFloat(l.quantity_kg);
            });
            $select.find('option[value!=""]').each(function () {
                const id = parseInt($(this).val(), 10);
                const base = parseFloat($(this).data('available')) || 0;
                const left = base - (used[id] || 0);
                const doc = $(this).data('doc');
                $(this).text(doc + ' — saldo ' + fmt(Math.max(0, left), 3) + ' KG');
                $(this).prop('disabled', left <= 0);
            });
        }

        function updateTotal() {
            const total = tripLines.reduce(function (s, l) {
                return s + (parseFloat(l.quantity_kg) || 0);
            }, 0);
            $('#prog-total-kg').text(fmt(total, 3));
        }

        function renderLines() {
            const $body = $('#prog-lines-body');
            if (!tripLines.length) {
                $body.html('<tr id="prog-lines-empty"><td colspan="4" class="text-center text-muted py-3">Agregue facturas y cantidades para este viaje</td></tr>');
            } else {
                let html = '';
                tripLines.forEach(function (l, idx) {
                    html += '<tr data-idx="' + idx + '">' +
                        '<td><span class="glp-doc-chip">' + l.document + '</span></td>' +
                        '<td>' + (l.scop || '—') + '</td>' +
                        '<td class="text-right font-weight-bold">' + fmt(l.quantity_kg, 3) + '</td>' +
                        '<td class="text-center"><button type="button" class="btn btn-danger btn-sm prog-line-del"><i class="fas fa-trash"></i></button></td></tr>';
                });
                $body.html(html);
            }
            updateTotal();
            refreshAvailableMap();
        }

        $('#prog-purchase-select').off('change').on('change', function () {
            const $o = $(this).find(':selected');
            const avail = $o.data('available');
            $('#prog-available-hint').text(avail ? 'Disponible inicial: ' + fmt(avail, 3) + ' KG' : '');
        });

        $('#prog-use-all').off('click').on('click', function () {
            const $o = $('#prog-purchase-select').find(':selected');
            const pid = parseInt($o.val(), 10);
            if (!pid) return;
            const used = tripLines.filter(function (l) { return l.purchase_id === pid; })
                .reduce(function (s, l) { return s + parseFloat(l.quantity_kg); }, 0);
            const left = (parseFloat($o.data('available')) || 0) - used;
            if (left > 0) $('#prog-qty').val(fmt(left, 3));
        });

        $('#prog-add-line').off('click').on('click', function () {
            const pid = parseInt($('#prog-purchase-select').val(), 10);
            const qty = parseNum($('#prog-qty').val());
            if (!pid || !qty || parseFloat(qty) <= 0) {
                toastr.warning('Seleccione factura e ingrese KG mayor a cero');
                return;
            }
            const $o = $('#prog-purchase-select').find(':selected');
            const used = tripLines.filter(function (l) { return l.purchase_id === pid; })
                .reduce(function (s, l) { return s + parseFloat(l.quantity_kg); }, 0);
            const left = (parseFloat($o.data('available')) || 0) - used;
            if (parseFloat(qty) > left + 0.001) {
                toastr.warning('Solo quedan ' + fmt(left, 3) + ' KG disponibles en esta factura');
                return;
            }
            const existing = tripLines.findIndex(function (l) { return l.purchase_id === pid; });
            const row = {
                purchase_id: pid,
                quantity_kg: qty,
                document: $o.data('doc'),
                scop: $o.data('scop') || '',
            };
            if (existing >= 0) {
                tripLines[existing].quantity_kg = parseFloat(tripLines[existing].quantity_kg) + parseFloat(qty);
            } else {
                tripLines.push(row);
            }
            $('#prog-qty').val('');
            renderLines();
        });

        $(document).off('click.progline').on('click.progline', '.prog-line-del', function () {
            const idx = $(this).closest('tr').data('idx');
            tripLines.splice(idx, 1);
            renderLines();
        });

        $('#btn-save-programming').off('click').on('click', function () {
            const truckId = $('#prog-truck').val();
            const scop = $('#prog-scop').val().trim();
            if (!truckId || !scop) {
                toastr.warning('Complete placa y SCOP de traslado');
                return;
            }
            if (!tripLines.length) {
                toastr.warning('Agregue al menos una factura con cantidad');
                return;
            }
            const $btn = $(this);
            $btn.prop('disabled', true);
            $.ajax({
                url: window.GLP_URLS.saveProgramming,
                type: 'POST',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': window.GLP_URLS.csrf },
                data: JSON.stringify({
                    truck_id: parseInt(truckId, 10),
                    transfer_scop_number: scop,
                    programming_date: $('#prog-date').val(),
                    lines: tripLines.map(function (l) {
                        return { purchase_id: l.purchase_id, quantity_kg: String(l.quantity_kg) };
                    }),
                }),
                success: function (r) {
                    toastr.success(r.message);
                    $('#add-modal').modal('hide');
                    if (typeof loadPurchases === 'function') loadPurchases();
                },
                error: function (xhr) {
                    toastr.error(xhr.responseJSON?.error || 'Error');
                },
                complete: function () {
                    $btn.prop('disabled', false);
                },
            });
        });
    }

    let whLinesData = [];
    const whExpRows = [];

    function whProgrammedKg() {
        return whLinesData.reduce(function (s, l) { return s + (parseFloat(l.quantity_kg) || 0); }, 0);
    }

    function whPurchaseValuePen() {
        return whLinesData.reduce(function (s, l) {
            return s + (parseFloat(l.unit_price_pen) || 0) * (parseFloat(l.quantity_kg) || 0);
        }, 0);
    }

    function whExpensesTotal() {
        return whExpRows.reduce(function (s, r) { return s + (parseFloat(r.amount) || 0); }, 0);
    }

    function updateWhLanded() {
        const programmed = whProgrammedKg();
        const purchaseValue = whPurchaseValuePen();
        const expenses = whExpensesTotal();
        const total = purchaseValue + expenses;
        const unit = programmed > 0 ? total / programmed : 0;
        const extraPerKg = programmed > 0 ? expenses / programmed : 0;

        $('#wh-ls-purchase').text('S/ ' + fmt(purchaseValue, 2));
        $('#wh-ls-expense').text('S/ ' + fmt(expenses, 2));
        $('#wh-ls-total').text('S/ ' + fmt(total, 2));
        $('#wh-ls-kg').text(fmt(programmed, 3));
        $('#wh-ls-unit').text('S/ ' + fmt(unit, 4));

        $('#wh-invoices-body tr[data-line-idx]').each(function () {
            const idx = parseInt($(this).data('line-idx'), 10);
            const line = whLinesData[idx];
            if (!line) return;
            const landed = (parseFloat(line.unit_price_pen) || 0) + extraPerKg;
            $(this).find('.wh-landed-cost')
                .text(fmt(landed, 6))
                .attr('title', 'Base ' + fmt(line.unit_price_pen, 6) + ' + gastos ' + fmt(extraPerKg, 6) + '/KG');
        });
    }

    function renderWhExpenses() {
        const $body = $('#wh-exp-rows');
        if (!whExpRows.length) {
            $body.html('<tr class="wh-exp-empty"><td colspan="7" class="text-center text-muted py-3">Sin gastos registrados — el costo usará solo el valor de la factura</td></tr>');
        } else {
            let html = '';
            whExpRows.forEach(function (r, idx) {
                html += '<tr data-exp-idx="' + idx + '">' +
                    '<td class="text-center text-muted">' + (idx + 1) + '</td>' +
                    '<td>' + r.type_label + '</td>' +
                    '<td>' + (r.invoice_number || '—') + '</td>' +
                    '<td>' + (r.expense_date || '—') + '</td>' +
                    '<td class="text-right font-weight-bold">' + fmt(r.amount, 2) + '</td>' +
                    '<td>' + (r.description || '') + '</td>' +
                    '<td class="text-center"><button type="button" class="btn btn-danger btn-sm wh-exp-del"><i class="fas fa-trash"></i></button></td>' +
                    '</tr>';
            });
            html += '<tr class="glp-prog-total-row">' +
                '<td colspan="4" class="text-right font-weight-bold">Total gastos</td>' +
                '<td class="text-right font-weight-bold">' + fmt(whExpensesTotal(), 2) + '</td>' +
                '<td colspan="2"></td></tr>';
            $body.html(html);
        }
        updateWhLanded();
    }

    function loadProgrammingInvoices(progId) {
        const $body = $('#wh-invoices-body');
        whLinesData = [];
        if (!progId) {
            $body.html('<tr><td colspan="6" class="text-center text-muted py-3">Seleccione una programación</td></tr>');
            $('#wh-prog-badge').addClass('d-none');
            updateWhLanded();
            return;
        }
        $body.html('<tr><td colspan="6" class="text-center text-muted py-3"><i class="fas fa-spinner fa-spin"></i> Cargando...</td></tr>');
        $.ajax({
            url: window.GLP_URLS.programmingDetail + progId + '/',
            type: 'GET',
            success: function (r) {
                if (!r.lines || !r.lines.length) {
                    $body.html('<tr><td colspan="6" class="text-center text-warning py-3">Sin cantidades programadas</td></tr>');
                    $('#wh-prog-badge').addClass('d-none');
                    return;
                }
                whLinesData = r.lines;
                let html = '';
                let total = 0;
                r.lines.forEach(function (p, idx) {
                    total += p.quantity_kg;
                    html += '<tr data-line-idx="' + idx + '">' +
                        '<td><span class="glp-doc-chip">' + p.document + '</span></td>' +
                        '<td>' + (p.scop || '—') + '</td>' +
                        '<td>' + p.supplier + '</td>' +
                        '<td class="text-right font-weight-bold text-primary">' + fmt(p.quantity_kg, 3) + '</td>' +
                        '<td class="text-right glp-base-cell">' + fmt(p.unit_price_pen, 6) + '</td>' +
                        '<td class="text-right glp-landed-cell wh-landed-cost">' + fmt(p.unit_price_pen, 6) + '</td>' +
                        '</tr>';
                });
                html += '<tr class="glp-prog-total-row">' +
                    '<td colspan="3" class="text-right font-weight-bold">Total programado</td>' +
                    '<td class="text-right font-weight-bold glp-prog-total-kg">' + fmt(total, 3) + '</td>' +
                    '<td colspan="2"></td></tr>';
                $body.html(html);
                $('#wh-programmed-kg').text(fmt(total, 3));
                $('#wh-prog-badge').removeClass('d-none');
                $('#wh-programming').find(':selected').data('total', total);
                updateWhLanded();
            },
            error: function () {
                $body.html('<tr><td colspan="6" class="text-center text-danger py-3">Error al cargar</td></tr>');
            },
        });
    }

    function bindWarehouseModal() {
        whExpRows.length = 0;
        whLinesData = [];
        bindAmtFields('.wh-amt');
        renderWhExpenses();
        if (!$('#wh-date').val()) {
            const now = new Date();
            now.setMinutes(now.getMinutes() - now.getTimezoneOffset());
            $('#wh-date').val(now.toISOString().slice(0, 16));
        }

        $('#wh-programming').off('change').on('change', function () {
            const $o = $(this).find(':selected');
            const progId = $(this).val();
            $('#wh-truck').val($o.data('truck') || '');
            $('#wh-scop-transfer').val($o.data('scop') || '');
            loadProgrammingInvoices(progId);
        });

        function updateGuidePreview() {
            const s = ($('#wh-guide-series').val() || 'TXXX').toUpperCase();
            const n = $('#wh-guide-number').val() || '00000000';
            $('#wh-guide-preview').text(s + '-' + n);
        }
        $('#wh-guide-series, #wh-guide-number').on('input', updateGuidePreview);
        updateGuidePreview();

        $('#wh-exp-add').off('click').on('click', function () {
            const amount = parseNum($('#wh-exp-amount').val());
            if (!amount || parseFloat(amount) <= 0) {
                toastr.warning('Ingrese el monto del gasto');
                $('#wh-exp-amount').focus();
                return;
            }
            whExpRows.push({
                expense_type: $('#wh-exp-type').val(),
                type_label: $('#wh-exp-type option:selected').text(),
                invoice_number: $('#wh-exp-invoice').val().trim(),
                expense_date: $('#wh-exp-date').val(),
                amount: amount,
                description: $('#wh-exp-desc').val().trim(),
            });
            $('#wh-exp-amount, #wh-exp-invoice, #wh-exp-desc').val('');
            renderWhExpenses();
        });

        $(document).off('click.whexpdel').on('click.whexpdel', '.wh-exp-del', function () {
            const idx = parseInt($(this).closest('tr').data('exp-idx'), 10);
            whExpRows.splice(idx, 1);
            renderWhExpenses();
        });

        $('#btn-save-warehouse').off('click').on('click', function () {
            const programmingId = $('#wh-programming').val();
            const warehouseId = $('#wh-warehouse').val();
            if (!programmingId || !warehouseId) {
                toastr.warning('Complete programación y almacén');
                return;
            }
            if (!$('#wh-guide-series').val() || !$('#wh-guide-number').val()) {
                toastr.warning('Ingrese serie y número de guía');
                return;
            }

            const $btn = $(this);
            $btn.prop('disabled', true);
            $.ajax({
                url: window.GLP_URLS.saveTransfer,
                type: 'POST',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': window.GLP_URLS.csrf },
                data: JSON.stringify({
                    programming_id: parseInt(programmingId, 10),
                    warehouse_id: parseInt(warehouseId, 10),
                    expenses: whExpRows.map(function (r) {
                        return {
                            expense_type: r.expense_type,
                            invoice_number: r.invoice_number,
                            expense_date: r.expense_date,
                            amount: r.amount,
                            description: r.description,
                        };
                    }),
                    receipt: {
                        receipt_date: $('#wh-date').val(),
                        guide_series: $('#wh-guide-series').val(),
                        guide_number: $('#wh-guide-number').val(),
                        destination: $('#wh-destination').val(),
                        net_weight: '0',
                    },
                }),
                success: function (r) {
                    toastr.success(r.message);
                    $('#add-modal').modal('hide');
                    if (typeof loadPurchases === 'function') loadPurchases();
                },
                error: function (xhr) {
                    toastr.error(xhr.responseJSON?.error || 'Error');
                },
                complete: function () {
                    $btn.prop('disabled', false);
                },
            });
        });
    }

    const expRows = [];

    function bindExpenseModal() {
        expRows.length = 0;
        bindAmtFields('.exp-amt');
        $('#exp-programming').off('change').on('change', function () {
            const $o = $(this).find(':selected');
            $('#exp-truck').val($o.data('truck') || '');
            $('#exp-scop').val($o.data('scop') || '');
        });
        $('#exp-add-row').off('click').on('click', function () {
            const progId = $('#exp-programming').val();
            if (!progId) {
                toastr.warning('Seleccione programación');
                return;
            }
            const amount = parseNum($('#exp-amount').val());
            if (!amount || parseFloat(amount) <= 0) {
                toastr.warning('Ingrese monto');
                return;
            }
            const row = {
                expense_type: $('#exp-type').val(),
                invoice_number: $('#exp-invoice').val(),
                expense_date: $('#exp-date').val(),
                quantity: parseNum($('#exp-qty').val()) || '0',
                amount: amount,
                description: $('#exp-desc').val(),
            };
            expRows.push(row);
            const typeText = $('#exp-type option:selected').text();
            $('#exp-rows').append(
                '<tr><td class="text-center">' + expRows.length + '</td>' +
                '<td>' + (row.invoice_number || '—') + '</td>' +
                '<td>' + (row.expense_date || '—') + '</td>' +
                '<td class="text-right">' + fmt(row.amount, 2) + '</td>' +
                '<td>' + (row.description || '') + '</td>' +
                '<td>' + typeText + '</td>' +
                '<td class="text-center"><button type="button" class="btn btn-danger btn-sm exp-del"><i class="fas fa-trash"></i></button></td></tr>'
            );
            $('#exp-amount, #exp-invoice, #exp-desc, #exp-qty').val('');
        });
        $(document).off('click.expdel').on('click.expdel', '.exp-del', function () {
            const idx = $(this).closest('tr').index();
            expRows.splice(idx, 1);
            $(this).closest('tr').remove();
        });
        $('#btn-save-expenses').off('click').on('click', function () {
            const progId = $('#exp-programming').val();
            if (!progId || !expRows.length) {
                toastr.warning('Agregue gastos a la programación');
                return;
            }
            const $btn = $(this);
            $btn.prop('disabled', true);
            $.ajax({
                url: window.GLP_URLS.saveExpense,
                type: 'POST',
                contentType: 'application/json',
                headers: { 'X-CSRFToken': window.GLP_URLS.csrf },
                data: JSON.stringify({
                    programming_id: parseInt(progId, 10),
                    rows: expRows,
                }),
                success: function (r) {
                    toastr.success(r.message);
                    $('#add-modal').modal('hide');
                },
                error: function (xhr) {
                    toastr.error(xhr.responseJSON?.error || 'Error');
                },
                complete: function () {
                    $btn.prop('disabled', false);
                },
            });
        });
    }

    window.loadPurchases = function () {
        $.ajax({
            url: window.GLP_URLS.list,
            type: 'GET',
            data: {
                status: $('#filter-status').val(),
                start_date: $('#filter-start').val(),
                end_date: $('#filter-end').val(),
                search: $('#filter-search').val(),
            },
            success: function (r) {
                if (r.success) {
                    $('#purchase-grid-list').html(r.form);
                    if (r.stats) {
                        $('#stat-total').text(r.stats.total);
                        $('#stat-pending-detail').text(r.stats.pending_detail);
                        $('#stat-pending-transfer').text(r.stats.pending_transfer);
                        $('#stat-completed').text(r.stats.completed);
                    }
                }
            },
        });
    };

    $(document).ready(function () {
        if (window.GLP_URLS && window.GLP_URLS.openOnLoad) {
            showGlpModal('get_glp_purchase_invoice_modal');
        }
        $('#btn-filter').on('click', loadPurchases);
        $('#filter-search').on('keypress', function (e) {
            if (e.which === 13) loadPurchases();
        });
        $(document).on('click', '.btn-purchase-summary', function () {
            showPurchaseSummary($(this).data('pk'));
        });
    });
})();
