import uuid

from django.db import models


class PaymentChannel(models.Model):
    PROVIDER_CHOICES = [
        ("mpesa", "M-Pesa"),
        ("stripe", "Stripe"),
        ("bank", "Bank"),
    ]
    ENV_CHOICES = [
        ("sandbox", "Sandbox"),
        ("production", "Production"),
    ]

    name = models.CharField(max_length=100)
    provider_type = models.CharField(max_length=20, choices=PROVIDER_CHOICES)
    environment = models.CharField(max_length=20, choices=ENV_CHOICES, default="sandbox")
    enabled = models.BooleanField(default=True)

    # M-Pesa identifiers
    shortcode = models.CharField(max_length=20, blank=True)
    till_number = models.CharField(max_length=20, blank=True)
    paybill_number = models.CharField(max_length=20, blank=True)
    account_reference_format = models.CharField(max_length=100, blank=True)

    # Callback URLs
    callback_url = models.URLField(blank=True)
    validation_url = models.URLField(blank=True)
    confirmation_url = models.URLField(blank=True)

    # Credentials
    consumer_key = models.CharField(max_length=200, blank=True)
    consumer_secret = models.CharField(max_length=200, blank=True)
    passkey = models.CharField(max_length=200, blank=True)

    # Behaviour
    transaction_timeout = models.IntegerField(default=30)
    stk_push_enabled = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"{self.name} ({self.get_provider_type_display()} / {self.get_environment_display()})"

    class Meta:
        verbose_name = "Payment Channel"
        verbose_name_plural = "Payment Channels"


class Transaction(models.Model):
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("completed", "Completed"),
        ("failed", "Failed"),
        ("cancelled", "Cancelled"),
    ]

    id = models.AutoField(primary_key=True)
    reference = models.UUIDField(default=uuid.uuid4, unique=True)
    channel = models.ForeignKey(PaymentChannel, on_delete=models.PROTECT)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=3, default="KES")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="pending")
    provider_reference = models.CharField(max_length=200, blank=True)
    provider_transaction = models.JSONField(default=dict, blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Transaction {self.reference} ({self.status})"

    class Meta:
        verbose_name = "Transaction"
        verbose_name_plural = "Transactions"
        ordering = ["-created_at"]
