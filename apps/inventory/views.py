import base64
import decimal
import json
from datetime import datetime
from http import HTTPStatus

from django.contrib.auth.models import User
from django.http import JsonResponse
from django.shortcuts import render
from django.template import loader
from django.views.decorators.csrf import csrf_exempt

from apps.hrm.models import Subsidiary
from apps.hrm.views import get_subsidiary_by_user
from apps.inventory.models import InventoryLedger, PurchaseReceipt, GlpKardexDocument
from apps.inventory.services import (
    GLP_PRODUCT_ID, register_sale_exit,
)
from apps.sales.models import (
    Product, SubsidiaryStore,
)


def _get_glp_kardex_context(request, subsidiary_store=None):
    user_obj = User.objects.get(pk=request.user.id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    product = Product.objects.get(id=GLP_PRODUCT_ID)
    formatdate = datetime.now().strftime('%Y-%m-%d')
    if subsidiary_store is None and request.GET.get('subsidiary_store'):
        subsidiary_store = SubsidiaryStore.objects.filter(
            id=request.GET.get('subsidiary_store'), category='G',
        ).first()
    if subsidiary_store is None:
        subsidiary_store = SubsidiaryStore.objects.filter(
            subsidiary=subsidiary_obj, category='G',
        ).first()
    return {
        'product': product,
        'subsidiary': subsidiary_obj,
        'subsidiaries': Subsidiary.objects.all(),
        'subsidiaries_stores': SubsidiaryStore.objects.filter(category='G'),
        'subsidiary_store': subsidiary_store,
        'date_now': formatdate,
        'user_obj': user_obj,
    }


MOVEMENT_TYPE_LABELS = dict(InventoryLedger.MOVEMENT_TYPE_CHOICES)
DOC_TYPE_LABELS = dict(GlpKardexDocument.DOCUMENT_TYPE_CHOICES)
OPERATION_SUNAT_LABELS = dict(GlpKardexDocument.OPERATION_SUNAT_CHOICES)
OPERATION_LABELS = {
    'E': 'Entrada',
    'S': 'Salida',
    'C': 'Saldo inicial',
}


def _resolve_movement_type(ledger):
    """Compras recibidas se registraban como Transfer; mostrar siempre como Compra."""
    if ledger.reference_type == 'PurchaseReceipt':
        return 'Purchase'
    return ledger.movement_type


def _ledger_row(ledger):
    glp_doc = ledger.get_glp_document()
    doc_type = '00'
    operation_sunat = '16' if ledger.movement_type == 'Adjustment' else '02'
    serial = document_number = document_number_end = partner_ruc = description = ''

    if glp_doc:
        doc_type = glp_doc.document_type
        operation_sunat = glp_doc.operation_sunat
        serial = glp_doc.serial or ''
        document_number = glp_doc.document_number or ''
        document_number_end = glp_doc.document_number_end or ''
        partner_ruc = glp_doc.partner_ruc or ''
        description = glp_doc.description or ''
    elif ledger.reference_type == 'PurchaseReceipt':
        try:
            rec = PurchaseReceipt.objects.select_related('purchase__supplier').get(pk=ledger.reference_id)
            purchase = rec.purchase
            doc_type = '01'
            operation_sunat = '02'
            serial = purchase.series
            document_number = purchase.number
            partner_ruc = purchase.supplier.ruc or ''
            description = f'COMPRA {purchase.document_display}'
            if rec.scop_number:
                description += f' | SCOP {rec.scop_number}'
            if rec.guide_series:
                description += f' | Guía {rec.guide_series}-{rec.guide_number or ""}'
        except PurchaseReceipt.DoesNotExist:
            description = f'COMPRA #{ledger.reference_id}'
    elif ledger.movement_type == 'Sale':
        doc_type = '01'
        operation_sunat = '01'
        description = ledger.remarks or 'VENTA'

    is_entry = ledger.is_entry
    display_type = _resolve_movement_type(ledger)
    doc_display = serial and document_number and f'{serial}-{document_number}' or document_number or '—'
    if document_number_end:
        doc_display = f'{serial}-{document_number} … {serial}-{document_number_end}'

    detail = {
        'id': ledger.id,
        'product_name': ledger.product.name,
        'product_code': ledger.product.code or 'GLP',
        'warehouse': ledger.warehouse.name,
        'date': ledger.movement_date.strftime('%d/%m/%Y %H:%M'),
        'movement_type': display_type,
        'movement_type_label': MOVEMENT_TYPE_LABELS.get(display_type, display_type),
        'operation': ledger.operation_code,
        'operation_label': OPERATION_LABELS.get(ledger.operation_code, ledger.operation_code),
        'doc_type': doc_type,
        'doc_type_label': DOC_TYPE_LABELS.get(doc_type, doc_type),
        'operation_sunat': operation_sunat,
        'operation_sunat_label': OPERATION_SUNAT_LABELS.get(operation_sunat, operation_sunat),
        'serial': serial or '—',
        'document_number': document_number or '—',
        'document_number_end': document_number_end or '',
        'document_display': doc_display,
        'partner_ruc': partner_ruc or '—',
        'description': description or ledger.remarks or '—',
        'reference_type': ledger.reference_type or '—',
        'reference_id': ledger.reference_id,
        'remarks': ledger.remarks or '—',
        'created_by': (
            ledger.created_by.get_full_name() or ledger.created_by.username
            if ledger.created_by else '—'
        ),
        'created_at': ledger.created_at.strftime('%d/%m/%Y %H:%M') if ledger.created_at else '—',
        'qty_in': float(ledger.quantity_in) if is_entry else 0,
        'unit_cost_in': float(ledger.unit_cost) if is_entry else 0,
        'total_in': float(ledger.quantity_in * ledger.unit_cost) if is_entry else 0,
        'qty_out': float(ledger.quantity_out) if not is_entry else 0,
        'unit_cost_out': float(ledger.unit_cost) if not is_entry else 0,
        'total_out': float(ledger.quantity_out * ledger.unit_cost) if not is_entry else 0,
        'balance_qty': float(ledger.balance_quantity),
        'balance_unit_cost': float(ledger.average_cost),
        'balance_total': float(ledger.balance_value),
    }
    detail_json = base64.b64encode(
        json.dumps(detail, ensure_ascii=False).encode('utf-8')
    ).decode('ascii')

    return {
        'id': ledger.id,
        'product_name': ledger.product.name,
        'product_code': ledger.product.code or 'GLP',
        'date': ledger.movement_date,
        'movement_type': display_type,
        'movement_type_label': MOVEMENT_TYPE_LABELS.get(display_type, display_type),
        'reference_type': ledger.reference_type,
        'reference_id': ledger.reference_id,
        'operation': ledger.operation_code,
        'doc_type': doc_type,
        'operation_sunat': operation_sunat,
        'serial': serial,
        'document_number': document_number,
        'document_number_end': document_number_end,
        'partner_ruc': partner_ruc,
        'description': description or ledger.remarks or '—',
        'detail_json': detail_json,
        'qty_in': ledger.quantity_in if is_entry else 0,
        'unit_cost_in': ledger.unit_cost if is_entry else 0,
        'total_in': ledger.quantity_in * ledger.unit_cost if is_entry else 0,
        'qty_out': ledger.quantity_out if not is_entry else 0,
        'unit_cost_out': ledger.unit_cost if not is_entry else 0,
        'total_out': ledger.quantity_out * ledger.unit_cost if not is_entry else 0,
        'balance_qty': ledger.balance_quantity,
        'balance_unit_cost': ledger.average_cost,
        'balance_total': ledger.balance_value,
    }


def _build_ledger_rows(warehouse, start_date, end_date):
    ledgers = InventoryLedger.objects.filter(
        product_id=GLP_PRODUCT_ID,
        warehouse=warehouse,
        movement_date__date__range=[start_date, end_date],
    ).select_related('product', 'glp_document', 'warehouse', 'created_by').order_by('movement_date', 'id')

    return [_ledger_row(lg) for lg in ledgers]


def kardex_valorizado_glp_page(request):
    return render(request, 'inventory/kardex_valorizado_glp.html', _get_glp_kardex_context(request))


def get_kardex_valorizado_glp(request):
    context = _get_glp_kardex_context(request)
    t = loader.get_template('inventory/kardex_valorizado_glp.html')
    return JsonResponse({'success': True, 'form': t.render(context, request)})


def get_list_kardex_valorizado_glp(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    user_obj = User.objects.get(pk=request.user.id)
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')

    try:
        product = Product.objects.get(id=GLP_PRODUCT_ID)
        subsidiary_store = SubsidiaryStore.objects.get(
            id=request.GET.get('subsidiary_store', ''), category='G',
        )
    except (Product.DoesNotExist, SubsidiaryStore.DoesNotExist):
        return JsonResponse({'error': 'Producto o almacén GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)

    rows = _build_ledger_rows(subsidiary_store, start_date, end_date)

    total_entradas_qty = total_entradas = total_salidas_qty = total_salidas = 0
    saldo_final = stock_final = 0

    for r in rows:
        if r['operation'] in ('E', 'C'):
            total_entradas_qty += float(r['qty_in'] or 0)
            total_entradas += float(r['total_in'] or 0)
        if r['operation'] == 'S':
            total_salidas_qty += float(r['qty_out'] or 0)
            total_salidas += float(r['total_out'] or 0)
        saldo_final = float(r['balance_total'] or 0)
        stock_final = float(r['balance_qty'] or 0)

    t = loader.get_template('inventory/kardex_valorizado_glp_grid.html')
    c = {
        'product': product,
        'rows': rows,
        'user_obj': user_obj,
        'start_date': start_date,
        'end_date': end_date,
        'subsidiary_store': subsidiary_store,
        'subsidiary': subsidiary_store.subsidiary,
        'total_entradas_qty': total_entradas_qty,
        'total_entradas': total_entradas,
        'total_salidas_qty': total_salidas_qty,
        'total_salidas': total_salidas,
        'saldo_final': saldo_final,
        'stock_final': stock_final,
    }
    return JsonResponse({'success': True, 'form': t.render(c, request)})


@csrf_exempt
def save_glp_kardex_salida_factura(request):
    """Salida por factura — registra en InventoryLedger."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    try:
        user_obj = User.objects.get(pk=request.user.id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        subsidiary_store = SubsidiaryStore.objects.get(
            id=int(request.POST.get('subsidiary_store', 0)),
            category='G', subsidiary=subsidiary_obj,
        )
        product = Product.objects.get(id=GLP_PRODUCT_ID)
        quantity = decimal.Decimal(str(request.POST.get('quantity', 0)).replace('.', '').replace(',', '.'))

        register_sale_exit(
            product=product,
            warehouse=subsidiary_store,
            movement_date=request.POST.get('movement_date'),
            quantity=quantity,
            user=user_obj,
            doc_data={
                'document_type': '01',
                'serial': request.POST.get('serial', ''),
                'document_number': request.POST.get('document_number', ''),
                'partner_ruc': request.POST.get('partner_ruc', ''),
                'description': request.POST.get('description', 'VENTA'),
            },
        )

        return JsonResponse({'success': True, 'message': 'Salida por factura registrada correctamente'})
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Producto GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)
    except SubsidiaryStore.DoesNotExist:
        return JsonResponse({'error': 'Almacén GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@csrf_exempt
def save_glp_kardex_salida_boleta(request):
    """Salida por bloque de boletas — registra en InventoryLedger."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    try:
        user_obj = User.objects.get(pk=request.user.id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        subsidiary_store = SubsidiaryStore.objects.get(
            id=int(request.POST.get('subsidiary_store', 0)),
            category='G', subsidiary=subsidiary_obj,
        )
        product = Product.objects.get(id=GLP_PRODUCT_ID)
        quantity = decimal.Decimal(str(request.POST.get('quantity', 0)).replace('.', '').replace(',', '.'))
        serial = request.POST.get('serial', '')
        doc_ini = request.POST.get('document_number', '')
        doc_fin = request.POST.get('document_number_end', '')

        register_sale_exit(
            product=product,
            warehouse=subsidiary_store,
            movement_date=request.POST.get('movement_date'),
            quantity=quantity,
            user=user_obj,
            doc_data={
                'document_type': '03',
                'serial': serial,
                'document_number': doc_ini,
                'document_number_end': doc_fin,
                'description': f'VENTA BOLETAS ({serial}-{doc_ini} al {serial}-{doc_fin})',
            },
        )

        return JsonResponse({
            'success': True,
            'message': f'Salida bloque {serial}-{doc_ini} al {serial}-{doc_fin} registrada',
        })
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Producto GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)
    except SubsidiaryStore.DoesNotExist:
        return JsonResponse({'error': 'Almacén GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
