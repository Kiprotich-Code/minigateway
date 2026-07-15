from django.contrib import admin

from .models import PaymentChannel, Transaction


@admin.register(PaymentChannel)
class PaymentChannelAdmin(admin.ModelAdmin):
    list_display = ("name", "provider_type", "environment", "enabled", "stk_push_enabled")
    list_filter = ("provider_type", "environment", "enabled")
    search_fields = ("name", "shortcode", "paybill_number", "till_number")
    fieldsets = (
        ("General", {
            "fields": ("name", "provider_type", "environment", "enabled"),
        }),
        ("M-Pesa Identifiers", {
            "fields": ("shortcode", "till_number", "paybill_number", "account_reference_format"),
        }),
        ("Callback URLs", {
            "fields": ("callback_url", "validation_url", "confirmation_url"),
        }),
        ("Credentials", {
            "fields": ("consumer_key", "consumer_secret", "passkey"),
            "classes": ("collapse",),
            "description": "Keep these values secret. Never share them publicly.",
        }),
        ("Behaviour", {
            "fields": ("transaction_timeout", "stk_push_enabled", "settings"),
        }),
    )


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("reference", "channel", "amount", "currency", "status", "created_at")
    list_filter = ("status", "currency", "channel")
    search_fields = ("reference", "provider_reference")
    readonly_fields = ("reference", "created_at", "provider_transaction")
