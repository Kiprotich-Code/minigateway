from django.dispatch import Signal

payment_completed = Signal()  # kwargs: transaction
payment_failed = Signal()     # kwargs: transaction
