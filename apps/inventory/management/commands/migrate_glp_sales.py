# -*- coding: utf-8 -*-
"""
Rehace el kardex valorizado de GLP metiendo las ventas de Nubefact
entre las compras, en soles.

Ventas desde el 2 de enero de 2024 hasta el 28 de marzo de 2025.
2023 no entra: no hay compras de ese año y el saldo inicial no alcanza.

Las boletas de una misma serie y día se agrupan en rangos correlativos.
Cada factura es una fila. La nota de crédito entra como devolución.
La salida usa el costo promedio vigente. El precio de venta no se usa.
El mismo día, primero las guías y después las ventas.

No mueve el stock operativo de ProductStore.

Uso:
    python manage.py migrate_glp_sales
    python manage.py migrate_glp_sales --apply
"""
import datetime
import re
import zipfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.inventory.management.commands.migrate_glp_purchases import (
    KG,
    OPENING_DATE,
    OPENING_QTY_KG,
    OPENING_REFERENCE,
    PEN,
    UNIT,
    WAREHOUSE_ID,
    _aware,
    _q,
)
from apps.inventory.models import GlpKardexDocument, InventoryLedger, PurchaseReceipt
from apps.inventory.services import GLP_PRODUCT_ID
from apps.sales.models import Product, ProductStore, SubsidiaryStore

SOURCE = Path(r'C:\Users\jholp\Documents\info victoria kardex nubefact')
SALES_FROM = datetime.date(2024, 1, 2)
SALES_TO = datetime.date(2025, 3, 28)

KG_RE = re.compile(r'(\d+(?:[.,]\d+)?)\s*KG')
BALON_RE = re.compile(r'BALON DE\s*(\d+(?:[.,]\d+)?)')
COLS = {
    'A': 'fecha', 'B': 'tipo', 'C': 'serie', 'D': 'numero',
    'E': 'doc_tipo', 'F': 'doc_num', 'L': 'desc', 'M': 'qty', 'Z': 'anulado',
}


def _parse_date(value):
    text = (value or '').strip()
    for fmt in ('%d/%m/%Y', '%Y-%m-%d'):
        try:
            return datetime.datetime.strptime(text[:10], fmt).date()
        except ValueError:
            continue
    return None


def _num(value):
    try:
        return Decimal(str(value).strip() or '0')
    except Exception:
        return Decimal(0)


def _whole(value):
    text = str(value or '').strip()
    if text.endswith('.0'):
        text = text[:-2]
    if text.isdigit():
        return int(text)
    return None


def _cells(chunk):
    text = chunk.decode('utf-8', 'replace')
    found = {}
    pos = 0
    while True:
        start = text.find('<c r="', pos)
        if start < 0:
            break
        end = text.find('"', start + 6)
        col = ''.join(ch for ch in text[start + 6:end] if ch.isalpha())
        close = text.find('</c>', end)
        body = text[end:close]
        pos = close + 4
        if col not in COLS:
            continue
        if '<v>' in body:
            value = body[body.find('<v>') + 3:body.find('</v>')]
        elif '<t' in body:
            left = body.find('>', body.find('<t'))
            right = body.find('</t>')
            value = body[left + 1:right]
        else:
            value = ''
        found[COLS[col]] = value.replace('&#10;', ' ').replace('&amp;', '&').strip()
    return found


def _rows(path):
    archive = zipfile.ZipFile(path)
    data = archive.read('xl/worksheets/sheet1.xml')
    archive.close()
    start = data.find(b'<row ')
    first = True
    while start >= 0:
        end = data.find(b'</row>', start)
        if not first:
            yield _cells(data[start:end])
        first = False
        start = data.find(b'<row ', end)


def _balloon_kg(description, quantity):
    text = ' '.join(description.upper().split())
    if 'BALON' not in text:
        return None
    match = KG_RE.search(text) or BALON_RE.search(text)
    if not match:
        return None
    weight = Decimal(match.group(1).replace(',', '.'))
    if weight <= 0 or quantity <= 0:
        return None
    return quantity * weight


