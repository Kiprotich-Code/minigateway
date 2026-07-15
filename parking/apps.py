from django.apps import AppConfig


class ParkingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'parking'

    def ready(self):
        from payments.signals import payment_completed
        from parking.listeners import on_payment_completed
        payment_completed.connect(on_payment_completed)
