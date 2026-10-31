import base64
import decimal
import json
from datetime import datetime
from http import HTTPStatus
from io import BytesIO

from django.contrib.auth.models import User
from django.http import HttpResponse, JsonResponse
from django.shortcuts import render
from django.template import loader
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from apps.inventory.models import InventoryLedger, PurchaseReceipt, GlpKardexDocument
from apps.inventory.services import (
    GLP_PRODUCT_ID, GLP_SUBSIDIARY_ID, GLP_WAREHOUSE_ID, register_sale_exit,
)
from apps.sales.models import (
    Product, SubsidiaryStore,
)


def _glp_place():
    """El kardex valorizado es siempre Sicuani / Pluspetrol."""
    store = SubsidiaryStore.objects.select_related('subsidiary').get(
        pk=GLP_WAREHOUSE_ID, category='G', subsidiary_id=GLP_SUBSIDIARY_ID,
    )
    return store.subsidiary, store


def _kardex_dates(request):
    start_date = request.GET.get('start_date', '')
    end_date = request.GET.get('end_date', '')
    try:
        datetime.strptime(start_date, '%Y-%m-%d')
        datetime.strptime(end_date, '%Y-%m-%d')
    except ValueError:
        return None
    if start_date > end_date:
        return None
    return start_date, end_date


def _get_glp_kardex_context(request, subsidiary_store=None):
    user_obj = User.objects.get(pk=request.user.id)
    subsidiary_obj, subsidiary_store = _glp_place()
    product = Product.objects.get(id=GLP_PRODUCT_ID)
    formatdate = datetime.now().strftime('%Y-%m-%d')
    return {
        'product': product,
        'subsidiary': subsidiary_obj,
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
    period = _kardex_dates(request)
    if not period:
        return JsonResponse({'error': 'Indique un rango de fechas válido'}, status=HTTPStatus.BAD_REQUEST)
    start_date, end_date = period

    try:
        product = Product.objects.get(id=GLP_PRODUCT_ID)
        subsidiary_obj, subsidiary_store = _glp_place()
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
        'subsidiary': subsidiary_obj,
        'total_entradas_qty': total_entradas_qty,
        'total_entradas': total_entradas,
        'total_salidas_qty': total_salidas_qty,
        'total_salidas': total_salidas,
        'saldo_final': saldo_final,
        'stock_final': stock_final,
    }
    return JsonResponse({'success': True, 'form': t.render(c, request)})


def _excel_fill(color):
    return PatternFill(start_color=color, end_color=color, fill_type='solid')


def _excel_border():
    thin = Side(border_style='thin', color='D0D7DE')
    return Border(left=thin, right=thin, top=thin, bottom=thin)


