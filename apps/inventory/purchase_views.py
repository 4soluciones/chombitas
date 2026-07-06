import decimal
import json
from datetime import datetime
from http import HTTPStatus

from django.contrib.auth.models import User
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import redirect, render, get_object_or_404
from django.template import loader
from django.views.decorators.csrf import csrf_exempt

from apps.comercial.models import Truck
from apps.hrm.models import Subsidiary
from apps.hrm.views import get_subsidiary_by_user
from apps.inventory.models import (
    Purchase, PurchaseParticipant, PurchaseProgramming, PurchaseTravelExpense,
)
from apps.inventory.services import (
    GLP_DEFAULT_QTY_KG,
    GLP_PRODUCT_ID,
    save_purchase_header,
    save_purchase_with_detail,
    save_purchase_simple_detail,
    save_purchase_participants,
    save_purchase_programmings,
    save_transfer_programming,
    save_travel_expenses,
    set_programming_travel_expenses,
    register_programming_transfer,
    register_purchase_transfer,
    get_purchase_base_unit_pen,
)
from apps.sales.models import Product, SubsidiaryStore, Supplier


GLP_CLIENT_NAME = 'VICTORIA JUAN GAS S.A.C.'


def _participant_suppliers_data():
    return [
        {
            'id': s.id,
            'ruc': s.ruc or '',
            'name': (s.business_name or s.name or '').strip(),
        }
        for s in Supplier.objects.filter(is_enabled=True, sector='G').order_by('business_name', 'name')
        if (s.ruc or '').strip()
    ]


def _purchase_context(request, purchase=None):
    user_obj = User.objects.get(pk=request.user.id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    product = Product.objects.get(id=GLP_PRODUCT_ID)
    return {
        'product': product,
        'subsidiary': subsidiary_obj,
        'subsidiaries': Subsidiary.objects.all(),
        'subsidiaries_stores': SubsidiaryStore.objects.filter(category='G'),
        'suppliers': Supplier.objects.filter(is_enabled=True, sector='G').order_by('name'),
        'participant_suppliers_json': json.dumps(_participant_suppliers_data()),
        'glp_client_name': GLP_CLIENT_NAME,
        'date_now': datetime.now().strftime('%Y-%m-%d'),
        'user_obj': user_obj,
        'purchase': purchase,
        'status_choices': Purchase.STATUS_CHOICES,
        'default_qty_kg': float(GLP_DEFAULT_QTY_KG),
        'trucks': Truck.objects.all().order_by('license_plate'),
        'expense_type_choices': PurchaseTravelExpense.TYPE_CHOICES,
    }


def _purchase_stats(qs):
    return {
        'total': qs.count(),
        'pending_detail': qs.filter(status='InvoiceRegistered').count(),
        'pending_transfer': qs.filter(status__in=('DetailRegistered', 'ParticipantsRegistered', 'InTransit')).count(),
        'completed': qs.filter(status='Completed').count(),
    }


def _filter_purchases(request):
    qs = Purchase.objects.select_related('supplier', 'created_by').prefetch_related(
        'items', 'participants', 'receipts', 'programming_lines__programming',
    ).order_by('-issue_date', '-id')

    status = request.GET.get('status', '')
    if status:
        qs = qs.filter(status=status)

    search = request.GET.get('search', '').strip()
    if search:
        qs = qs.filter(
            Q(series__icontains=search) | Q(number__icontains=search)
            | Q(scop_number__icontains=search)
            | Q(supplier__name__icontains=search) | Q(supplier__business_name__icontains=search)
        )

    start = request.GET.get('start_date', '')
    end = request.GET.get('end_date', '')
    if start and end:
        qs = qs.filter(issue_date__range=[start, end])
    return qs


def _purchases_available_for_programming():
    """Facturas con saldo KG disponible para programar."""
    result = []
    for p in Purchase.objects.filter(
        status__in=('DetailRegistered', 'ParticipantsRegistered', 'InTransit'),
    ).select_related('supplier').prefetch_related('items', 'receipts', 'programming_lines'):
        available = float(p.qty_available_for_programming)
        if available <= 0:
            continue
        result.append({
            'id': p.id,
            'document': p.document_display,
            'scop': p.scop_number or '',
            'supplier': (p.supplier.business_name or p.supplier.name or '')[:40],
            'invoiced_kg': float(p.invoiced_qty_total),
            'received_kg': float(p.received_qty_total),
            'pending_kg': float(p.qty_pending_programming),
            'available_kg': available,
        })
    return result


def _purchases_for_programming():
    return Purchase.objects.filter(
        status__in=('DetailRegistered', 'ParticipantsRegistered', 'InTransit'),
    ).select_related('supplier').prefetch_related(
        'items', 'receipts', 'programming_lines',
    ).order_by('-issue_date')[:100]


def glp_purchase_list_page(request):
    ctx = _purchase_context(request)
    qs = _filter_purchases(request)
    ctx['purchases'] = qs[:50]
    ctx['stats'] = _purchase_stats(qs)
    return render(request, 'inventory/purchase_list.html', ctx)


def get_glp_purchase_list(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)

    qs = _filter_purchases(request)
    t = loader.get_template('inventory/purchase_grid.html')
    html = t.render({'purchases': qs}, request)
    return JsonResponse({
        'success': True,
        'form': html,
        'stats': _purchase_stats(qs),
    })


def glp_purchase_create_page(request):
    from django.urls import reverse
    return redirect(reverse('inventory:glp_purchase_list') + '?new=1')


def glp_purchase_detail_page(request, pk):
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier', 'created_by').prefetch_related(
            'items__product', 'participants', 'receipts__warehouse',
            'programming_lines__programming__truck',
            'programming_lines__programming__travel_expenses',
        ),
        pk=pk,
    )
    ctx = _purchase_context(request, purchase)
    ctx['participants'] = purchase.participants.all()
    ctx['receipts'] = purchase.receipts.all().order_by('-receipt_date')
    ctx['items'] = purchase.items.all()
    ctx['programmings'] = PurchaseProgramming.objects.filter(
        lines__purchase=purchase,
    ).distinct().prefetch_related('lines__purchase', 'truck')
    item = purchase.items.first()
    ctx['main_item'] = item
    return render(request, 'inventory/purchase_detail.html', ctx)


