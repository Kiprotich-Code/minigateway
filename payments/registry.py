from payments.adapters.base import BaseAdapter
from payments.adapters.daraja import DarajaAdapter

PROVIDER_REGISTRY = {
    "mpesa": DarajaAdapter,
}


def resolve(channel) -> BaseAdapter:
    """Instantiate and return the correct adapter for the given channel."""
    adapter_class = PROVIDER_REGISTRY[channel.provider_type]
    return adapter_class(channel)
