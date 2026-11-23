from django.contrib import admin

from .models import Payment, Receipt, Sale, SaleItem


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ("line_total",)


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("id", "type", "status", "client", "agent", "total", "amount_paid", "remaining", "payment_status")
    list_filter = ("type", "status")
    readonly_fields = ("remaining", "payment_status")
    inlines = [SaleItemInline]


admin.site.register([Payment, Receipt])
