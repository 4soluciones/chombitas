import decimal

from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.inventory.models import (
    Purchase, PurchaseItem, PurchaseReceipt, PurchaseParticipant,
    PurchaseProgramming, PurchaseProgrammingLine, PurchaseTravelExpense,
    InventoryLedger, GlpKardexDocument,
)
from apps.sales.models import Product, ProductStore

GLP_PRODUCT_ID = 4
GLP_SUBSIDIARY_ID = 1  # SICUANI
GLP_WAREHOUSE_ID = 14  # PLUSPETROL, único almacén categoría G del kardex
GLP_TON_TO_KG = decimal.Decimal('1000')
GLP_DEFAULT_QTY_KG = decimal.Decimal('94000')
IGV_RATE = decimal.Decimal('0.18')


def _to_decimal(value, default=0):
    try:
        return decimal.Decimal(str(value or default))
    except (decimal.InvalidOperation, TypeError):
        return decimal.Decimal(default)


def _parse_date(value):
    if not value:
        return None
    if hasattr(value, 'year'):
        return value
    return parse_date(str(value))


def _parse_datetime(value):
    if not value:
        return None
    if hasattr(value, 'hour'):
        return timezone.make_aware(value) if timezone.is_naive(value) else value
    parsed = parse_datetime(str(value))
    if not parsed:
        return None
    return timezone.make_aware(parsed) if timezone.is_naive(parsed) else parsed


def get_last_ledger(product_id, warehouse_id):
    return InventoryLedger.objects.filter(
        product_id=product_id, warehouse_id=warehouse_id,
    ).order_by('-id').first()


def register_ledger_entry(product, warehouse, movement_date, movement_type,
                          reference_type, reference_id, quantity_in=0, quantity_out=0,
                          unit_cost=0, remarks='', user=None):
    quantity_in = _to_decimal(quantity_in)
    quantity_out = _to_decimal(quantity_out)
    unit_cost = _to_decimal(unit_cost)

    last = get_last_ledger(product.id, warehouse.id)
    prev_qty = last.balance_quantity if last else decimal.Decimal(0)
    prev_avg = last.average_cost if last else decimal.Decimal(0)
    prev_value = last.balance_value if last else decimal.Decimal(0)

    if quantity_out > 0:
        if unit_cost == 0:
            unit_cost = prev_avg
        new_avg = prev_avg
        new_qty = prev_qty - quantity_out
        new_value = new_qty * new_avg
    elif quantity_in > 0:
        new_qty = prev_qty + quantity_in
        new_value = prev_value + (quantity_in * unit_cost)
        new_avg = new_value / new_qty if new_qty else unit_cost
    else:
        new_avg = prev_avg
        new_qty = prev_qty
        new_value = prev_value

    ledger = InventoryLedger.objects.create(
        product=product,
        warehouse=warehouse,
        movement_date=movement_date,
        movement_type=movement_type,
        reference_type=reference_type,
        reference_id=reference_id,
        quantity_in=quantity_in,
        quantity_out=quantity_out,
        balance_quantity=new_qty,
        unit_cost=unit_cost,
        average_cost=new_avg,
        balance_value=new_value,
        remarks=remarks or '',
        created_by=user,
    )
    _sync_product_store_stock(product, warehouse, new_qty)
    return ledger


def register_sale_exit(product, warehouse, movement_date, quantity, user, doc_data):
    quantity = _to_decimal(quantity)
    if quantity <= 0:
        raise ValueError('La cantidad debe ser mayor a cero')

    last = get_last_ledger(product.id, warehouse.id)
    if not last or last.balance_quantity < quantity:
        raise ValueError('Stock insuficiente en el almacén GLP')

    movement_date = _parse_datetime(movement_date) or timezone.now()
    unit_cost = last.average_cost

    with transaction.atomic():
        ledger = register_ledger_entry(
            product=product,
            warehouse=warehouse,
            movement_date=movement_date,
            movement_type='Sale',
            reference_type='Sale',
            reference_id=0,
            quantity_out=quantity,
            unit_cost=unit_cost,
            user=user,
        )
        ledger.reference_id = ledger.id
        ledger.save(update_fields=['reference_id'])

        GlpKardexDocument.objects.create(
            inventory_ledger=ledger,
            document_type=doc_data.get('document_type', '01'),
            operation_sunat='01',
            serial=doc_data.get('serial', ''),
            document_number=doc_data.get('document_number', ''),
            document_number_end=doc_data.get('document_number_end', ''),
            partner_ruc=doc_data.get('partner_ruc', ''),
            description=doc_data.get('description', 'VENTA'),
            user=user,
        )
    return ledger


