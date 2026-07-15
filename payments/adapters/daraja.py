import base64
from datetime import datetime

import requests

from payments.adapters.base import BaseAdapter, StandardResult


class DarajaAdapter(BaseAdapter):
    SANDBOX_BASE = "https://sandbox.safaricom.co.ke"
    PRODUCTION_BASE = "https://api.safaricom.co.ke"

    def __init__(self, channel):
        """
        Accept a PaymentChannel instance (or any object with the matching
        attributes) and read the Daraja credentials from it.
        """
        self.channel = channel
        self.consumer_key = channel.consumer_key
        self.consumer_secret = channel.consumer_secret
        self.passkey = channel.passkey
        self.shortcode = channel.shortcode
        self.base_url = (
            self.SANDBOX_BASE
            if channel.environment == "sandbox"
            else self.PRODUCTION_BASE
        )

    def _get_access_token(self) -> str:
        """
        Fetch an OAuth access token from Safaricom using client credentials.
        Raises requests.HTTPError on non-2xx responses.
        """
        url = f"{self.base_url}/oauth/v1/generate?grant_type=client_credentials"
        response = requests.get(
            url,
            auth=(self.consumer_key, self.consumer_secret),
        )
        response.raise_for_status()
        return response.json()["access_token"]

    def _generate_password(self, timestamp: str) -> str:
        """
        Return the base64-encoded password for STK Push:
            base64(shortcode + passkey + timestamp)
        """
        raw = self.shortcode + self.passkey + timestamp
        return base64.b64encode(raw.encode()).decode()

    def charge(self, intent: dict) -> StandardResult:
        """
        Initiate an M-Pesa STK Push and return a StandardResult.

        On success the result has status="pending" and provider_reference set
        to the CheckoutRequestID returned by Safaricom.
        On HTTP error the result has status="failed" with the error message.
        """
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")

        try:
            token = self._get_access_token()
            password = self._generate_password(timestamp)

            payload = {
                "BusinessShortCode": self.shortcode,
                "Password": password,
                "Timestamp": timestamp,
                "TransactionType": "CustomerPayBillOnline",
                "Amount": int(intent["amount"]),
                "PartyA": intent["phone"],
                "PartyB": self.shortcode,
                "PhoneNumber": intent["phone"],
                "CallBackURL": self.channel.callback_url,
                "AccountReference": intent.get("reference", "PaymentRef"),
                "TransactionDesc": "Payment",
            }

            url = f"{self.base_url}/mpesa/stkpush/v1/processrequest"
            response = requests.post(
                url,
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            response.raise_for_status()
            response_json = response.json()

            return StandardResult(
                status="pending",
                provider_reference=response_json["CheckoutRequestID"],
                provider_transaction=response_json,
                message=response_json.get("ResponseDescription", ""),
                raw_response=response_json,
            )

        except requests.HTTPError as e:
            return StandardResult(
                status="failed",
                provider_reference="",
                provider_transaction={},
                message=str(e),
                raw_response=None,
            )

    def parse_callback(self, data: dict) -> StandardResult:
        """
        Parse the Daraja STK Push callback payload.

        ResultCode == 0  → status="completed"
        Anything else    → status="failed"
        """
        stk_callback = data.get("Body", {}).get("stkCallback", {})
        checkout_request_id = stk_callback.get("CheckoutRequestID", "")
        result_code = stk_callback.get("ResultCode", -1)
        result_desc = stk_callback.get("ResultDesc", "")

        status = "completed" if result_code == 0 else "failed"

        return StandardResult(
            status=status,
            provider_reference=checkout_request_id,
            provider_transaction=data,
            message=result_desc,
            raw_response=data,
        )
