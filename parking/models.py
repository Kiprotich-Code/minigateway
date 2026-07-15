from django.db import models


class ParkingSlot(models.Model):
    slot_number = models.CharField(max_length=20, unique=True)
    location = models.CharField(max_length=100)

    def __str__(self):
        return f"Slot {self.slot_number} — {self.location}"

    class Meta:
        verbose_name = "Parking Slot"
        verbose_name_plural = "Parking Slots"


class ParkingSession(models.Model):
    STATUS_CHOICES = [
        ("active", "Active"),
        ("paid", "Paid"),
        ("cancelled", "Cancelled"),
    ]

    slot = models.ForeignKey(
        ParkingSlot,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
    )
    plate_number = models.CharField(max_length=20)
    phone = models.CharField(max_length=20)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="active")
    transaction = models.ForeignKey(
        "payments.Transaction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    def __str__(self):
        return f"{self.plate_number} — {self.status}"

    class Meta:
        verbose_name = "Parking Session"
        verbose_name_plural = "Parking Sessions"