def _sync_product_store_stock(product, warehouse, new_qty):
    ps, _ = ProductStore.objects.get_or_create(
        product=product,
        subsidiary_store=warehouse,
        defaults={'stock': new_qty},
    )
    if ps.stock != new_qty:
        ps.stock = new_qty
        ps.save(update_fields=['stock'])


def _unit_price_pen(purchase, item):
    """Precio unitario sin IGV en soles (aplica tipo de cambio si la factura es USD)."""
    price = _to_decimal(item.unit_price)
    if purchase.currency == 'USD':
        return price * _to_decimal(purchase.exchange_rate, 1)
    return price


def get_purchase_base_unit_pen(purchase):
    """Precio unitario sin IGV (PEN) del ítem principal de la factura."""
    item = purchase.items.first()
    if not item:
        return decimal.Decimal(0)
    return _unit_price_pen(purchase, item)


def calc_landed_unit_cost(base_unit_pen, net_weight_kg, additional_cost_pen):
    """
    Costo unitario que ingresa al kardex (PEN/KG, sin IGV):

        costo_kardex = precio_factura_sin_igv + (gastos_transporte / kg_neto)

    Los gastos de transporte incluyen flete, seguro, descarga, otros del guía
    y las facturas de gastos de viaje vinculadas a la programación.
    """
    base = _to_decimal(base_unit_pen)
    net = _to_decimal(net_weight_kg)
    extra = _to_decimal(additional_cost_pen)
    if net <= 0:
        return base
    return (base + extra / net).quantize(decimal.Decimal('0.000001'))


def calc_trip_additional_cost(receipt_data, travel_expenses_total=0):
    """Suma de gastos adicionales del viaje (guía + gastos de viaje registrados)."""
    return (
        _to_decimal(receipt_data.get('freight_cost', 0))
        + _to_decimal(receipt_data.get('insurance_cost', 0))
        + _to_decimal(receipt_data.get('unloading_cost', 0))
        + _to_decimal(receipt_data.get('other_cost', 0))
        + _to_decimal(travel_expenses_total)
    )


def _qty_input_to_kg(value, unit='T0'):
    """Convierte cantidad ingresada (T0 = tonelada) a kilogramos para almacenar."""
    qty = _to_decimal(value)
    if str(unit or 'T0').upper() in ('T0', 'TO', 'TON', 'TONELADA', 'TONELADAS'):
        return qty * GLP_TON_TO_KG
    return qty


def _calc_participant_total(row):
    """Valor venta + ISC + IGV + Otros (FISE) = Total — formato Pluspetrol."""
    subtotal = _to_decimal(row.get('subtotal', 0))
    if subtotal == 0 and row.get('quantity') and row.get('unit_price'):
        subtotal = _to_decimal(row['quantity']) * _to_decimal(row['unit_price'])
    isc = _to_decimal(row.get('isc', 0))
    igv = _to_decimal(row.get('igv', 0))
    fise = _to_decimal(row.get('fise', 0))
    total = subtotal + isc + igv + fise
    return subtotal, isc, igv, fise, total


def _parse_participants_rows(participants_data):
    parsed = []
    for row in participants_data:
        if not row.get('company_name'):
            continue
        subtotal, isc, igv, fise, total = _calc_participant_total(row)
        qty = _qty_input_to_kg(row.get('quantity', 0), row.get('quantity_unit', 'T0'))
        unit_price = _to_decimal(row.get('unit_price', 0))
        if unit_price == 0 and qty > 0 and subtotal > 0:
            unit_price = subtotal / qty
        parsed.append({
            'company_name': row['company_name'],
            'tax_id': row.get('tax_id', ''),
            'quantity': qty,
            'unit_price': unit_price,
            'subtotal': subtotal,
            'isc': isc,
            'igv': igv,
            'fise': fise,
            'total': total,
        })
    return parsed


