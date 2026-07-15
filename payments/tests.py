import base64
from unittest.mock import MagicMock, patch

from django.test import TestCase
from django.urls import reverse
from requests.exceptions import HTTPError

from .adapters.daraja import DarajaAdapter
from .gateway import PaymentGateway
from .models import PaymentChannel, Transaction
from .registry import resolve


class ChannelStep1ViewTests(TestCase):
    def test_get_renders_step1_form(self):
        response = self.client.get(reverse("payments:channel_step1"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/channel_form_step1.html")
        self.assertContains(response, "provider_type")

    def test_valid_post_redirects_to_step2_with_query_params(self):
        response = self.client.post(
            reverse("payments:channel_step1"),
            {"name": "Test Channel", "provider_type": "mpesa"},
        )
        self.assertEqual(response.status_code, 302)
        location = response["Location"]
        self.assertIn("/step2/", location)
        self.assertIn("provider_type=mpesa", location)
        self.assertIn("name=Test", location)  # name is URL-encoded in the redirect

    def test_invalid_post_rerenders_form(self):
        response = self.client.post(
            reverse("payments:channel_step1"),
            {"name": "", "provider_type": "mpesa"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/channel_form_step1.html")


class ChannelStep2ViewTests(TestCase):
    def test_get_renders_step2_form(self):
        url = reverse("payments:channel_step2") + "?provider_type=mpesa&name=MyChannel"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/channel_form_step2.html")
        self.assertContains(response, "MyChannel")
        self.assertContains(response, "Secure Credentials")

    def test_valid_post_creates_channel_and_redirects_to_list(self):
        url = reverse("payments:channel_step2") + "?provider_type=mpesa&name=NewMpesa"
        response = self.client.post(
            url,
            {
                "_name": "NewMpesa",
                "_provider_type": "mpesa",
                "shortcode": "174379",
                "till_number": "",
                "paybill_number": "",
                "account_reference_format": "",
                "callback_url": "",
                "validation_url": "",
                "confirmation_url": "",
                "consumer_key": "testkey",
                "consumer_secret": "testsecret",
                "passkey": "testpasskey",
                "transaction_timeout": 30,
                "stk_push_enabled": True,
                "environment": "sandbox",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse("payments:channel_list"))

        # Confirm it was saved
        self.assertEqual(PaymentChannel.objects.count(), 1)
        channel = PaymentChannel.objects.first()
        self.assertEqual(channel.name, "NewMpesa")
        self.assertEqual(channel.provider_type, "mpesa")
        self.assertEqual(channel.shortcode, "174379")

    def test_channel_appears_in_list_after_creation(self):
        PaymentChannel.objects.create(
            name="Listed Channel",
            provider_type="mpesa",
            environment="sandbox",
            enabled=True,
        )
        response = self.client.get(reverse("payments:channel_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Listed Channel")
        self.assertContains(response, "M-Pesa")


class ChannelListViewTests(TestCase):
    def test_empty_list(self):
        response = self.client.get(reverse("payments:channel_list"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "payments/channel_list.html")
        self.assertContains(response, "No payment channels yet")

    def test_lists_multiple_channels(self):
        PaymentChannel.objects.create(name="Alpha", provider_type="mpesa", environment="sandbox")
        PaymentChannel.objects.create(name="Beta", provider_type="stripe", environment="production")
        response = self.client.get(reverse("payments:channel_list"))
        self.assertContains(response, "Alpha")
        self.assertContains(response, "Beta")
        self.assertContains(response, "Stripe")


class RegistryResolveTests(TestCase):
    def _make_channel(self):
        return PaymentChannel(
            name="Test MPesa",
            provider_type="mpesa",
            environment="sandbox",
            consumer_key="key",
            consumer_secret="secret",
            passkey="passkey",
            shortcode="174379",
        )

    def test_resolve_mpesa_returns_daraja_adapter(self):
        """resolve() with provider_type='mpesa' returns a DarajaAdapter instance."""
        channel = self._make_channel()
        adapter = resolve(channel)
        self.assertIsInstance(adapter, DarajaAdapter)

    def test_resolve_twice_returns_independent_instances(self):
        """Calling resolve() twice with the same channel returns two independent objects."""
        channel = self._make_channel()
        adapter1 = resolve(channel)
        adapter2 = resolve(channel)
        self.assertIsNot(adapter1, adapter2)


class PaymentGatewayChargeTests(TestCase):
    def _make_channel(self, enabled=True):
        """Helper: create a real PaymentChannel row in the test DB."""
        return PaymentChannel.objects.create(
            name="Test MPesa Channel",
            provider_type="mpesa",
            environment="sandbox",
            enabled=enabled,
            consumer_key="testkey",
            consumer_secret="testsecret",
            passkey="testpasskey",
            shortcode="174379",
        )

    def _make_intent(self, channel):
        return {
            "channel_id": channel.id,
            "amount": "100.00",
            "phone": "254712345678",
        }

    def _pending_result(self):
        from payments.adapters.base import StandardResult
        return StandardResult(
            status="pending",
            provider_reference="ws_CO_STUB",
            provider_transaction={},
            message="Stub",
            raw_response=None,
        )

    @patch("payments.gateway.resolve")
    def test_charge_creates_transaction_with_pending_status(self, mock_resolve):
        """charge() persists a Transaction row whose status matches the adapter result."""
        mock_adapter = MagicMock()
        mock_adapter.charge.return_value = self._pending_result()
        mock_resolve.return_value = mock_adapter

        channel = self._make_channel()
        intent = self._make_intent(channel)

        PaymentGateway().charge(intent)

        self.assertEqual(Transaction.objects.count(), 1)
        tx = Transaction.objects.first()
        self.assertEqual(tx.status, "pending")

    @patch("payments.gateway.resolve")
    def test_charge_returns_transaction_instance(self, mock_resolve):
        """charge() returns a Transaction instance."""
        mock_adapter = MagicMock()
        mock_adapter.charge.return_value = self._pending_result()
        mock_resolve.return_value = mock_adapter

        channel = self._make_channel()
        intent = self._make_intent(channel)

        result = PaymentGateway().charge(intent)

        self.assertIsInstance(result, Transaction)

    def test_charge_raises_for_disabled_channel(self):
        """charge() raises ValueError for a disabled channel and creates no Transaction."""
        channel = self._make_channel(enabled=False)
        intent = self._make_intent(channel)

        with self.assertRaises(ValueError):
            PaymentGateway().charge(intent)

        self.assertEqual(Transaction.objects.count(), 0)

    @patch("payments.gateway.resolve")
    def test_charge_transaction_links_correct_channel(self, mock_resolve):
        """The returned transaction.channel is the same channel used in the intent."""
        mock_adapter = MagicMock()
        mock_adapter.charge.return_value = self._pending_result()
        mock_resolve.return_value = mock_adapter

        channel = self._make_channel()
        intent = self._make_intent(channel)

        tx = PaymentGateway().charge(intent)

        self.assertEqual(tx.channel, channel)


# ---------------------------------------------------------------------------
# Helpers shared by DarajaAdapter tests
# ---------------------------------------------------------------------------

def _make_daraja_channel(**kwargs):
    """Return an unsaved PaymentChannel-like mock for DarajaAdapter tests."""
    channel = MagicMock()
    channel.environment = kwargs.get("environment", "sandbox")
    channel.consumer_key = kwargs.get("consumer_key", "test_consumer_key")
    channel.consumer_secret = kwargs.get("consumer_secret", "test_consumer_secret")
    channel.passkey = kwargs.get("passkey", "bfb279f9aa9bdbcf158e97dd71a467cd2e0c893059b10f78e6b72ada1ed2c919")
    channel.shortcode = kwargs.get("shortcode", "174379")
    channel.callback_url = kwargs.get("callback_url", "https://example.com/callback")
    return channel


# ---------------------------------------------------------------------------
# DarajaAdapter unit tests
# ---------------------------------------------------------------------------

class DarajaAdapterAccessTokenTests(TestCase):
    @patch("payments.adapters.daraja.requests.get")
    def test_get_access_token_returns_token(self, mock_get):
        """_get_access_token() parses and returns the access_token string."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "abc123token", "expires_in": "3599"}
        mock_response.raise_for_status.return_value = None
        mock_get.return_value = mock_response

        adapter = DarajaAdapter(_make_daraja_channel())
        token = adapter._get_access_token()

        self.assertEqual(token, "abc123token")
        mock_get.assert_called_once()
        call_url = mock_get.call_args[0][0]
        self.assertIn("/oauth/v1/generate", call_url)
        self.assertIn("grant_type=client_credentials", call_url)


class DarajaAdapterPasswordTests(TestCase):
    def test_generate_password_is_base64_of_shortcode_passkey_timestamp(self):
        """_generate_password() returns base64(shortcode + passkey + timestamp)."""
        channel = _make_daraja_channel(shortcode="174379", passkey="mysecretpasskey")
        adapter = DarajaAdapter(channel)
        timestamp = "20240101120000"

        result = adapter._generate_password(timestamp)

        expected = base64.b64encode(("174379" + "mysecretpasskey" + timestamp).encode()).decode()
        self.assertEqual(result, expected)


class DarajaAdapterChargeTests(TestCase):
    def _mock_oauth_response(self):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {"access_token": "test_token"}
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    def _mock_stk_response(self, checkout_request_id="ws_CO_123456789"):
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "MerchantRequestID": "29115-34620561-1",
            "CheckoutRequestID": checkout_request_id,
            "ResponseCode": "0",
            "ResponseDescription": "Success. Request accepted for processing",
            "CustomerMessage": "Success. Request accepted for processing",
        }
        mock_resp.raise_for_status.return_value = None
        return mock_resp

    @patch("payments.adapters.daraja.requests.post")
    @patch("payments.adapters.daraja.requests.get")
    def test_charge_calls_stk_push_endpoint(self, mock_get, mock_post):
        """charge() makes a POST to the STK Push endpoint."""
        mock_get.return_value = self._mock_oauth_response()
        mock_post.return_value = self._mock_stk_response()

        adapter = DarajaAdapter(_make_daraja_channel())
        intent = {"amount": 100, "phone": "254712345678"}
        adapter.charge(intent)

        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        self.assertIn("/mpesa/stkpush/v1/processrequest", call_url)

    @patch("payments.adapters.daraja.requests.post")
    @patch("payments.adapters.daraja.requests.get")
    def test_charge_returns_pending_with_checkout_request_id(self, mock_get, mock_post):
        """charge() returns StandardResult with status='pending' and the CheckoutRequestID."""
        mock_get.return_value = self._mock_oauth_response()
        mock_post.return_value = self._mock_stk_response("ws_CO_UNIQUE_ID_999")

        adapter = DarajaAdapter(_make_daraja_channel())
        result = adapter.charge({"amount": 100, "phone": "254712345678"})

        self.assertEqual(result.status, "pending")
        self.assertEqual(result.provider_reference, "ws_CO_UNIQUE_ID_999")

    @patch("payments.adapters.daraja.requests.post")
    @patch("payments.adapters.daraja.requests.get")
    def test_charge_returns_failed_on_http_error(self, mock_get, mock_post):
        """charge() returns StandardResult with status='failed' when an HTTPError is raised."""
        mock_get.return_value = self._mock_oauth_response()
        mock_post.side_effect = HTTPError("400 Bad Request")

        adapter = DarajaAdapter(_make_daraja_channel())
        result = adapter.charge({"amount": 100, "phone": "254712345678"})

        self.assertEqual(result.status, "failed")
        self.assertIn("400 Bad Request", result.message)
        self.assertEqual(result.provider_reference, "")
        self.assertIsNone(result.raw_response)


class DarajaAdapterParseCallbackTests(TestCase):
    def _build_callback(self, result_code: int, checkout_request_id: str = "ws_CO_123") -> dict:
        return {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "29115-34620561-1",
                    "CheckoutRequestID": checkout_request_id,
                    "ResultCode": result_code,
                    "ResultDesc": "The service request is processed successfully."
                    if result_code == 0
                    else "Request cancelled by user",
                }
            }
        }

    def test_parse_callback_result_code_0_is_completed(self):
        """parse_callback() returns status='completed' when ResultCode is 0."""
        adapter = DarajaAdapter(_make_daraja_channel())
        data = self._build_callback(result_code=0, checkout_request_id="ws_CO_DONE")

        result = adapter.parse_callback(data)

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.provider_reference, "ws_CO_DONE")

    def test_parse_callback_nonzero_result_code_is_failed(self):
        """parse_callback() returns status='failed' for any non-zero ResultCode."""
        adapter = DarajaAdapter(_make_daraja_channel())
        data = self._build_callback(result_code=1032, checkout_request_id="ws_CO_CANCELLED")

        result = adapter.parse_callback(data)

        self.assertEqual(result.status, "failed")
        self.assertEqual(result.provider_reference, "ws_CO_CANCELLED")


# ---------------------------------------------------------------------------
# Daraja callback view tests (Task 9)
# ---------------------------------------------------------------------------

import json

from django.urls import reverse

from .signals import payment_completed, payment_failed


def _build_callback_payload(checkout_request_id: str, result_code: int) -> dict:
    """Build a minimal Safaricom STK Push callback payload."""
    result_desc = (
        "The service request is processed successfully."
        if result_code == 0
        else "Request cancelled by user"
    )
    return {
        "Body": {
            "stkCallback": {
                "MerchantRequestID": "test-merchant-request-id",
                "CheckoutRequestID": checkout_request_id,
                "ResultCode": result_code,
                "ResultDesc": result_desc,
            }
        }
    }


def _make_channel_and_transaction(status="pending", provider_reference="ws_CO_TEST"):
    """Create a real PaymentChannel + Transaction row for callback tests."""
    channel = PaymentChannel.objects.create(
        name="Callback Test Channel",
        provider_type="mpesa",
        environment="sandbox",
        enabled=True,
        consumer_key="testkey",
        consumer_secret="testsecret",
        passkey="testpasskey",
        shortcode="174379",
    )
    transaction = Transaction.objects.create(
        channel=channel,
        amount="100.00",
        status=status,
        provider_reference=provider_reference,
    )
    return channel, transaction


class DarajaCallbackViewTests(TestCase):
    CALLBACK_URL = "/payments/callbacks/daraja/"

    # ------------------------------------------------------------------
    # Happy-path: status transitions
    # ------------------------------------------------------------------

    def test_callback_updates_transaction_to_completed(self):
        """POST with ResultCode=0 sets transaction.status to 'completed'."""
        _, tx = _make_channel_and_transaction(provider_reference="ws_CO_COMP")
        payload = _build_callback_payload("ws_CO_COMP", result_code=0)

        response = self.client.post(
            self.CALLBACK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, "completed")

    def test_callback_updates_transaction_to_failed(self):
        """POST with ResultCode=1032 sets transaction.status to 'failed'."""
        _, tx = _make_channel_and_transaction(provider_reference="ws_CO_FAIL")
        payload = _build_callback_payload("ws_CO_FAIL", result_code=1032)

        response = self.client.post(
            self.CALLBACK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        tx.refresh_from_db()
        self.assertEqual(tx.status, "failed")

    # ------------------------------------------------------------------
    # Signal firing
    # ------------------------------------------------------------------

    def test_callback_fires_payment_completed_signal(self):
        """payment_completed signal is fired when ResultCode=0."""
        _, tx = _make_channel_and_transaction(provider_reference="ws_CO_SIG_OK")
        payload = _build_callback_payload("ws_CO_SIG_OK", result_code=0)

        received = []

        def handler(sender, transaction, **kwargs):
            received.append(transaction)

        payment_completed.connect(handler)
        try:
            self.client.post(
                self.CALLBACK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        finally:
            payment_completed.disconnect(handler)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].pk, tx.pk)

    def test_callback_fires_payment_failed_signal(self):
        """payment_failed signal is fired when ResultCode is non-zero."""
        _, tx = _make_channel_and_transaction(provider_reference="ws_CO_SIG_FAIL")
        payload = _build_callback_payload("ws_CO_SIG_FAIL", result_code=1032)

        received = []

        def handler(sender, transaction, **kwargs):
            received.append(transaction)

        payment_failed.connect(handler)
        try:
            self.client.post(
                self.CALLBACK_URL,
                data=json.dumps(payload),
                content_type="application/json",
            )
        finally:
            payment_failed.disconnect(handler)

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0].pk, tx.pk)

    # ------------------------------------------------------------------
    # Error cases
    # ------------------------------------------------------------------

    def test_callback_returns_404_for_unknown_checkout_id(self):
        """POST with a CheckoutRequestID that matches no Transaction → 404."""
        payload = _build_callback_payload("ws_CO_UNKNOWN_XYZ", result_code=0)

        response = self.client.post(
            self.CALLBACK_URL,
            data=json.dumps(payload),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 404)

    def test_callback_returns_400_for_invalid_json(self):
        """POST with a non-JSON body → 400."""
        response = self.client.post(
            self.CALLBACK_URL,
            data="this is not json!!!",
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)

    def test_callback_returns_405_for_get_request(self):
        """Non-POST requests to the callback endpoint → 405."""
        response = self.client.get(self.CALLBACK_URL)
        self.assertEqual(response.status_code, 405)