def export_kardex_valorizado_glp_excel(request):
    """Descarga el kardex del período en Excel. openpyxl 3.0 funciona con Django 3.0."""
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    period = _kardex_dates(request)
    if not period:
        return JsonResponse({'error': 'Indique un rango de fechas válido'}, status=HTTPStatus.BAD_REQUEST)
    start_date, end_date = period
    subsidiary, store = _glp_place()
    rows = _build_ledger_rows(store, start_date, end_date)

    wb = Workbook()
    ws = wb.active
    ws.title = 'Kardex GLP'
    headers = [
        'N°', 'Producto', 'Código', 'Fecha', 'Tipo', 'Operación SUNAT', 'Tipo doc.',
        'Serie', 'Número', 'Cant. ingreso', 'C.U. ingreso', 'Total ingreso',
        'Cant. salida', 'C.U. salida', 'Total salida', 'Cant. saldo', 'C.U. saldo',
        'Valor saldo', 'RUC', 'Descripción',
    ]
    last_col = len(headers)
    title_font = Font(name='Calibri', size=14, bold=True, color='FFFFFF')
    meta_font = Font(name='Calibri', size=11, color='FFFFFF')
    head_font = Font(name='Calibri', size=9, bold=True, color='FFFFFF')
    text_font = Font(name='Calibri', size=9)
    navy = _excel_fill('0D3B66')
    green = _excel_fill('1B7A4E')
    red = _excel_fill('C0392B')
    blue = _excel_fill('1A5F8A')
    slate = _excel_fill('5A6A7E')
    border = _excel_border()
    center = Alignment(horizontal='center', vertical='center', wrap_text=True)
    right = Alignment(horizontal='right', vertical='center')

    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=last_col)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=last_col)
    ws.merge_cells(start_row=3, start_column=1, end_row=3, end_column=last_col)
    ws['A1'] = subsidiary.business_name or subsidiary.name
    ws['A1'].font = title_font
    ws['A1'].fill = navy
    ws['A1'].alignment = Alignment(horizontal='left', vertical='center')
    ws['A2'] = 'KARDEX VALORIZADO GLP  ·  Formato 13.1  ·  Promedio ponderado en soles'
    ws['A2'].font = meta_font
    ws['A2'].fill = navy
    start_label = datetime.strptime(start_date, '%Y-%m-%d').strftime('%d/%m/%Y')
    end_label = datetime.strptime(end_date, '%Y-%m-%d').strftime('%d/%m/%Y')
    ws['A3'] = (
        f'RUC {subsidiary.ruc}   ·   Sede {subsidiary.name}   ·   '
        f'Almacén {store.name}   ·   Período {start_label} al {end_label}'
    )
    ws['A3'].font = meta_font
    ws['A3'].fill = navy
    ws.row_dimensions[1].height = 24
    ws.row_dimensions[2].height = 18
    ws.row_dimensions[3].height = 18

    header_fills = (
        [navy] * 9 + [green] * 3 + [red] * 3 + [blue] * 3 + [slate] * 2
    )
    for col, title in enumerate(headers, 1):
        cell = ws.cell(5, col, title)
        cell.font = head_font
        cell.fill = header_fills[col - 1]
        cell.alignment = center
        cell.border = border
    ws.row_dimensions[5].height = 30
    ws.freeze_panes = 'A6'
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToPage = True
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.oddHeader.left.text = 'Kardex valorizado GLP'
    ws.oddFooter.right.text = 'Página &P de &N'
    ws.print_title_rows = '1:5'
    ws.page_setup.horizontalCentered = True
    ws.sheet_view.showGridLines = False
    ws.sheet_view.zoomScale = 110
    ws.page_margins.left = 0.4
    ws.page_margins.right = 0.4
    ws.page_margins.top = 0.6
    ws.page_margins.bottom = 0.6

    qty_format = '#,##0.000'
    cost_format = '#,##0.000000'
    money_format = '"S/" #,##0.00'
    zebra = _excel_fill('F7F9FB')
    entry_fill = _excel_fill('F3FAF6')
    exit_fill = _excel_fill('FDF6F5')

    first_data = 6
    for offset, row in enumerate(rows):
        excel_row = first_data + offset
        when = timezone.localtime(row['date'])
        number = row['document_number'] or ''
        if row['document_number_end']:
            number = f'{row["serial"]}-{row["document_number"]} al {row["serial"]}-{row["document_number_end"]}'
        values = [
            row['id'], row['product_name'], row['product_code'],
            when.strftime('%d/%m/%Y %H:%M'), row['movement_type_label'],
            row['operation_sunat'], row['doc_type'], row['serial'] or '',
            number,
            float(row['qty_in'] or 0), float(row['unit_cost_in'] or 0), float(row['total_in'] or 0),
            float(row['qty_out'] or 0), float(row['unit_cost_out'] or 0), float(row['total_out'] or 0),
            float(row['balance_qty'] or 0), float(row['balance_unit_cost'] or 0), float(row['balance_total'] or 0),
            row['partner_ruc'] or '', row['description'] or '',
        ]
        band = entry_fill if row['operation'] in ('E', 'C') else exit_fill if row['operation'] == 'S' else zebra
        for col, value in enumerate(values, 1):
            show = None if col in (10, 11, 12, 13, 14, 15) and not value else value
            cell = ws.cell(excel_row, col, show)
            cell.font = text_font
            cell.border = border
            cell.fill = band
            if col in (10, 13, 16):
                cell.number_format = qty_format
                cell.alignment = right
            elif col in (11, 14, 17):
                cell.number_format = cost_format
                cell.alignment = right
            elif col in (12, 15, 18):
                cell.number_format = money_format
                cell.alignment = right
            elif col in (1, 4, 5, 6, 7, 8):
                cell.alignment = center

    last_data = first_data + len(rows) - 1
    if rows:
        ws.auto_filter.ref = f'A5:{get_column_letter(last_col)}{last_data}'
    total_row = (last_data + 1) if rows else first_data
    if rows:
        ws.cell(total_row, 9, 'TOTALES')
        for col, fmt in ((10, qty_format), (12, money_format), (13, qty_format), (15, money_format)):
            letter = get_column_letter(col)
            cell = ws.cell(total_row, col, f'=SUM({letter}{first_data}:{letter}{last_data})')
            cell.number_format = fmt
            cell.alignment = right
        for col, source in ((16, 16), (18, 18)):
            cell = ws.cell(total_row, col, f'={get_column_letter(source)}{last_data}')
            cell.number_format = qty_format if col == 16 else money_format
            cell.alignment = right
        for col in range(1, last_col + 1):
            cell = ws.cell(total_row, col)
            cell.font = Font(name='Calibri', size=9, bold=True)
            cell.fill = _excel_fill('E8EEF4')
            cell.border = border
    else:
        ws.cell(total_row, 1, 'Sin movimientos en el período')

    widths = [10, 22, 12, 18, 14, 12, 12, 10, 28, 16, 16, 16, 16, 16, 16, 16, 16, 18, 14, 42]
    for index, width in enumerate(widths, 1):
        ws.column_dimensions[get_column_letter(index)].width = width

    buffer = BytesIO()
    wb.save(buffer)
    filename = f'Kardex_GLP_{start_date}_{end_date}.xlsx'
    response = HttpResponse(
        buffer.getvalue(),
        content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    return response


@csrf_exempt
def save_glp_kardex_salida_factura(request):
    """Salida por factura — registra en InventoryLedger."""
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    try:
        user_obj = User.objects.get(pk=request.user.id)
        subsidiary_obj, subsidiary_store = _glp_place()
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
        subsidiary_obj, subsidiary_store = _glp_place()
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