def _save_participants_for_purchase(purchase, parsed, skip_qty_check=False, update_totals=False):
    if not parsed:
        raise ValueError('Debe registrar al menos un participante con razón social')

    totals_sum = sum(p['total'] for p in parsed)
    qty_sum = sum(p['quantity'] for p in parsed)
    invoice_total = _to_decimal(purchase.total)

    if not update_totals and invoice_total > 0 and abs(totals_sum - invoice_total) > decimal.Decimal('0.05'):
        raise ValueError(
            f'La suma de participantes ({totals_sum:.2f}) debe igualar '
            f'el total de factura ({invoice_total:.2f})'
        )

    invoiced_qty = sum(_to_decimal(i.quantity) for i in purchase.items.all())
    if not skip_qty_check and invoiced_qty > 0 and abs(qty_sum - invoiced_qty) > decimal.Decimal('0.001'):
        raise ValueError(
            f'La suma de cantidades ({qty_sum:.3f} KG) debe igualar '
            f'la cantidad facturada ({invoiced_qty:.3f} KG)'
        )

    purchase.participants.all().delete()
    for p in parsed:
        PurchaseParticipant.objects.create(purchase=purchase, **p)

    if update_totals:
        sum_subtotal = sum(p['subtotal'] for p in parsed)
        sum_isc = sum(p['isc'] for p in parsed)
        sum_igv = sum(p['igv'] for p in parsed)
        sum_fise = sum(p['fise'] for p in parsed)
        purchase.subtotal = sum_subtotal
        purchase.isc = sum_isc
        purchase.igv = sum_igv
        purchase.fise = sum_fise
        purchase.other_charges = sum_fise
        purchase.total = totals_sum
        purchase.uses_participants = True
        avg_price = sum_subtotal / qty_sum if qty_sum > 0 else decimal.Decimal(0)
        avg_incl = totals_sum / qty_sum if qty_sum > 0 else decimal.Decimal(0)
        product = purchase.items.first().product if purchase.items.exists() else Product.objects.get(pk=GLP_PRODUCT_ID)
        purchase.items.all().delete()
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            description=product.name,
            unit='KG',
            quantity=qty_sum,
            unit_price=avg_price,
            unit_price_incl_igv=avg_incl,
            subtotal=sum_subtotal,
            isc=sum_isc,
            igv=sum_igv,
            fise=sum_fise,
            total=totals_sum,
        )

    purchase.status = 'ParticipantsRegistered'
    purchase.save()
    return purchase


def save_purchase_with_detail(purchase_data, detail_data, product_id, user, purchase_id=None):
    """Registra cabecera + detalle simple en una sola operación."""
    with transaction.atomic():
        purchase = save_purchase_header(
            purchase_data=purchase_data,
            user=user,
            purchase_id=purchase_id,
        )
        purchase = save_purchase_simple_detail(
            purchase_id=purchase.id,
            detail_data=detail_data,
            product_id=product_id,
            user=user,
        )
    return purchase


def save_purchase_header(purchase_data, user, purchase_id=None):
    """Registra cabecera de factura (N° SCOP + comprobante)."""
    currency = purchase_data.get('currency', 'PEN')
    exchange_rate = _to_decimal(purchase_data.get('exchange_rate', 1), 1)
    if currency == 'USD' and exchange_rate <= 0:
        raise ValueError('Ingrese un tipo de cambio válido para facturas en dólares')
    with transaction.atomic():
        fields = {
            'supplier_id': purchase_data['supplier_id'],
            'invoice_type': purchase_data.get('invoice_type', 'Invoice'),
            'series': purchase_data['series'],
            'number': purchase_data['number'],
            'issue_date': _parse_date(purchase_data['issue_date']),
            'due_date': _parse_date(purchase_data.get('due_date')),
            'currency': currency,
            'exchange_rate': exchange_rate if currency == 'USD' else decimal.Decimal('1'),
            'scop_number': (purchase_data.get('scop_number') or '').strip(),
            'sales_order': purchase_data.get('sales_order', ''),
            'terminal': purchase_data.get('terminal', ''),
            'payment_terms': purchase_data.get('payment_terms', 'Cash'),
            'remarks': purchase_data.get('remarks', ''),
            'status': 'InvoiceRegistered',
        }
        if purchase_id:
            purchase = Purchase.objects.get(pk=purchase_id)
            if purchase.status in ('Completed', 'Cancelled'):
                raise ValueError('No se puede editar una compra completada o anulada')
            if purchase.receipts.filter(ledger_posted=True).exists():
                raise ValueError('No se puede editar: ya hay traslados ingresados al kardex')
            for k, v in fields.items():
                setattr(purchase, k, v)
            purchase.save()
        else:
            purchase = Purchase.objects.create(created_by=user, **fields)
        return purchase


def _calc_prices_from_total(qty, total, igv=None):
    qty = _to_decimal(qty)
    total = _to_decimal(total)
    if qty <= 0:
        raise ValueError('La cantidad debe ser mayor a cero')
    if total <= 0:
        raise ValueError('El importe total debe ser mayor a cero')
    igv_val = _to_decimal(igv, 0)
    if igv_val == 0:
        igv_val = (total * IGV_RATE / (decimal.Decimal('1') + IGV_RATE)).quantize(
            decimal.Decimal('0.0001'))
    subtotal = total - igv_val
    unit_excl = (subtotal / qty).quantize(decimal.Decimal('0.000001'))
    unit_incl = (total / qty).quantize(decimal.Decimal('0.000001'))
    return subtotal, igv_val, unit_excl, unit_incl


