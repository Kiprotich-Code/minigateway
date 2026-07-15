from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class StandardResult:
    status: str                 # "pending" | "completed" | "failed"
    provider_reference: str     # e.g. CheckoutRequestID from Daraja
    provider_transaction: dict  # full provider response payload
    message: str
    raw_response: Any


class BaseAdapter(ABC):
    @abstractmethod
    def charge(self, intent: dict) -> StandardResult:
        """Initiate a payment charge and return a StandardResult."""
        ...

    @abstractmethod
    def parse_callback(self, data: dict) -> StandardResult:
        """Parse an inbound provider callback and return a StandardResult."""
        ...
