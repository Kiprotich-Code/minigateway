from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from parking.models import ParkingSession
from payments.adapters.base import StandardResult
from payments.models import PaymentChannel, Transaction


def make_channel():
    """Helper: create a minimal enabled PaymentChannel."""
    return PaymentChannel.objects.create(
        name="Test M-Pesa",
        provider_type="mpesa",
        environment="sandbox",
        enabled=True,
        shortcode="174379",
        consumer_key="test_key",
        consumer_secret="test_secret",
        passkey="test_passkey",
        callback_url="https://example.com/callback",
    )


def make_transaction(channel):
    """Helper: create a minimal Transaction linked to a channel."""
    return Transaction.objects.create(
        channel=channel,
        amount="100.00",
        status="pending",
        provider_reference="ws_CO_test",
        provider_transaction={},
        metadata={},
    )


class PayViewGetTest(TestCase):
    def test_pay_view_get_renders_form(self):
        """GET /parking/pay/ should return 200 and use the pay template."""
        response = self.client.get(reverse("parking:pay"))
        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "parking/pay.html")
        self.assertIn("form", response.context)


class PayViewPostTest(TestCase):
    def _stub_result(self):
        return StandardResult(
            status="pending",
            provider_reference="ws_CO_12345",
            provider_transaction={"CheckoutRequestID": "ws_CO_12345"},
            message="Success",
            raw_response=None,
        )

    @patch("parking.views.PaymentGateway")
    def test_pay_view_post_creates_session_and_redirects(self, MockGateway):
        """Valid POST should create a ParkingSession and redirect to session status."""
        channel = make_channel()

        # Gateway mock returns a real Transaction so FK integrity holds
        tx = make_transaction(channel)
        MockGateway.return_value.charge.return_value = tx

        post_data = {
            "plate_number": "KAA 001A",
            "phone": "254712345678",
            "amount": "200.00",
            "channel": channel.pk,
        }
        response = self.client.post(reverse("parking:pay"), data=post_data)

        self.assertEqual(ParkingSession.objects.count(), 1)
        session = ParkingSession.objects.first()
        self.assertRedirects(
            response,
            reverse("parking:session_status", kwargs={"session_id": session.pk}),
        )

    @patch("parking.views.PaymentGateway")
    def test_pay_view_links_session_to_transaction(self, MockGateway):
        """The created ParkingSession.transaction should not be None."""
        channel = make_channel()
        tx = make_transaction(channel)
        MockGateway.return_value.charge.return_value = tx

        post_data = {
            "plate_number": "KBB 002B",
            "phone": "254700000001",
            "amount": "50.00",
            "channel": channel.pk,
        }
        self.client.post(reverse("parking:pay"), data=post_data)

        session = ParkingSession.objects.first()
        self.assertIsNotNone(session)
        self.assertIsNotNone(session.transaction)
        self.assertEqual(session.transaction.pk, tx.pk)


class SessionStatusViewTest(TestCase):
    def test_session_status_view_shows_session(self):
        """GET /parking/session/<id>/ should return 200 and show the session."""
        channel = make_channel()
        tx = make_transaction(channel)
        session = ParkingSession.objects.create(
            plate_number="KCC 003C",
            phone="254711111111",
            amount="300.00",
            status="active",
            transaction=tx,
        )

        url = reverse("parking:session_status", kwargs={"session_id": session.pk})
        response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(response, "parking/session_status.html")
        self.assertEqual(response.context["session"].pk, session.pk)
        self.assertContains(response, "KCC 003C")


class SignalListenerTest(TestCase):
    def test_on_payment_completed_marks_session_paid(self):
        """Firing payment_completed for a transaction should set its ParkingSession to 'paid'."""
        from payments.signals import payment_completed

        channel = make_channel()
        tx = make_transaction(channel)
        session = ParkingSession.objects.create(
            plate_number="KDD 004D",
            phone="254722222222",
            amount="150.00",
            status="active",
            transaction=tx,
        )

        payment_completed.send(sender=Transaction, transaction=tx)

        session.refresh_from_db()
        self.assertEqual(session.status, "paid")

    def test_on_payment_completed_does_not_affect_other_sessions(self):
        """Firing the signal for one transaction must not change unrelated sessions."""
        from payments.signals import payment_completed

        channel = make_channel()
        tx1 = make_transaction(channel)
        tx2 = make_transaction(channel)

        session1 = ParkingSession.objects.create(
            plate_number="KEE 005E",
            phone="254733333333",
            amount="200.00",
            status="active",
            transaction=tx1,
        )
        session2 = ParkingSession.objects.create(
            plate_number="KFF 006F",
            phone="254744444444",
            amount="200.00",
            status="active",
            transaction=tx2,
        )

        payment_completed.send(sender=Transaction, transaction=tx1)

        session1.refresh_from_db()
        session2.refresh_from_db()
        self.assertEqual(session1.status, "paid")
        self.assertEqual(session2.status, "active")