def save_purchase_simple_detail(purchase_id, detail_data, product_id, user):
    """Detalle simple: cantidad KG + importe total → precios unitarios."""
    purchase = Purchase.objects.get(pk=purchase_id)
    if purchase.status == 'Cancelled':
        raise ValueError('Compra anulada')
    if purchase.receipts.filter(ledger_posted=True).exists():
        raise ValueError('No se puede modificar el detalle: ya hay ingresos al kardex')

    qty = _to_decimal(detail_data.get('quantity', GLP_DEFAULT_QTY_KG))
    total = _to_decimal(detail_data.get('total', 0))
    igv_input = detail_data.get('igv')
    subtotal, igv, unit_excl, unit_incl = _calc_prices_from_total(qty, total, igv_input)

    product = Product.objects.get(pk=product_id)
    uses_participants = bool(detail_data.get('uses_participants'))

    with transaction.atomic():
        purchase.subtotal = subtotal
        purchase.igv = igv
        purchase.total = total
        purchase.uses_participants = uses_participants
        purchase.status = 'InvoiceRegistered' if uses_participants else 'DetailRegistered'
        purchase.save()

        purchase.items.all().delete()
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            description=product.name,
            unit='KG',
            quantity=qty,
            unit_price=unit_excl,
            unit_price_incl_igv=unit_incl,
            subtotal=subtotal,
            igv=igv,
            total=total,
        )
        if not uses_participants:
            purchase.participants.all().delete()
    return purchase


def get_purchase_qty_available(purchase):
    """KG de la factura aún no recibidos ni programados en viajes pendientes."""
    purchase = Purchase.objects.prefetch_related('items', 'receipts', 'programming_lines').get(
        pk=purchase.pk if isinstance(purchase, Purchase) else purchase)
    invoiced = sum(_to_decimal(i.quantity) for i in purchase.items.all())
    received = sum(
        _to_decimal(r.net_weight)
        for r in purchase.receipts.filter(status='Received', ledger_posted=True)
    )
    pending = sum(
        _to_decimal(line.quantity_kg)
        for line in purchase.programming_lines.filter(programming__status='Pending')
    )
    return invoiced - received - pending


def save_transfer_programming(truck_id, transfer_scop_number, lines, user, programming_date=None):
    """Programación: placa + SCOP + líneas parciales (factura + KG) por viaje."""
    scop = (transfer_scop_number or '').strip().upper()
    if not scop:
        raise ValueError('Ingrese el N° SCOP de traslado')
    truck_id = int(truck_id or 0)
    if not truck_id:
        raise ValueError('Seleccione la placa del tracto')
    if not lines:
        raise ValueError('Agregue al menos una factura con cantidad en KG')

    today = timezone.now().date()
    prog_date = _parse_date(programming_date) or today

    existing = PurchaseProgramming.objects.filter(transfer_scop_number=scop).select_related('truck').first()
    if existing and existing.truck_id != truck_id:
        raise ValueError(
            f'El SCOP {scop} ya está asignado a la placa {existing.truck.license_plate}'
        )
    if existing and existing.status == 'Finished':
        raise ValueError(f'El SCOP {scop} ya fue finalizado (ingresado al almacén)')

    parsed_lines = []
    for row in lines:
        purchase_id = int(row.get('purchase_id', 0))
        qty = _to_decimal(row.get('quantity_kg', 0))
        if not purchase_id or qty <= 0:
            continue
        parsed_lines.append({'purchase_id': purchase_id, 'quantity_kg': qty})

    if not parsed_lines:
        raise ValueError('Agregue al menos una factura con cantidad mayor a cero')

    with transaction.atomic():
        if existing and existing.status == 'Pending':
            programming = existing
        else:
            programming = PurchaseProgramming.objects.create(
                truck_id=truck_id,
                transfer_scop_number=scop,
                programming_date=prog_date,
                status='Pending',
            )

        purchase_ids = [pl['purchase_id'] for pl in parsed_lines]
        purchases = {
            p.id: p for p in Purchase.objects.filter(
                id__in=purchase_ids,
                status__in=('DetailRegistered', 'ParticipantsRegistered', 'InTransit'),
            ).prefetch_related('items', 'receipts', 'programming_lines')
        }
        if len(purchases) != len(set(purchase_ids)):
            raise ValueError('Una o más facturas no están disponibles para programación')

        for pl in parsed_lines:
            purchase = purchases[pl['purchase_id']]
            available = get_purchase_qty_available(purchase)
            existing_line = PurchaseProgrammingLine.objects.filter(
                programming=programming, purchase=purchase,
            ).first()
            if existing_line:
                available += _to_decimal(existing_line.quantity_kg)
            if pl['quantity_kg'] > available + decimal.Decimal('0.001'):
                raise ValueError(
                    f'Factura {purchase.document_display}: solo quedan {available:.3f} KG disponibles '
                    f'(facturado {purchase.invoiced_qty_total:.3f}, '
                    f'recibido {purchase.received_qty_total:.3f}, '
                    f'programado pendiente {purchase.qty_pending_programming:.3f})'
                )
            PurchaseProgrammingLine.objects.update_or_create(
                programming=programming,
                purchase=purchase,
                defaults={'quantity_kg': pl['quantity_kg']},
            )
            if purchase.status in ('DetailRegistered', 'ParticipantsRegistered'):
                purchase.status = 'InTransit'
                purchase.save(update_fields=['status', 'updated_at'])

    return programming


