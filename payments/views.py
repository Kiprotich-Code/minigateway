from django.shortcuts import render, redirect
from django.urls import reverse
from .models import PaymentChannel
from .forms import ChannelStep1Form, ChannelStep2Form


def channel_list(request):
    channels = PaymentChannel.objects.all().order_by("name")
    return render(request, "payments/channel_list.html", {"channels": channels})


def channel_form_step1(request):
    if request.method == "POST":
        form = ChannelStep1Form(request.POST)
        if form.is_valid():
            provider_type = form.cleaned_data["provider_type"]
            name = form.cleaned_data["name"]
            step2_url = reverse("payments:channel_step2")
            return redirect(f"{step2_url}?provider_type={provider_type}&name={name}")
    else:
        form = ChannelStep1Form()
    return render(request, "payments/channel_form_step1.html", {"form": form})


def channel_form_step2(request):
    provider_type = request.GET.get("provider_type", "")
    name = request.GET.get("name", "")

    if request.method == "POST":
        form = ChannelStep2Form(request.POST)
        if form.is_valid():
            channel = form.save(commit=False)
            channel.name = request.POST.get("_name", name)
            channel.provider_type = request.POST.get("_provider_type", provider_type)
            channel.save()
            return redirect("payments:channel_list")
    else:
        form = ChannelStep2Form()

    return render(
        request,
        "payments/channel_form_step2.html",
        {
            "form": form,
            "provider_type": provider_type,
            "name": name,
        },
    )