class Command(BaseCommand):
    help = 'Rehace el kardex GLP con las ventas Nubefact de 2024 y el primer trimestre de 2025.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Escribe el kardex. Sin esto solo simula.')
        parser.add_argument('--source', default=str(SOURCE), help='Carpeta de los Excel de Nubefact.')

    def handle(self, *args, **options):
        product = Product.objects.get(pk=GLP_PRODUCT_ID)
        warehouse = SubsidiaryStore.objects.get(pk=WAREHOUSE_ID)
        stock_before = self._stock()
        sales, stats = self._read_sales(Path(options['source']))
        purchases = self._purchases(warehouse)
        opening_unit = purchases[0]['unit_cost'] if purchases else Decimal(0)
        moves = self._moves(opening_unit, purchases, sales)
        rows, summary = self._replay(moves)

        self.stdout.write(f'Almacén: {warehouse.id} {warehouse.name}')
        self.stdout.write(f'Stock operativo antes: {stock_before}')
        self.stdout.write(
            f'Ventas {SALES_FROM} a {SALES_TO}: '
            f'{stats["facturas"]} facturas, {stats["rangos"]} rangos de boleta, '
            f'{stats["notas"]} notas de crédito'
        )
        self.stdout.write(
            f'Kg ventas {summary["sale_kg"]} | kg devoluciones {summary["credit_kg"]} | '
            f'kg compras {summary["purchase_kg"]}'
        )
        self.stdout.write(
            f'Lineas leidas {stats["lines"]} | anuladas {stats["anuladas"]} | '
            f'sin balon {stats["otras"]} | fuera de rango {stats["fuera"]}'
        )
        self.stdout.write(
            f'Saldo mínimo {summary["min_qty"]} kg el {summary["min_day"]} | '
            f'saldo final {summary["final_qty"]} kg a S/ {summary["final_avg"]}'
        )
        if summary['short']:
            day, have, need = summary['short']
            raise CommandError(
                f'Stock insuficiente el {day}: hay {have} kg y la salida pide {need} kg.'
            )
        if not options['apply']:
            self.stdout.write(self.style.WARNING('Sin --apply no se escribió nada.'))
            return

        with transaction.atomic():
            self._replace(product, warehouse, rows)
        stock_after = self._stock()
        self.stdout.write(f'Stock operativo después: {stock_after}')
        if stock_after != stock_before:
            raise CommandError('El stock operativo cambió. La carga no debía tocarlo.')
        self.stdout.write(self.style.SUCCESS(
            f'Kardex rehecho: {len(rows)} movimientos. Stock operativo sigue en {stock_after}.'
        ))

    def _stock(self):
        row = ProductStore.objects.filter(
            product_id=GLP_PRODUCT_ID, subsidiary_store_id=WAREHOUSE_ID,
        ).first()
        return row.stock if row else None

    def _read_sales(self, root):
        facturas = {}
        boletas = defaultdict(lambda: defaultdict(Decimal))
        notas = {}
        stats = {'lines': 0, 'anuladas': 0, 'otras': 0, 'fuera': 0, 'facturas': 0, 'rangos': 0, 'notas': 0}
        files = sorted(path for year in ('2024', '2025') for path in (root / year).glob('*.xlsx'))
        if not files:
            raise CommandError(f'No hay Excel en {root}')
        for path in files:
            count = 0
            for rec in _rows(path):
                count += 1
                stats['lines'] += 1
                day = _parse_date(rec.get('fecha'))
                if day is None or day < SALES_FROM or day > SALES_TO:
                    stats['fuera'] += 1
                    continue
                if (rec.get('anulado') or '').upper() == 'SI':
                    stats['anuladas'] += 1
                    continue
                tipo = (rec.get('tipo') or '').zfill(2)
                if tipo not in ('01', '03', '07'):
                    stats['otras'] += 1
                    continue
                kg = _balloon_kg(rec.get('desc') or '', _num(rec.get('qty')))
                if kg is None:
                    stats['otras'] += 1
                    continue
                serie = (rec.get('serie') or '').strip().upper()
                numero = _whole(rec.get('numero'))
                if not serie or numero is None:
                    stats['otras'] += 1
                    continue
                if tipo == '03':
                    boletas[(day, serie)][numero] += kg
                elif tipo == '01':
                    key = (day, serie, numero)
                    slot = facturas.setdefault(key, {'kg': Decimal(0), 'ruc': ''})
                    slot['kg'] += kg
                    ruc = self._ruc(rec)
                    if ruc:
                        slot['ruc'] = ruc
                else:
                    notas[(day, serie, numero)] = notas.get((day, serie, numero), Decimal(0)) + kg
            self.stdout.write(f'  {path.parent.name} {path.name} lineas {count}')

        sales = []
        for (day, serie), numbers in boletas.items():
            ordered = sorted(numbers)
            start = prev = ordered[0]
            total = numbers[start]
            ranges = []
            for numero in ordered[1:]:
                if numero == prev + 1:
                    prev = numero
                    total += numbers[numero]
                else:
                    ranges.append((start, prev, total))
                    start = prev = numero
                    total = numbers[numero]
            ranges.append((start, prev, total))
            for ini, fin, kg in ranges:
                sales.append({
                    'kind': 'sale', 'day': day, 'serie': serie, 'numero': ini,
                    'numero_fin': fin if fin != ini else None, 'kg': kg,
                    'doc_type': '03', 'ruc': '',
                })
        for (day, serie, numero), slot in facturas.items():
            sales.append({
                'kind': 'sale', 'day': day, 'serie': serie, 'numero': numero,
                'numero_fin': None, 'kg': slot['kg'], 'doc_type': '01', 'ruc': slot['ruc'],
            })
        for (day, serie, numero), kg in notas.items():
            sales.append({
                'kind': 'credit', 'day': day, 'serie': serie, 'numero': numero,
                'numero_fin': None, 'kg': kg, 'doc_type': '07', 'ruc': '',
            })
        stats['facturas'] = len(facturas)
        stats['rangos'] = sum(1 for item in sales if item['doc_type'] == '03')
        stats['notas'] = len(notas)
        return sales, stats

    def _ruc(self, rec):
        if (rec.get('doc_tipo') or '').strip() != '6':
            return ''
        ruc = ''.join(ch for ch in (rec.get('doc_num') or '') if ch.isdigit())
        if len(ruc) == 11 and set(ruc) != {'0'}:
            return ruc
        return ''

    def _purchases(self, warehouse):
        receipts = PurchaseReceipt.objects.filter(
            warehouse=warehouse,
            status='Received',
            purchase__remarks__contains='[req:',
        ).select_related('purchase__supplier').prefetch_related('purchase__items').order_by('receipt_date', 'id')
        rows = []
        for receipt in receipts:
            item = receipt.purchase.items.first()
            if not item or not receipt.net_weight:
                continue
            rows.append({
                'id': receipt.id,
                'day': timezone.localtime(receipt.receipt_date).date(),
                'when': receipt.receipt_date,
                'kg': receipt.net_weight,
                'unit_cost': item.unit_price,
                'remarks': receipt.purchase.remarks or '',
                'serial': receipt.purchase.series or '',
                'number': receipt.purchase.number or '',
                'ruc': receipt.purchase.supplier.ruc or '',
                'description': (
                    f'INGRESO GLP {receipt.purchase.document_display}'
                    f' | Guía {receipt.guide_number}'
                    f' | SCOP {receipt.scop_number}'
                )[:200],
            })
        if not rows:
            raise CommandError('No hay guías de compra para rehacer el kardex.')
        return rows

    def _moves(self, opening_unit, purchases, sales):
        moves = [{
            'kind': 'opening', 'day': OPENING_DATE, 'seq': 0,
            'kg': OPENING_QTY_KG, 'unit_cost': opening_unit,
        }]
        for row in purchases:
            moves.append({
                'kind': 'purchase', 'day': row['day'], 'seq': row['id'], **row,
            })
        for index, row in enumerate(sales):
            row['seq'] = index
            moves.append(row)
        order = {'opening': 0, 'purchase': 1, 'sale': 2, 'credit': 3}
        moves.sort(key=lambda item: (item['day'], order[item['kind']], item['seq'], item.get('numero') or 0))
        return moves

    def _replay(self, moves):
        bal_qty = Decimal(0)
        bal_value = Decimal(0)
        average = Decimal(0)
        rows = []
        min_qty = None
        min_day = None
        short = None
        sale_kg = Decimal(0)
        credit_kg = Decimal(0)
        purchase_kg = Decimal(0)
        for move in moves:
            qty = _q(move['kg'], KG)
            if qty <= 0:
                continue
            kind = move['kind']
            if kind in ('opening', 'purchase'):
                unit = _q(move['unit_cost'], UNIT)
                new_qty = _q(bal_qty + qty, KG)
                new_value = _q(bal_value + (qty * unit), PEN)
                average = _q(new_value / new_qty, UNIT) if new_qty else unit
                bal_qty, bal_value = new_qty, new_value
                if kind == 'purchase':
                    purchase_kg += qty
                rows.append(self._entry(move, qty, unit, bal_qty, average, bal_value))
            elif kind == 'sale':
                if bal_qty < qty:
                    short = (move['day'], bal_qty, qty)
                    break
                unit = average
                new_qty = _q(bal_qty - qty, KG)
                new_value = _q(bal_value - _q(qty * unit, PEN), PEN)
                if new_qty == 0:
                    new_value = Decimal(0)
                bal_qty, bal_value = new_qty, new_value
                sale_kg += qty
                rows.append(self._exit(move, qty, unit, bal_qty, average, bal_value))
            else:
                unit = average
                new_qty = _q(bal_qty + qty, KG)
                new_value = _q(bal_value + _q(qty * unit, PEN), PEN)
                bal_qty, bal_value = new_qty, new_value
                credit_kg += qty
                rows.append(self._entry(move, qty, unit, bal_qty, average, bal_value))
            if min_qty is None or bal_qty < min_qty:
                min_qty = bal_qty
                min_day = move['day']
        return rows, {
            'min_qty': min_qty,
            'min_day': min_day,
            'final_qty': bal_qty,
            'final_avg': average,
            'short': short,
            'sale_kg': sale_kg,
            'credit_kg': credit_kg,
            'purchase_kg': purchase_kg,
        }

    def _entry(self, move, qty, unit, bal_qty, average, bal_value):
        if move['kind'] == 'opening':
            return self._row(
                _aware(OPENING_DATE), 'Adjustment', OPENING_REFERENCE, 20230101,
                qty, 0, unit, bal_qty, average, bal_value,
                'Saldo inicial enero 2023', '16', '16', '', '', '',
                'SALDO INICIAL 01/01/2023',
            )
        if move['kind'] == 'purchase':
            return self._row(
                move['when'], 'Purchase', 'PurchaseReceipt', move['id'],
                qty, 0, unit, bal_qty, average, bal_value,
                move['remarks'], '01', '02', move['serial'], move['number'], move['ruc'],
                move['description'],
            )
        end = move['numero_fin']
        label = f'{move["serie"]}-{move["numero"]}'
        return self._row(
            _aware(move['day']), 'Return', 'NubefactCreditNote', 0,
            qty, 0, unit, bal_qty, average, bal_value,
            f'[nc:{move["doc_type"]}-{label}]',
            '07', '05', move['serie'], str(move['numero']), '',
            f'DEVOLUCION {label}'[:200],
        )

    def _exit(self, move, qty, unit, bal_qty, average, bal_value):
        end = move['numero_fin']
        if move['doc_type'] == '03' and end:
            description = f'VENTA BOLETAS ({move["serie"]}-{move["numero"]} al {move["serie"]}-{end})'
            remarks = f'[boleta:{move["serie"]}:{move["day"]}:{move["numero"]}-{end}]'
            number_end = str(end)
        else:
            description = f'VENTA {move["serie"]}-{move["numero"]}'
            remarks = f'[venta:{move["doc_type"]}-{move["serie"]}-{move["numero"]}]'
            number_end = ''
        return self._row(
            _aware(move['day']), 'Sale', 'NubefactSale', 0,
            0, qty, unit, bal_qty, average, bal_value,
            remarks, move['doc_type'], '01', move['serie'], str(move['numero']),
            move['ruc'], description[:200], number_end,
        )

    def _row(self, when, movement_type, reference_type, reference_id,
             qty_in, qty_out, unit, bal_qty, average, bal_value,
             remarks, doc_type, operation, serial, number, ruc, description, number_end=''):
        return {
            'when': when,
            'movement_type': movement_type,
            'reference_type': reference_type,
            'reference_id': reference_id,
            'qty_in': qty_in,
            'qty_out': qty_out,
            'unit': unit,
            'bal_qty': bal_qty,
            'average': average,
            'bal_value': bal_value,
            'remarks': remarks or '',
            'doc_type': doc_type,
            'operation': operation,
            'serial': (serial or '')[:10],
            'number': (number or '')[:20],
            'number_end': (number_end or '')[:20],
            'ruc': (ruc or '')[:11],
            'description': (description or '')[:200],
        }

    def _replace(self, product, warehouse, rows):
        ledger_ids = InventoryLedger.objects.filter(product=product, warehouse=warehouse).values('id')
        GlpKardexDocument.objects.filter(inventory_ledger_id__in=ledger_ids).delete()
        InventoryLedger.objects.filter(product=product, warehouse=warehouse).delete()
        ledgers = [
            InventoryLedger(
                product=product,
                warehouse=warehouse,
                movement_date=row['when'],
                movement_type=row['movement_type'],
                reference_type=row['reference_type'],
                reference_id=row['reference_id'],
                quantity_in=row['qty_in'],
                quantity_out=row['qty_out'],
                balance_quantity=row['bal_qty'],
                unit_cost=row['unit'],
                average_cost=row['average'],
                balance_value=row['bal_value'],
                remarks=row['remarks'],
            )
            for row in rows
        ]
        ledgers = InventoryLedger.objects.bulk_create(ledgers, batch_size=1000)
        if not ledgers or ledgers[0].pk is None:
            raise CommandError('La base no devolvió los id del kardex.')
        GlpKardexDocument.objects.bulk_create([
            GlpKardexDocument(
                inventory_ledger=ledger,
                document_type=row['doc_type'],
                operation_sunat=row['operation'],
                serial=row['serial'],
                document_number=row['number'],
                document_number_end=row['number_end'],
                partner_ruc=row['ruc'],
                description=row['description'],
            )
            for ledger, row in zip(ledgers, rows)
        ], batch_size=1000)
        PurchaseReceipt.objects.filter(
            warehouse=warehouse,
            status='Received',
            purchase__remarks__contains='[req:',
        ).update(ledger_posted=True)
