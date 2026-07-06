from django.contrib import admin
from apps.inventory import models

admin.site.register(models.Purchase)
admin.site.register(models.PurchaseItem)
admin.site.register(models.PurchaseReceipt)
admin.site.register(models.PurchaseParticipant)
admin.site.register(models.InventoryLedger)
admin.site.register(models.GlpKardexDocument)
