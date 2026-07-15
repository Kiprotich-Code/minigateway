import uuid

from payments.models import PaymentChannel, Transaction
from payments.registry import resolve


class PaymentGateway:
    def charge(self, intent: dict) -> Transaction:
        """
        Orchestrate a full charge cycle:
          1. Load and validate the PaymentChannel
          2. Resolve the correct adapter via the registry
          3. Call adapter.charge() to get a StandardResult
          4. Persist and return a Transaction

        Args:
            intent: dict with keys:
                - channel_id (int, required)
                - amount (Decimal/str/int, required)
                - phone (str, required)
                - reference (UUID or str, optional — defaults to a new uuid4)
                - metadata (dict, optional — defaults to {})

        Returns:
            The saved Transaction instance.

        Raises:
            ValueError: if the channel does not exist or is disabled.
        """
        # Normalise reference to str so it's JSON-safe for JSONFields and API calls
        reference = str(intent.get("reference", uuid.uuid4()))
        intent = {**intent, "reference": reference}  # adapter also sees a str

        # Step 1: Load channel, raise if missing or disabled
        try:
            channel = PaymentChannel.objects.get(id=intent["channel_id"])
        except PaymentChannel.DoesNotExist:
            raise ValueError(f"PaymentChannel with id={intent['channel_id']} does not exist")

        if not channel.enabled:
            raise ValueError(f"PaymentChannel {channel.id} is disabled")

        # Step 2: Resolve adapter from registry
        adapter = resolve(channel)

        # Step 3: Delegate the charge to the adapter
        result = adapter.charge(intent)

        # Step 4: Persist the transaction
        transaction = Transaction.objects.create(
            channel=channel,
            amount=intent["amount"],
            reference=reference,
            status=result.status,
            provider_reference=result.provider_reference,
            provider_transaction=result.provider_transaction,
            metadata=intent.get("metadata", {}),
        )

        return transaction
