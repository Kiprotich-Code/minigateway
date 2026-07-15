from django import forms

from payments.models import PaymentChannel


class ParkingPayForm(forms.Form):
    plate_number = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. KAA 123A"}),
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. 254712345678"}),
    )
    amount = forms.DecimalField(
        max_digits=10,
        decimal_places=2,
        widget=forms.NumberInput(attrs={"class": "form-control", "placeholder": "Amount (KES)"}),
    )
    channel = forms.ModelChoiceField(
        queryset=PaymentChannel.objects.filter(enabled=True),
        widget=forms.Select(attrs={"class": "form-select"}),
        empty_label="Select payment channel",
    )
