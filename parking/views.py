import uuid

from django.shortcuts import get_object_or_404, redirect, render

from parking.forms import ParkingPayForm
from parking.models import ParkingSession
from payments.gateway import PaymentGateway


def pay_view(request):
    if request.method == "POST":
        form = ParkingPayForm(request.POST)
        if form.is_valid():
            intent = {
                "amount": form.cleaned_data["amount"],
                "phone": form.cleaned_data["phone"],
                "channel_id": form.cleaned_data["channel"].id,
                "reference": uuid.uuid4(),
                "metadata": {"plate_number": form.cleaned_data["plate_number"]},
            }
            tx = PaymentGateway().charge(intent)
            session = ParkingSession.objects.create(
                plate_number=form.cleaned_data["plate_number"],
                phone=form.cleaned_data["phone"],
                amount=form.cleaned_data["amount"],
                transaction=tx,
                status="active",
            )
            return redirect("parking:session_status", session_id=session.pk)
    else:
        form = ParkingPayForm()

    return render(request, "parking/pay.html", {"form": form})


def session_status_view(request, session_id):
    session = get_object_or_404(ParkingSession, pk=session_id)
    return render(request, "parking/session_status.html", {"session": session})
