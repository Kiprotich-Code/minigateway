def on_payment_completed(sender, transaction, **kwargs):
    """Find the ParkingSession linked to this transaction and mark it paid."""
    from parking.models import ParkingSession
    try:
        session = ParkingSession.objects.get(transaction=transaction)
        session.status = "paid"
        session.save()
    except ParkingSession.DoesNotExist:
        pass  # No session linked — ignore
