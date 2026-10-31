from django.db import models
from django.contrib.auth.models import User
from django.core.exceptions import ObjectDoesNotExist
import decimal


class Purchase(models.Model):
    INVOICE_TYPE_CHOICES = (
        ('Invoice', 'Factura'),
        ('Credit Note', 'Nota de crédito'),
    )
    CURRENCY_CHOICES = (
        ('PEN', 'Soles'),
        ('USD', 'Dólares'),
    )
    PAYMENT_TERMS_CHOICES = (
        ('Cash', 'Contado'),
        ('Credit', 'Crédito'),
    )
    STATUS_CHOICES = (
        ('Draft', 'Borrador'),
        ('InvoiceRegistered', 'Factura registrada'),
        ('DetailRegistered', 'Detalle registrado'),
        ('ParticipantsRegistered', 'Participantes registrados'),
        ('InTransit', 'En traslado'),
        ('Completed', 'Completado'),
        ('Cancelled', 'Anulado'),
    )

    supplier = models.ForeignKey(
        'sales.Supplier', on_delete=models.PROTECT, related_name='inventory_purchases')
    invoice_type = models.CharField(max_length=20, choices=INVOICE_TYPE_CHOICES, default='Invoice')
    series = models.CharField(max_length=10)
    number = models.CharField(max_length=20)
    issue_date = models.DateField()
    due_date = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=5, choices=CURRENCY_CHOICES, default='PEN')
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=1)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    igv = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    isc = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    fise = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    other_charges = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    sales_order = models.CharField(max_length=30, null=True, blank=True)
    terminal = models.CharField(max_length=100, null=True, blank=True)
    scop_number = models.CharField(max_length=45, null=True, blank=True, verbose_name='N° SCOP factura')
    uses_participants = models.BooleanField(default=False)
    payment_terms = models.CharField(max_length=50, choices=PAYMENT_TERMS_CHOICES, default='Cash')
    status = models.CharField(max_length=25, choices=STATUS_CHOICES, default='Draft')
    remarks = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_purchases_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Compra inventario'
        verbose_name_plural = 'Compras inventario'
        ordering = ['-issue_date', '-id']

    def __str__(self):
        return f'{self.series}-{self.number}'

    @property
    def document_display(self):
        return f'{self.series}-{self.number}'

    @property
    def participants_total(self):
        return sum(p.total for p in self.participants.all())

    @property
    def participants_qty_total(self):
        return sum(p.quantity for p in self.participants.all())

    @property
    def participants_subtotal(self):
        return sum(p.subtotal for p in self.participants.all())

    @property
    def participants_isc(self):
        return sum(p.isc for p in self.participants.all())

    @property
    def participants_igv(self):
        return sum(p.igv for p in self.participants.all())

    @property
    def participants_fise(self):
        return sum(p.fise for p in self.participants.all())

    @property
    def participants_subtotal_with_isc(self):
        return self.participants_subtotal + self.participants_isc

    @property
    def invoiced_qty_total(self):
        return sum(i.quantity for i in self.items.all())

    @property
    def received_qty_total(self):
        return sum(
            r.net_weight for r in self.receipts.filter(status='Received')
        )

    @property
    def qty_pending_programming(self):
        return sum(
            line.quantity_kg for line in self.programming_lines.filter(
                programming__status='Pending',
            )
        )

    @property
    def qty_available_for_programming(self):
        available = self.invoiced_qty_total - self.received_qty_total - self.qty_pending_programming
        return max(available, decimal.Decimal(0))

    @property
    def purchase_value_pen(self):
        """Valor de compra sin IGV en soles = subtotal factura × tipo de cambio."""
        rate = self.exchange_rate if self.currency == 'USD' else decimal.Decimal('1')
        return (self.subtotal or decimal.Decimal(0)) * (rate or decimal.Decimal('1'))

    @property
    def travel_expenses_pen(self):
        """Total de gastos de traslado prorrateados a las recepciones de esta compra."""
        return sum(
            (r.total_additional_cost or decimal.Decimal(0))
            for r in self.receipts.all()
        )

    @property
    def landed_total_pen(self):
        """Costo total del lote en soles = valor de compra + gastos de traslado."""
        return self.purchase_value_pen + self.travel_expenses_pen

    @property
    def landed_cost_per_kg(self):
        """Costo unitario final (S/ por kg) según promedio ponderado del lote."""
        qty = self.invoiced_qty_total
        if not qty:
            return decimal.Decimal(0)
        return self.landed_total_pen / qty

    def get_status_display_class(self):
        return {
            'Draft': 'secondary',
            'InvoiceRegistered': 'info',
            'DetailRegistered': 'primary',
            'ParticipantsRegistered': 'primary',
            'InTransit': 'warning',
            'Completed': 'success',
            'Cancelled': 'danger',
        }.get(self.status, 'secondary')


