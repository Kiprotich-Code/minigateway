import json

from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt

from .adapters.daraja import DarajaAdapter
from .models import Transaction
from .signals import payment_completed, payment_failed


@csrf_exempt
def daraja_callback(request):
    """
    Receive Safaricom's asynchronous STK Push callback, update the matching
    Transaction, and fire the appropriate Django signal.

    POST /payments/callbacks/daraja/
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    try:
        checkout_request_id = data["Body"]["stkCallback"]["CheckoutRequestID"]
    except (KeyError, TypeError):
        return JsonResponse({"error": "Malformed payload"}, status=400)

    try:
        transaction = Transaction.objects.get(provider_reference=checkout_request_id)
    except Transaction.DoesNotExist:
        return JsonResponse({"error": "Transaction not found"}, status=404)

    adapter = DarajaAdapter(transaction.channel)
    result = adapter.parse_callback(data)

    transaction.status = result.status
    transaction.provider_transaction = result.provider_transaction
    transaction.save()

    if result.status == "completed":
        payment_completed.send(sender=Transaction, transaction=transaction)
    elif result.status == "failed":
        payment_failed.send(sender=Transaction, transaction=transaction)

    return JsonResponse({"status": "ok"})