def save_purchase_programmings(purchase_id, rows, user):
    """Compatibilidad: filas con purchase_ids y quantity_kg opcional."""
    if not rows:
        raise ValueError('Debe agregar al menos un tracto con SCOP de traslado')
    results = []
    for row in rows:
        pids = row.get('purchase_ids') or ([purchase_id] if purchase_id else [])
        lines = row.get('lines')
        if not lines:
            lines = [{'purchase_id': pid, 'quantity_kg': row.get('quantity_kg')} for pid in pids]
        prog = save_transfer_programming(
            truck_id=row.get('truck_id'),
            transfer_scop_number=row.get('transfer_scop_number'),
            lines=lines,
            user=user,
            programming_date=row.get('programming_date'),
        )
        results.append(prog)
    return results


def save_travel_expenses(programming_id, rows, user):
    """Facturas de gastos de viaje vinculadas a una programación."""
    programming = PurchaseProgramming.objects.get(pk=programming_id)
    if not rows:
        raise ValueError('Debe registrar al menos un gasto')
    created = []
    with transaction.atomic():
        for row in rows:
            amount = _to_decimal(row.get('amount', 0))
            if amount <= 0:
                continue
            obj = PurchaseTravelExpense.objects.create(
                programming=programming,
                expense_type=row.get('expense_type', 'F'),
                invoice_number=(row.get('invoice_number') or '').strip(),
                expense_date=_parse_date(row.get('expense_date')),
                quantity=_to_decimal(row.get('quantity', 0)),
                amount=amount,
                description=(row.get('description') or '').strip(),
                status='Registered',
            )
            created.append(obj)
        if not created:
            raise ValueError('Debe registrar al menos un gasto con monto')
    return created


def set_programming_travel_expenses(programming_id, rows, user):
    """Reemplaza los gastos de viaje de una programación (permite lista vacía).

    Se usa desde el modal de asignar almacén: los gastos ingresados ahí definen
    el costo de traslado que se prorratea al costo unitario del kardex.
    """
    programming = PurchaseProgramming.objects.get(pk=programming_id)
    created = []
    with transaction.atomic():
        programming.travel_expenses.all().delete()
        for row in rows or []:
            amount = _to_decimal(row.get('amount', 0))
            if amount <= 0:
                continue
            obj = PurchaseTravelExpense.objects.create(
                programming=programming,
                expense_type=row.get('expense_type', 'F'),
                invoice_number=(row.get('invoice_number') or '').strip(),
                expense_date=_parse_date(row.get('expense_date')),
                quantity=_to_decimal(row.get('quantity', 0)),
                amount=amount,
                description=(row.get('description') or '').strip(),
                status='Registered',
            )
            created.append(obj)
    return created


