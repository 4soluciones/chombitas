"""
Migra compras GLP históricas al inventario y al kardex valorizado, en soles.

La fecha del movimiento de kardex es buys_programminginvoice.date_arrive.
La fecha de la factura es buys_requirement_buys.approval_date.

El precio en dólares queda como referencia (tipo de cambio, USD/kg e importe USD).
El costo que entra al kardex es el precio en soles por kg del detalle
(amount_pen / quantity).

No migra las 11 compras sin guía. El 96 y el 205 entran con la factura ya
corregida. El 225 queda corregido en el requerimiento y fuera del kardex
porque no tiene guía. No duplica un requerimiento marcado [req:ID].

Uso:
    python manage.py migrate_glp_purchases
    python manage.py migrate_glp_purchases --apply
"""
import datetime
import decimal
from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.buys.models import (
    Programminginvoice,
    Requirement_buys,
    RequirementBuysProgramming,
    RequirementDetail_buys,
)
from apps.inventory.models import (
    GlpKardexDocument,
    InventoryLedger,
    Purchase,
    PurchaseItem,
    PurchaseProgramming,
    PurchaseProgrammingLine,
    PurchaseReceipt,
)
from apps.inventory.services import GLP_PRODUCT_ID
from apps.sales.models import Product, SubsidiaryStore

SUPPLIER_ID = 1
WAREHOUSE_ID = 14  # PLUSPETROL, único almacén categoría G que lee el kardex valorizado
OPENING_QTY_KG = decimal.Decimal('584940')
OPENING_DATE = datetime.date(2023, 1, 1)
OPENING_REFERENCE = 'OpeningBalance'

# Compras con precio y sin guía. No hay fecha ni kilos de ingreso.
EXCLUDED_REQUIREMENT_IDS = {
    208, 223, 224, 225, 226, 227, 228, 229, 230, 231, 232,
}

PEN = decimal.Decimal('0.0001')
KG = decimal.Decimal('0.001')
UNIT = decimal.Decimal('0.000001')


def _q(value, places):
    return decimal.Decimal(value or 0).quantize(places)


def _mark(requirement_id):
    return f'[req:{requirement_id}]'


def _aware(day):
    naive = datetime.datetime.combine(day, datetime.time.min)
    return timezone.make_aware(naive, timezone.get_current_timezone())


def _split_invoice(invoice):
    text = (invoice or '').strip().upper()
    if '-' not in text:
        return text[:10], ''
    series, number = text.split('-', 1)
    return series[:10], number[:20]


def _transfer_scop(programming):
    scop = (programming.number_scop or '').strip()
    duplicated = RequirementBuysProgramming.objects.filter(number_scop=scop).exclude(
        pk=programming.pk,
    ).exists()
    if duplicated:
        return f'{scop}-P{programming.pk}'[:45]
    return scop[:45]


