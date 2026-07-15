from django.shortcuts import render
from payments.models import PaymentChannel, Transaction
from parking.models import ParkingSession


def dashboard(request):
    context = {
        "channel_count": PaymentChannel.objects.count(),
        "active_channel_count": PaymentChannel.objects.filter(enabled=True).count(),
        "transaction_count": Transaction.objects.count(),
        "pending_count": Transaction.objects.filter(status="pending").count(),
        "completed_count": Transaction.objects.filter(status="completed").count(),
        "session_count": ParkingSession.objects.count(),
        "active_session_count": ParkingSession.objects.filter(status="active").count(),
        "recent_transactions": Transaction.objects.select_related("channel").order_by("-created_at")[:5],
        "recent_sessions": ParkingSession.objects.select_related("transaction").order_by("-id")[:5],
    }
    return render(request, "dashboard.html", context)