def save_purchase_invoice(purchase_data, items_data, user, purchase_id=None):
    """Paso 1: registrar factura e ítems (sin kardex)."""
    with transaction.atomic():
        fields = {
            'supplier_id': purchase_data['supplier_id'],
            'invoice_type': purchase_data.get('invoice_type', 'Invoice'),
            'series': purchase_data['series'],
            'number': purchase_data['number'],
            'issue_date': _parse_date(purchase_data['issue_date']),
            'due_date': _parse_date(purchase_data.get('due_date')),
            'currency': purchase_data.get('currency', 'PEN'),
            'exchange_rate': _to_decimal(purchase_data.get('exchange_rate', 1), 1),
            'subtotal': _to_decimal(purchase_data.get('subtotal', 0)),
            'igv': _to_decimal(purchase_data.get('igv', 0)),
            'isc': _to_decimal(purchase_data.get('isc', 0)),
            'fise': _to_decimal(purchase_data.get('fise', 0)),
            'other_charges': _to_decimal(purchase_data.get('other_charges', 0)),
            'total': _to_decimal(purchase_data.get('total', 0)),
            'sales_order': purchase_data.get('sales_order', ''),
            'terminal': purchase_data.get('terminal', ''),
            'payment_terms': purchase_data.get('payment_terms', 'Cash'),
            'status': 'InvoiceRegistered',
            'remarks': purchase_data.get('remarks', ''),
        }

        if purchase_id:
            purchase = Purchase.objects.get(pk=purchase_id)
            if purchase.status in ('Completed', 'Cancelled'):
                raise ValueError('No se puede editar una compra completada o anulada')
            if purchase.receipts.filter(ledger_posted=True).exists():
                raise ValueError('No se puede editar: ya hay traslados ingresados al kardex')
            for k, v in fields.items():
                setattr(purchase, k, v)
            purchase.save()
            purchase.items.all().delete()
        else:
            purchase = Purchase.objects.create(created_by=user, **fields)

        items = []
        for row in items_data:
            item = PurchaseItem.objects.create(
                purchase=purchase,
                product_id=row['product_id'],
                description=row.get('description', ''),
                unit=row.get('unit', 'KG'),
                quantity=_to_decimal(row['quantity']),
                unit_price=_to_decimal(row['unit_price']),
                unit_price_incl_igv=_to_decimal(row.get('unit_price_incl_igv', 0)),
                subtotal=_to_decimal(row.get('subtotal', 0)),
                igv=_to_decimal(row.get('igv', 0)),
                isc=_to_decimal(row.get('isc', 0)),
                fise=_to_decimal(row.get('fise', 0)),
                total=_to_decimal(row.get('total', 0)),
            )
            items.append(item)

        return purchase, items


def save_purchase_with_participants(purchase_data, participants_data, product_id, user, purchase_id=None):
    """Registra factura + participantes en una sola operación (documento operador)."""
    parsed = _parse_participants_rows(participants_data)
    if not parsed:
        raise ValueError('Debe registrar al menos un participante')

    sum_subtotal = sum(p['subtotal'] for p in parsed)
    sum_isc = sum(p['isc'] for p in parsed)
    sum_igv = sum(p['igv'] for p in parsed)
    sum_fise = sum(p['fise'] for p in parsed)
    sum_total = sum(p['total'] for p in parsed)
    sum_qty = sum(p['quantity'] for p in parsed)

    purchase_data = dict(purchase_data)
    purchase_data['subtotal'] = sum_subtotal
    purchase_data['isc'] = sum_isc
    purchase_data['igv'] = sum_igv
    purchase_data['fise'] = sum_fise
    purchase_data['other_charges'] = sum_fise
    purchase_data['total'] = sum_total

    avg_price = sum_subtotal / sum_qty if sum_qty > 0 else decimal.Decimal(0)
    product = Product.objects.get(pk=product_id) if product_id else None
    items_data = [{
        'product_id': product_id,
        'description': product.name if product else 'GLP',
        'unit': 'KG',
        'quantity': sum_qty,
        'unit_price': avg_price,
        'subtotal': sum_subtotal,
        'isc': sum_isc,
        'igv': sum_igv,
        'fise': sum_fise,
        'total': sum_total,
    }]

    with transaction.atomic():
        purchase, _ = save_purchase_invoice(
            purchase_data=purchase_data,
            items_data=items_data,
            user=user,
            purchase_id=purchase_id,
        )
        _save_participants_for_purchase(purchase, parsed, skip_qty_check=True)
    return purchase


def save_purchase_participants(purchase_id, participants_data, user):
    """Paso 2: participantes — la suma debe igualar el total de la factura."""
    purchase = Purchase.objects.prefetch_related('items').get(pk=purchase_id)
    if purchase.status == 'Cancelled':
        raise ValueError('Compra anulada')
    if purchase.status == 'Draft':
        raise ValueError('Registre primero la factura')
    if purchase.receipts.filter(ledger_posted=True).exists():
        raise ValueError('No se pueden modificar participantes: ya hay ingresos al kardex')

    if not participants_data:
        raise ValueError('Debe registrar al menos un participante')

    parsed = _parse_participants_rows(participants_data)
    if not parsed:
        raise ValueError('Debe registrar al menos un participante con nombre')

    with transaction.atomic():
        _save_participants_for_purchase(
            purchase, parsed, skip_qty_check=True, update_totals=True,
        )

    return purchase