class Command(BaseCommand):
    help = 'Migra compras GLP con guía al inventario y al kardex valorizado en soles.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--apply',
            action='store_true',
            help='Escribe en la base. Sin esta bandera solo muestra el conteo.',
        )

    def handle(self, *args, **options):
        product = Product.objects.get(pk=GLP_PRODUCT_ID)
        warehouse = SubsidiaryStore.objects.get(pk=WAREHOUSE_ID)
        requirements = self._requirements()
        guides = list(self._guides(requirements))
        opening_unit = self._opening_unit_cost(guides)

        self.stdout.write(f'Almacén kardex: {warehouse.id} {warehouse.name} ({warehouse.category})')
        self.stdout.write(f'Facturas a migrar: {len(requirements)}')
        self.stdout.write(f'Guías con kilos: {len(guides)}')
        self.stdout.write(
            f'Saldo inicial: {OPENING_QTY_KG} kg el {OPENING_DATE} '
            f'a S/ {opening_unit} por kg (costo del primer ingreso)'
        )
        self.stdout.write('Excluidos: ' + ', '.join(str(i) for i in sorted(EXCLUDED_REQUIREMENT_IDS)))
        if guides:
            self.stdout.write(
                f'Llegadas: {guides[0].date_arrive} a {guides[-1].date_arrive}'
            )
        for guide in guides[:3]:
            detail = guide.requirement_buys.requirements_buys.first()
            unit_pen = _q(detail.amount_pen / detail.quantity, UNIT)
            self.stdout.write(
                f'  guía {guide.id} llega {guide.date_arrive} '
                f'{guide.quantity} kg a S/ {unit_pen} '
                f'(ref USD {detail.price} x TC {detail.change_coin}) '
                f'req {guide.requirement_buys_id}'
            )

        if not options['apply']:
            self.stdout.write(self.style.WARNING('Sin --apply no se escribió nada.'))
            return

        if InventoryLedger.objects.filter(
            product=product, warehouse=warehouse, movement_type='Sale',
        ).exists():
            self.stderr.write('Hay ventas en el kardex. No se rehace el promedio encima de ellas.')
            return

        with transaction.atomic():
            self.bal_qty = decimal.Decimal(0)
            self.bal_value = decimal.Decimal(0)
            self._clear_purchase_ledger(product, warehouse)
            for requirement in requirements:
                self._migrate_requirement(requirement, product, warehouse)
            self._post_opening(product, warehouse, opening_unit)
            posted = self._post_guides(product, warehouse)
        self.stdout.write(self.style.SUCCESS(f'Kardex de compras asentado: {posted} guías.'))

    def _opening_unit_cost(self, guides):
        """Soles por kg del primer ingreso, el de fecha de llegada más antigua."""
        if not guides:
            return decimal.Decimal(0)
        detail = RequirementDetail_buys.objects.get(requirement_buys_id=guides[0].requirement_buys_id)
        return _q(detail.amount_pen / detail.quantity, UNIT)

    def _requirements(self):
        """
        Requerimiento aprobado, con precio, con al menos una guía de kilos,
        y fuera de la lista excluida.
        """
        received = Programminginvoice.objects.filter(quantity__gt=0).values('requirement_buys_id')
        return list(
            Requirement_buys.objects.filter(
                status='2',
                id__in=received,
            ).exclude(
                id__in=EXCLUDED_REQUIREMENT_IDS,
            ).filter(
                requirements_buys__price__gt=0,
            ).distinct().select_related('user').order_by('approval_date', 'id')
        )

    def _guides(self, requirements):
        ids = [item.id for item in requirements]
        return Programminginvoice.objects.filter(
            requirement_buys_id__in=ids,
            quantity__gt=0,
        ).select_related(
            'requirement_buys', 'requirementBuysProgramming',
        ).order_by('date_arrive', 'id')

    def _clear_purchase_ledger(self, product, warehouse):
        """Borra entradas de compras y saldo inicial para rearmar el promedio en orden de fecha."""
        ledgers = InventoryLedger.objects.filter(
            product=product,
            warehouse=warehouse,
            reference_type__in=[OPENING_REFERENCE, 'PurchaseReceipt'],
        )
        GlpKardexDocument.objects.filter(inventory_ledger__in=ledgers).delete()
        ledgers.delete()
        PurchaseReceipt.objects.filter(
            warehouse=warehouse,
            purchase__remarks__contains='[req:',
        ).update(ledger_posted=False)

    def _migrate_requirement(self, requirement, product, warehouse):
        if Purchase.objects.filter(remarks__contains=_mark(requirement.id)).exists():
            return
        detail = RequirementDetail_buys.objects.get(requirement_buys=requirement)
        qty = _q(detail.quantity, KG)
        amount_pen = _q(detail.amount_pen, PEN)
        unit_pen = _q(amount_pen / qty, UNIT)
        series, number = _split_invoice(requirement.invoice)
        purchase = Purchase.objects.create(
            supplier_id=SUPPLIER_ID,
            invoice_type='Invoice',
            series=series,
            number=number,
            issue_date=requirement.approval_date or requirement.creation_date,
            currency='PEN',
            exchange_rate=_q(detail.change_coin, UNIT),
            subtotal=amount_pen,
            igv=0,
            isc=0,
            fise=0,
            other_charges=0,
            total=amount_pen,
            scop_number=(requirement.number_scop or '')[:45],
            terminal='PLUSPETROL',
            uses_participants=False,
            payment_terms='Credit',
            status='InTransit',
            remarks=(
                f'{_mark(requirement.id)} '
                f'Ref. USD/kg {detail.price} | USD {detail.amount} | TC {detail.change_coin}'
            ),
            created_by=requirement.user,
        )
        PurchaseItem.objects.create(
            purchase=purchase,
            product=product,
            description='GLP',
            unit='KG',
            quantity=qty,
            unit_price=unit_pen,
            unit_price_incl_igv=unit_pen,
            subtotal=amount_pen,
            igv=0,
            isc=0,
            fise=0,
            total=amount_pen,
        )
        self._migrate_guides(requirement, purchase, detail, warehouse)

    def _migrate_guides(self, requirement, purchase, detail, warehouse):
        guides = Programminginvoice.objects.filter(
            requirement_buys=requirement,
            quantity__gt=0,
        ).select_related('requirementBuysProgramming__truck')
        kg_by_programming = defaultdict(lambda: decimal.Decimal(0))
        for guide in guides:
            programming = self._programming(guide.requirementBuysProgramming)
            kg_by_programming[programming.id] += _q(guide.quantity, KG)
            plate = ''
            if guide.requirementBuysProgramming.truck_id:
                plate = guide.requirementBuysProgramming.truck.license_plate
            destiny = guide.subsidiary_store_destiny.name if guide.subsidiary_store_destiny_id else ''
            PurchaseReceipt.objects.create(
                purchase=purchase,
                programming=programming,
                truck=guide.requirementBuysProgramming.truck,
                warehouse=warehouse,
                receipt_date=_aware(guide.date_arrive),
                guide_number=(guide.guide or '')[:20],
                scop_number=(guide.requirementBuysProgramming.number_scop or '')[:30],
                vehicle_plate=plate[:20],
                net_weight=_q(guide.quantity, KG),
                loading_terminal='PLUSPETROL',
                destination=destiny[:100],
                status='Received',
                ledger_posted=False,
                remarks=f'Guía histórica {guide.id}. Llegada {guide.date_arrive}.',
            )
        for programming_id, kg in kg_by_programming.items():
            PurchaseProgrammingLine.objects.get_or_create(
                programming_id=programming_id,
                purchase=purchase,
                defaults={'quantity_kg': _q(kg, KG)},
            )
        received = purchase.receipts.filter(status='Received').aggregate(total=Sum('net_weight'))['total'] or 0
        ordered = purchase.items.aggregate(total=Sum('quantity'))['total'] or 0
        if ordered and decimal.Decimal(received) + 1 >= decimal.Decimal(ordered):
            purchase.status = 'Completed'
        purchase.save(update_fields=['status'])

    def _programming(self, source):
        scop = _transfer_scop(source)
        programming, _ = PurchaseProgramming.objects.get_or_create(
            transfer_scop_number=scop,
            defaults={
                'truck': source.truck,
                'programming_date': source.date_programming,
                'status': 'Finished',
            },
        )
        return programming

    def _post_opening(self, product, warehouse, unit_cost):
        self._write_ledger(
            product, warehouse, _aware(OPENING_DATE), 'Adjustment',
            OPENING_REFERENCE, 20230101, OPENING_QTY_KG, unit_cost,
            'Saldo inicial enero 2023',
            document_type='16', operation_sunat='16',
            description='SALDO INICIAL 01/01/2023',
        )

    def _post_guides(self, product, warehouse):
        receipts = PurchaseReceipt.objects.filter(
            warehouse=warehouse,
            status='Received',
            ledger_posted=False,
            purchase__remarks__contains='[req:',
        ).select_related('purchase__supplier', 'purchase').prefetch_related(
            'purchase__items',
        ).order_by('receipt_date', 'id')
        posted = 0
        for receipt in receipts:
            item = receipt.purchase.items.first()
            self._write_ledger(
                product, warehouse, receipt.receipt_date, 'Purchase',
                'PurchaseReceipt', receipt.id, receipt.net_weight, item.unit_price,
                receipt.purchase.remarks,
                document_type='01', operation_sunat='02',
                serial=receipt.purchase.series,
                document_number=receipt.purchase.number,
                partner_ruc=receipt.purchase.supplier.ruc or '',
                description=(
                    f'INGRESO GLP {receipt.purchase.document_display}'
                    f' | Guía {receipt.guide_number}'
                    f' | SCOP {receipt.scop_number}'
                )[:200],
            )
            receipt.ledger_posted = True
            receipt.save(update_fields=['ledger_posted'])
            posted += 1
        return posted

    def _write_ledger(self, product, warehouse, movement_date, movement_type,
                      reference_type, reference_id, quantity_in, unit_cost, remarks,
                      document_type, operation_sunat, description,
                      serial='', document_number='', partner_ruc=''):
        """Escribe el kardex en soles sin tocar el stock operativo del almacén."""
        quantity_in = _q(quantity_in, KG)
        unit_cost = _q(unit_cost, UNIT)
        new_qty = _q(self.bal_qty + quantity_in, KG)
        new_value = _q(self.bal_value + (quantity_in * unit_cost), PEN)
        new_avg = _q(new_value / new_qty, UNIT) if new_qty else unit_cost
        ledger = InventoryLedger.objects.create(
            product=product,
            warehouse=warehouse,
            movement_date=movement_date,
            movement_type=movement_type,
            reference_type=reference_type,
            reference_id=reference_id,
            quantity_in=quantity_in,
            quantity_out=0,
            balance_quantity=new_qty,
            unit_cost=unit_cost,
            average_cost=new_avg,
            balance_value=new_value,
            remarks=remarks or '',
        )
        GlpKardexDocument.objects.create(
            inventory_ledger=ledger,
            document_type=document_type,
            operation_sunat=operation_sunat,
            serial=serial or '',
            document_number=document_number or '',
            partner_ruc=partner_ruc or '',
            description=description,
        )
        self.bal_qty = new_qty
        self.bal_value = new_value
