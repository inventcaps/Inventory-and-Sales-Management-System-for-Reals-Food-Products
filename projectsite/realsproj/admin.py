from django.contrib import admin
from .models import Expenses, HistoryLog, HistoryLogTypes, ProductBatches, ProductInventory, ProductTypes, ProductVariants, Products, RawMaterialBatches, RawMaterialInventory, RawMaterials, Sales, SizeUnits, Sizes, SrpPrices, UnitPrices, StockChanges, Notifications, Withdrawals, SalesSummary, ExpensesSummary
# Register your models here.

admin.site.register(Expenses)
admin.site.register(HistoryLog)
admin.site.register(HistoryLogTypes)
admin.site.register(ProductBatches)
admin.site.register(ProductInventory)
admin.site.register(ProductTypes)
admin.site.register(ProductVariants)
admin.site.register(RawMaterialBatches)
admin.site.register(RawMaterialInventory)
admin.site.register(RawMaterials)
admin.site.register(Sales)
admin.site.register(SizeUnits)
admin.site.register(Sizes)
admin.site.register(SrpPrices)
admin.site.register(UnitPrices)
admin.site.register(StockChanges)
admin.site.register(Notifications)
admin.site.register(Withdrawals)
admin.site.register(SalesSummary)
admin.site.register(ExpensesSummary)

@admin.register(Products)
class ProductsAdmin(admin.ModelAdmin):
    pass