def _post_receipt_to_ledger(purchase, receipt, user):
    if receipt.ledger_posted:
        return []

    items = list(purchase.items.select_related('product'))
    if not items:
        raise ValueError('La compra no tiene ítems')

    net_weight = receipt.net_weight

    ledgers = []
    for item in items:
        qty = net_weight if net_weight > 0 else item.quantity
        unit_cost = calc_landed_unit_cost(
            _unit_price_pen(purchase, item),
            net_weight,
            receipt.total_additional_cost,
        )
        ledger = register_ledger_entry(
            product=item.product,
            warehouse=receipt.warehouse,
            movement_date=receipt.receipt_date,
            movement_type='Purchase',
            reference_type='PurchaseReceipt',
            reference_id=receipt.id,
            quantity_in=qty,
            unit_cost=unit_cost,
            remarks=f'Compra GLP — Guía {receipt.guide_series or ""}-{receipt.guide_number or ""}',
            user=user,
        )
        ledgers.append(ledger)

        supplier_ruc = purchase.supplier.ruc if purchase.supplier else ''
        GlpKardexDocument.objects.create(
            inventory_ledger=ledger,
            document_type='01',
            operation_sunat='02',
            serial=purchase.series,
            document_number=purchase.number,
            partner_ruc=supplier_ruc or '',
            description=(
                f'INGRESO GLP {purchase.document_display}'
                + (f' | Guía {receipt.guide_series}-{receipt.guide_number}'
                   if receipt.guide_series else '')
                + (f' | SCOP {receipt.scop_number}' if receipt.scop_number else '')
            ),
            user=user,
        )

    receipt.ledger_posted = True
    receipt.save(update_fields=['ledger_posted'])
    return ledgers


def _refresh_purchase_status(purchase):
    received = sum(
        r.net_weight for r in purchase.receipts.filter(status='Received', ledger_posted=True)
    )
    invoiced = sum(i.quantity for i in purchase.items.all())
    if invoiced > 0 and received >= invoiced:
        purchase.status = 'Completed'
    elif purchase.receipts.filter(status='Received').exists():
        purchase.status = 'InTransit'
    purchase.save(update_fields=['status', 'updated_at'])


def register_programming_transfer(programming_id, receipt_data, user, warehouse):
    """Guía de traslado: ingresa al kardex las cantidades programadas por factura."""
    programming = PurchaseProgramming.objects.select_related('truck').prefetch_related(
        'lines__purchase__items',
    ).get(pk=programming_id)

    if programming.status == 'Finished':
        raise ValueError('Esta programación ya fue finalizada')

    prog_lines = list(programming.lines.select_related('purchase').all())
    if not prog_lines:
        raise ValueError('La programación no tiene cantidades asignadas')

    receipt_date = _parse_datetime(receipt_data.get('receipt_date')) or timezone.now()
    net_weight_total = _to_decimal(receipt_data.get('net_weight', 0))
    total_programmed = sum(_to_decimal(line.quantity_kg) for line in prog_lines)

    if net_weight_total <= 0:
        net_weight_total = total_programmed
    if net_weight_total <= 0:
        raise ValueError('El peso neto debe ser mayor a cero')

    travel_cost = programming.travel_expenses_total
    base_freight = _to_decimal(receipt_data.get('freight_cost', 0))
    base_insurance = _to_decimal(receipt_data.get('insurance_cost', 0))
    base_unloading = _to_decimal(receipt_data.get('unloading_cost', 0))
    base_other = _to_decimal(receipt_data.get('other_cost', 0))

    receipts = []
    all_ledgers = []

    with transaction.atomic():
        for line in prog_lines:
            purchase = line.purchase
            line_qty = _to_decimal(line.quantity_kg)
            share = line_qty / total_programmed if total_programmed > 0 else decimal.Decimal(0)
            net_weight = (net_weight_total * share).quantize(decimal.Decimal('0.001'))
            if line_qty > 0 and abs(net_weight - line_qty) > decimal.Decimal('0.5'):
                net_weight = line_qty

            receipt = PurchaseReceipt.objects.create(
                purchase=purchase,
                programming=programming,
                truck=programming.truck,
                warehouse=warehouse,
                receipt_date=receipt_date,
                guide_series=receipt_data.get('guide_series', ''),
                guide_number=receipt_data.get('guide_number', ''),
                weighing_ticket=receipt_data.get('weighing_ticket', ''),
                scop_number=programming.transfer_scop_number,
                vehicle_plate=programming.truck.license_plate,
                trailer_plate=receipt_data.get('trailer_plate', ''),
                driver_name=receipt_data.get('driver_name', ''),
                driver_license=receipt_data.get('driver_license', ''),
                hydrocarbon_registry=receipt_data.get('hydrocarbon_registry', ''),
                gross_weight=_to_decimal(receipt_data.get('gross_weight', 0)) * share,
                tare_weight=_to_decimal(receipt_data.get('tare_weight', 0)) * share,
                net_weight=net_weight,
                volume_gallons=_to_decimal(receipt_data.get('volume_gallons', 0)) * share,
                density=_to_decimal(receipt_data.get('density', 0)),
                temperature=_to_decimal(receipt_data.get('temperature', 0)),
                odorant_ml=_to_decimal(receipt_data.get('odorant_ml', 0)),
                loading_terminal=receipt_data.get('loading_terminal', ''),
                destination=receipt_data.get('destination', ''),
                freight_cost=base_freight * share + travel_cost * share,
                insurance_cost=base_insurance * share,
                unloading_cost=base_unloading * share,
                other_cost=base_other * share,
                received_by=user,
                status='Received',
                remarks=receipt_data.get('remarks', ''),
            )
            receipt.compute_additional_costs()
            receipt.save(update_fields=['total_additional_cost'])
            ledgers = _post_receipt_to_ledger(purchase, receipt, user)
            all_ledgers.extend(ledgers)
            receipts.append(receipt)
            _refresh_purchase_status(purchase)

        programming.status = 'Finished'
        programming.save(update_fields=['status'])

    return receipts, all_ledgers