class PurchaseItem(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('sales.Product', on_delete=models.PROTECT)
    description = models.CharField(max_length=200, null=True, blank=True)
    unit = models.CharField(max_length=20, default='KG')
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    unit_price_incl_igv = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    igv = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    isc = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    fise = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Ítem de compra'
        verbose_name_plural = 'Ítems de compra'

    def __str__(self):
        return f'{self.product} x {self.quantity}'


class PurchaseReceipt(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Pendiente'),
        ('Received', 'Recibido'),
        ('Cancelled', 'Anulado'),
    )

    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='receipts')
    programming = models.ForeignKey(
        'PurchaseProgramming', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='receipts')
    truck = models.ForeignKey(
        'comercial.Truck', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_purchase_receipts')
    warehouse = models.ForeignKey(
        'sales.SubsidiaryStore', on_delete=models.PROTECT, related_name='purchase_receipts')
    receipt_date = models.DateTimeField()
    guide_series = models.CharField(max_length=10, null=True, blank=True)
    guide_number = models.CharField(max_length=20, null=True, blank=True)
    weighing_ticket = models.CharField(max_length=30, null=True, blank=True)
    scop_number = models.CharField(max_length=30, null=True, blank=True)
    vehicle_plate = models.CharField(max_length=20, null=True, blank=True)
    trailer_plate = models.CharField(max_length=20, null=True, blank=True)
    driver_name = models.CharField(max_length=150, null=True, blank=True)
    driver_license = models.CharField(max_length=30, null=True, blank=True)
    hydrocarbon_registry = models.CharField(max_length=50, null=True, blank=True)
    gross_weight = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    tare_weight = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    net_weight = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    volume_gallons = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    density = models.DecimalField(max_digits=10, decimal_places=5, default=0)
    temperature = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    odorant_ml = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    loading_terminal = models.CharField(max_length=100, null=True, blank=True)
    destination = models.CharField(max_length=100, null=True, blank=True)
    freight_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    insurance_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    unloading_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    other_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total_additional_cost = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    received_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_receipts_received')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    ledger_posted = models.BooleanField(default=False)
    remarks = models.TextField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Traslado / recepción GLP'
        verbose_name_plural = 'Traslados / recepciones GLP'

    def __str__(self):
        return f'Recepción #{self.id} — {self.purchase}'

    def compute_additional_costs(self):
        self.total_additional_cost = (
            self.freight_cost + self.insurance_cost + self.unloading_cost + self.other_cost
        )
        return self.total_additional_cost


class PurchaseParticipant(models.Model):
    purchase = models.ForeignKey(Purchase, on_delete=models.CASCADE, related_name='participants')
    company_name = models.CharField(max_length=200)
    tax_id = models.CharField(max_length=20, null=True, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    subtotal = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    isc = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    igv = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    fise = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    total = models.DecimalField(max_digits=18, decimal_places=4, default=0)

    class Meta:
        verbose_name = 'Participante de compra'
        verbose_name_plural = 'Participantes de compra'

    @property
    def subtotal_with_isc(self):
        return self.subtotal + self.isc


class PurchaseProgramming(models.Model):
    STATUS_CHOICES = (
        ('Pending', 'Programado'),
        ('Finished', 'Finalizado'),
    )

    truck = models.ForeignKey(
        'comercial.Truck', on_delete=models.PROTECT, related_name='glp_purchase_programmings')
    transfer_scop_number = models.CharField(
        max_length=45, unique=True, verbose_name='N° SCOP traslado')
    programming_date = models.DateField()
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Pending')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Programación traslado GLP'
        verbose_name_plural = 'Programaciones traslado GLP'

    def __str__(self):
        return f'{self.truck} — SCOP {self.transfer_scop_number}'

    @property
    def travel_expenses_total(self):
        return sum(e.amount for e in self.travel_expenses.all())

    @property
    def total_quantity_kg(self):
        return sum(line.quantity_kg for line in self.lines.all())

    def purchase_documents_display(self):
        return ', '.join(
            f'{line.purchase.document_display} ({line.quantity_kg} KG)'
            for line in self.lines.select_related('purchase').all()[:5]
        )


class PurchaseProgrammingLine(models.Model):
    """Cantidad parcial (KG) de una factura asignada a un tracto + SCOP."""
    programming = models.ForeignKey(
        PurchaseProgramming, on_delete=models.CASCADE, related_name='lines')
    purchase = models.ForeignKey(
        Purchase, on_delete=models.CASCADE, related_name='programming_lines')
    quantity_kg = models.DecimalField(max_digits=18, decimal_places=3, default=0)

    class Meta:
        verbose_name = 'Línea de programación GLP'
        verbose_name_plural = 'Líneas de programación GLP'
        unique_together = ('programming', 'purchase')

    def __str__(self):
        return f'{self.purchase} → {self.quantity_kg} KG'


class PurchaseTravelExpense(models.Model):
    TYPE_CHOICES = (
        ('C', 'Combustible'),
        ('F', 'Flete'),
        ('P', 'Peaje'),
        ('S', 'Sueldo'),
        ('V', 'Viático'),
        ('L', 'Lavado'),
        ('O', 'Otros'),
    )
    STATUS_CHOICES = (
        ('Pending', 'Pendiente'),
        ('Registered', 'Registrado'),
    )

    programming = models.ForeignKey(
        PurchaseProgramming, on_delete=models.CASCADE, related_name='travel_expenses')
    expense_type = models.CharField(max_length=2, choices=TYPE_CHOICES, default='F')
    invoice_number = models.CharField(max_length=45, null=True, blank=True)
    expense_date = models.DateField(null=True, blank=True)
    quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    amount = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    description = models.CharField(max_length=200, null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='Registered')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Gasto de viaje GLP'
        verbose_name_plural = 'Gastos de viaje GLP'


class InventoryLedger(models.Model):
    MOVEMENT_TYPE_CHOICES = (
        ('Purchase', 'Compra'),
        ('Sale', 'Venta'),
        ('Return', 'Devolución'),
        ('Transfer', 'Traspaso'),
        ('Adjustment', 'Ajuste'),
    )

    product = models.ForeignKey('sales.Product', on_delete=models.PROTECT, related_name='inventory_ledger')
    warehouse = models.ForeignKey(
        'sales.SubsidiaryStore', on_delete=models.PROTECT, related_name='inventory_ledger')
    movement_date = models.DateTimeField()
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPE_CHOICES)
    reference_type = models.CharField(max_length=30)
    reference_id = models.BigIntegerField()
    quantity_in = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    quantity_out = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    balance_quantity = models.DecimalField(max_digits=18, decimal_places=3, default=0)
    unit_cost = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    average_cost = models.DecimalField(max_digits=18, decimal_places=6, default=0)
    balance_value = models.DecimalField(max_digits=18, decimal_places=4, default=0)
    remarks = models.TextField(null=True, blank=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='inventory_ledger_created')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Kardex inventario'
        verbose_name_plural = 'Kardex inventario'
        ordering = ['movement_date', 'id']

    def __str__(self):
        return f'{self.movement_type} #{self.id} — {self.product}'

    @property
    def is_entry(self):
        return self.quantity_in > 0

    @property
    def is_exit(self):
        return self.quantity_out > 0

    @property
    def movement_total(self):
        qty = self.quantity_in if self.is_entry else self.quantity_out
        return qty * self.unit_cost

    @property
    def operation_code(self):
        if self.movement_type == 'Adjustment' and self.is_entry:
            return 'C'
        return 'E' if self.is_entry else 'S'

    def get_glp_document(self):
        try:
            return self.glp_document
        except ObjectDoesNotExist:
            return None


class GlpKardexDocument(models.Model):
    DOCUMENT_TYPE_CHOICES = (
        ('00', 'Sin documento'),
        ('01', 'Factura'),
        ('03', 'Boleta'),
        ('07', 'Nota de crédito'),
        ('16', 'Saldo inicial'),
    )
    OPERATION_SUNAT_CHOICES = (
        ('01', 'Venta / Salida'),
        ('02', 'Compra / Entrada'),
        ('05', 'Devolución recibida'),
        ('16', 'Saldo inicial'),
    )

    kardex = models.OneToOneField(
        'sales.Kardex', on_delete=models.CASCADE, null=True, blank=True, related_name='glp_document')
    inventory_ledger = models.OneToOneField(
        InventoryLedger, on_delete=models.CASCADE, null=True, blank=True, related_name='glp_document')
    document_type = models.CharField(max_length=2, choices=DOCUMENT_TYPE_CHOICES, default='00')
    operation_sunat = models.CharField(max_length=2, choices=OPERATION_SUNAT_CHOICES, default='02')
    serial = models.CharField(max_length=10, null=True, blank=True)
    document_number = models.CharField(max_length=20, null=True, blank=True)
    document_number_end = models.CharField(max_length=20, null=True, blank=True)
    partner_ruc = models.CharField(max_length=11, null=True, blank=True)
    description = models.CharField(max_length=200, null=True, blank=True)
    user = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='glp_kardex_documents')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Documento kardex GLP'
        verbose_name_plural = 'Documentos kardex GLP'