def get_glp_purchase_invoice_modal(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    ctx = _purchase_context(request)
    t = loader.get_template('inventory/modals/purchase_invoice_new.html')
    return JsonResponse({'form': t.render(ctx, request)})


def get_glp_purchase_summary_modal(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    pk = request.GET.get('pk')
    purchase = get_object_or_404(
        Purchase.objects.select_related('supplier').prefetch_related(
            'items__product', 'programming_lines__programming__truck',
            'receipts__warehouse',
        ),
        pk=pk,
    )
    ctx = _purchase_context(request, purchase)
    ctx['main_item'] = purchase.items.first()
    ctx['programmings'] = PurchaseProgramming.objects.filter(
        lines__purchase=purchase,
    ).distinct().prefetch_related('lines__purchase', 'truck')
    ctx['receipts'] = purchase.receipts.all().order_by('-receipt_date')
    t = loader.get_template('inventory/modals/purchase_summary_modal.html')
    return JsonResponse({'form': t.render(ctx, request)})


def get_glp_purchase_programming_modal(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    ctx = _purchase_context(request)
    ctx['purchases_available'] = _purchases_available_for_programming()
    ctx['purchases_available_json'] = json.dumps(ctx['purchases_available'])
    ctx['programmings'] = PurchaseProgramming.objects.filter(
        status='Pending',
    ).prefetch_related('lines__purchase', 'truck').order_by('-programming_date')[:30]
    t = loader.get_template('inventory/modals/purchase_programming.html')
    return JsonResponse({'form': t.render(ctx, request)})


def get_glp_programming_detail(request, pk):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    prog = get_object_or_404(
        PurchaseProgramming.objects.select_related('truck').prefetch_related(
            'lines__purchase__supplier',
        ),
        pk=pk,
    )
    purchases = []
    for line in prog.lines.all():
        purchases.append({
            'id': line.purchase_id,
            'document': line.purchase.document_display,
            'scop': line.purchase.scop_number or '',
            'supplier': (line.purchase.supplier.business_name or line.purchase.supplier.name or '')[:40],
            'quantity_kg': float(line.quantity_kg),
            'available_kg': float(line.purchase.qty_available_for_programming),
            'unit_price_pen': float(get_purchase_base_unit_pen(line.purchase)),
            'currency': line.purchase.currency,
        })
    return JsonResponse({
        'success': True,
        'programming': {
            'id': prog.id,
            'scop': prog.transfer_scop_number,
            'truck': prog.truck.license_plate,
            'status': prog.status,
            'total_kg': float(prog.total_quantity_kg),
            'travel_expenses_total': float(prog.travel_expenses_total),
        },
        'lines': purchases,
    })


def get_glp_purchase_warehouse_modal(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    user_obj = User.objects.get(pk=request.user.id)
    subsidiary_obj = get_subsidiary_by_user(user_obj)
    ctx = _purchase_context(request)
    ctx['programmings_pending'] = PurchaseProgramming.objects.filter(
        status='Pending',
    ).prefetch_related('lines__purchase').select_related('truck').order_by('-programming_date')
    ctx['subsidiaries_stores'] = SubsidiaryStore.objects.filter(
        category='G', subsidiary=subsidiary_obj,
    )
    t = loader.get_template('inventory/modals/purchase_warehouse.html')
    return JsonResponse({'form': t.render(ctx, request)})


def get_glp_purchase_expense_modal(request):
    if request.method != 'GET':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    ctx = _purchase_context(request)
    ctx['programmings'] = PurchaseProgramming.objects.filter(
        status='Pending',
    ).prefetch_related('lines__purchase').select_related('truck').order_by('-programming_date')
    t = loader.get_template('inventory/modals/purchase_travel_expense.html')
    return JsonResponse({'form': t.render(ctx, request)})


@csrf_exempt
def save_purchase_header_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    try:
        user_obj = User.objects.get(pk=request.user.id)
        payload = json.loads(request.body.decode('utf-8'))
        detail = payload.get('detail')
        product_id = payload.get('product_id', GLP_PRODUCT_ID)

        if detail:
            purchase = save_purchase_with_detail(
                purchase_data=payload.get('purchase', {}),
                detail_data=detail,
                product_id=product_id,
                user=user_obj,
                purchase_id=payload.get('purchase_id'),
            )
        else:
            purchase = save_purchase_header(
                purchase_data=payload.get('purchase', {}),
                user=user_obj,
                purchase_id=payload.get('purchase_id'),
            )

        item = purchase.items.first()
        return JsonResponse({
            'success': True,
            'message': f'Factura {purchase.document_display} registrada',
            'purchase_id': purchase.id,
            'summary_url': f'/inventory/get_glp_purchase_summary_modal/?pk={purchase.id}',
            'unit_price_excl': float(item.unit_price) if item else 0,
            'unit_price_incl': float(item.unit_price_incl_igv) if item else 0,
            'quantity': float(item.quantity) if item else 0,
            'total': float(purchase.total),
        })
    except Purchase.DoesNotExist:
        return JsonResponse({'error': 'Compra no encontrada'}, status=HTTPStatus.NOT_FOUND)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'JSON inválido'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@csrf_exempt
def save_purchase_detail_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    try:
        user_obj = User.objects.get(pk=request.user.id)
        payload = json.loads(request.body.decode('utf-8'))
        purchase_id = payload['purchase_id']
        detail = payload.get('detail', {})
        participants_data = payload.get('participants')
        uses_participants = isinstance(participants_data, list)

        if uses_participants:
            if not participants_data:
                return JsonResponse(
                    {'error': 'Debe registrar al menos un participante'},
                    status=HTTPStatus.BAD_REQUEST,
                )
            purchase = save_purchase_participants(
                purchase_id=purchase_id,
                participants_data=participants_data,
                user=user_obj,
            )
        else:
            purchase = save_purchase_simple_detail(
                purchase_id=purchase_id,
                detail_data=detail,
                product_id=payload.get('product_id', GLP_PRODUCT_ID),
                user=user_obj,
            )

        item = purchase.items.first()
        return JsonResponse({
            'success': True,
            'message': 'Detalle registrado correctamente',
            'purchase_id': purchase.id,
            'unit_price_excl': float(item.unit_price) if item else 0,
            'unit_price_incl': float(item.unit_price_incl_igv) if item else 0,
            'quantity': float(item.quantity) if item else 0,
            'total': float(purchase.total),
        })
    except (KeyError, json.JSONDecodeError):
        return JsonResponse({'error': 'Datos incompletos'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@csrf_exempt
def save_purchase_programming_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    try:
        user_obj = User.objects.get(pk=request.user.id)
        payload = json.loads(request.body.decode('utf-8'))

        if payload.get('lines'):
            programming = save_transfer_programming(
                truck_id=payload['truck_id'],
                transfer_scop_number=payload['transfer_scop_number'],
                lines=payload['lines'],
                user=user_obj,
                programming_date=payload.get('programming_date'),
            )
            total_kg = float(programming.total_quantity_kg)
            return JsonResponse({
                'success': True,
                'message': (
                    f'Programación SCOP {programming.transfer_scop_number} — '
                    f'{programming.lines.count()} factura(s), {total_kg:,.3f} KG total'
                ),
                'programming_id': programming.id,
                'total_kg': total_kg,
            })

        return JsonResponse({'error': 'Debe enviar las líneas de programación'}, status=HTTPStatus.BAD_REQUEST)
    except (KeyError, json.JSONDecodeError):
        return JsonResponse({'error': 'Datos incompletos'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@csrf_exempt
def save_purchase_travel_expense_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    try:
        user_obj = User.objects.get(pk=request.user.id)
        payload = json.loads(request.body.decode('utf-8'))
        rows = save_travel_expenses(
            programming_id=payload['programming_id'],
            rows=payload.get('rows', []),
            user=user_obj,
        )
        return JsonResponse({
            'success': True,
            'message': f'{len(rows)} gasto(s) registrado(s)',
            'count': len(rows),
        })
    except (KeyError, json.JSONDecodeError):
        return JsonResponse({'error': 'Datos incompletos'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)


@csrf_exempt
def save_purchase_transfer_view(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Método no permitido'}, status=HTTPStatus.METHOD_NOT_ALLOWED)
    try:
        user_obj = User.objects.get(pk=request.user.id)
        subsidiary_obj = get_subsidiary_by_user(user_obj)
        payload = json.loads(request.body.decode('utf-8'))

        warehouse = SubsidiaryStore.objects.get(
            id=int(payload.get('warehouse_id', 0)),
            category='G',
            subsidiary=subsidiary_obj,
        )

        programming_id = payload.get('programming_id')
        if not programming_id:
            return JsonResponse({'error': 'Seleccione la programación de traslado'}, status=HTTPStatus.BAD_REQUEST)

        set_programming_travel_expenses(
            programming_id=int(programming_id),
            rows=payload.get('expenses', []),
            user=user_obj,
        )

        receipts, ledgers = register_programming_transfer(
            programming_id=int(programming_id),
            receipt_data=payload.get('receipt', {}),
            user=user_obj,
            warehouse=warehouse,
        )

        if not receipts:
            return JsonResponse({'error': 'No se generaron recepciones'}, status=HTTPStatus.BAD_REQUEST)

        return JsonResponse({
            'success': True,
            'message': (
                f'Guía {receipts[0].guide_series or ""}-{receipts[0].guide_number or ""} registrada. '
                f'{len(receipts)} factura(s) ingresada(s) al kardex ({len(ledgers)} movimiento(s)).'
            ),
            'receipt_ids': [r.id for r in receipts],
            'ledger_count': len(ledgers),
        })
    except SubsidiaryStore.DoesNotExist:
        return JsonResponse({'error': 'Almacén GLP no encontrado'}, status=HTTPStatus.BAD_REQUEST)
    except ValueError as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.BAD_REQUEST)
    except Exception as exc:
        return JsonResponse({'error': str(exc)}, status=HTTPStatus.INTERNAL_SERVER_ERROR)
