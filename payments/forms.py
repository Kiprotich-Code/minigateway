from django import forms
from .models import PaymentChannel


class ChannelStep1Form(forms.Form):
    name = forms.CharField(
        max_length=100,
        widget=forms.TextInput(attrs={"class": "form-control", "placeholder": "e.g. My M-Pesa Channel"}),
    )
    provider_type = forms.ChoiceField(
        choices=PaymentChannel.PROVIDER_CHOICES,
        widget=forms.Select(attrs={"class": "form-select"}),
    )


class ChannelStep2Form(forms.ModelForm):
    class Meta:
        model = PaymentChannel
        fields = [
            "shortcode",
            "till_number",
            "paybill_number",
            "account_reference_format",
            "callback_url",
            "validation_url",
            "confirmation_url",
            "consumer_key",
            "consumer_secret",
            "passkey",
            "transaction_timeout",
            "stk_push_enabled",
            "environment",
        ]
        widgets = {
            "shortcode": forms.TextInput(attrs={"class": "form-control"}),
            "till_number": forms.TextInput(attrs={"class": "form-control"}),
            "paybill_number": forms.TextInput(attrs={"class": "form-control"}),
            "account_reference_format": forms.TextInput(attrs={"class": "form-control"}),
            "callback_url": forms.URLInput(attrs={"class": "form-control"}),
            "validation_url": forms.URLInput(attrs={"class": "form-control"}),
            "confirmation_url": forms.URLInput(attrs={"class": "form-control"}),
            "consumer_key": forms.TextInput(attrs={"class": "form-control"}),
            "consumer_secret": forms.TextInput(attrs={"class": "form-control"}),
            "passkey": forms.TextInput(attrs={"class": "form-control"}),
            "transaction_timeout": forms.NumberInput(attrs={"class": "form-control"}),
            "stk_push_enabled": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "environment": forms.Select(attrs={"class": "form-select"}),
        }
