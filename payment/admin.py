from django.contrib import admin

from .models import PaymentEvent


@admin.register(PaymentEvent)
class PaymentEventAdmin(admin.ModelAdmin):
    list_display = (
        "provider_event_id",
        "order",
        "payment_id",
        "status",
        "amount",
        "signature_valid",
        "received_at",
    )
    list_filter = ("status", "signature_valid", "received_at")
    search_fields = ("provider_event_id", "payment_id", "order__order_number")
    readonly_fields = (
        "order",
        "provider_event_id",
        "payment_id",
        "status",
        "amount",
        "payload",
        "signature_valid",
        "processed_at",
        "received_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