def register_purchase_transfer(purchase_id, receipt_data, user, warehouse, programming_id=None):
    """Traslado legacy: una factura. Preferir register_programming_transfer."""
    if programming_id:
        return register_programming_transfer(programming_id, receipt_data, user, warehouse)

    purchase = Purchase.objects.prefetch_related('items').get(pk=purchase_id)
    if purchase.status not in ('DetailRegistered', 'ParticipantsRegistered', 'InTransit'):
        raise ValueError('Registre la factura y el detalle antes del traslado')

    receipt_date = _parse_datetime(receipt_data.get('receipt_date')) or timezone.now()
    net_weight = _to_decimal(receipt_data.get('net_weight', 0))
    if net_weight <= 0:
        raise ValueError('El peso neto recibido debe ser mayor a cero')

    with transaction.atomic():
        receipt = PurchaseReceipt.objects.create(
            purchase=purchase,
            warehouse=warehouse,
            receipt_date=receipt_date,
            guide_series=receipt_data.get('guide_series', ''),
            guide_number=receipt_data.get('guide_number', ''),
            weighing_ticket=receipt_data.get('weighing_ticket', ''),
            scop_number=receipt_data.get('scop_number', ''),
            vehicle_plate=receipt_data.get('vehicle_plate', ''),
            trailer_plate=receipt_data.get('trailer_plate', ''),
            driver_name=receipt_data.get('driver_name', ''),
            driver_license=receipt_data.get('driver_license', ''),
            hydrocarbon_registry=receipt_data.get('hydrocarbon_registry', ''),
            gross_weight=_to_decimal(receipt_data.get('gross_weight', 0)),
            tare_weight=_to_decimal(receipt_data.get('tare_weight', 0)),
            net_weight=net_weight,
            volume_gallons=_to_decimal(receipt_data.get('volume_gallons', 0)),
            density=_to_decimal(receipt_data.get('density', 0)),
            temperature=_to_decimal(receipt_data.get('temperature', 0)),
            odorant_ml=_to_decimal(receipt_data.get('odorant_ml', 0)),
            loading_terminal=receipt_data.get('loading_terminal', ''),
            destination=receipt_data.get('destination', ''),
            freight_cost=_to_decimal(receipt_data.get('freight_cost', 0)),
            insurance_cost=_to_decimal(receipt_data.get('insurance_cost', 0)),
            unloading_cost=_to_decimal(receipt_data.get('unloading_cost', 0)),
            other_cost=_to_decimal(receipt_data.get('other_cost', 0)),
            received_by=user,
            status='Received',
            remarks=receipt_data.get('remarks', ''),
        )
        receipt.compute_additional_costs()
        receipt.save(update_fields=['total_additional_cost'])
        ledgers = _post_receipt_to_ledger(purchase, receipt, user)
        _refresh_purchase_status(purchase)

    return [receipt], ledgers
