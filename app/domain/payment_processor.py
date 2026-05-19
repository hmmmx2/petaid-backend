"""PaymentProcessor — Adapter pattern (SRS 5.3.1, 3.3.6).

The abstract class defines the interface the :class:`Donation` entity uses
to execute a payment. The concrete :class:`MockPaymentProcessor` simulates
a successful charge so the donation scenario can be demonstrated without a
real banking integration (Assignment 3 simplification).
"""
from __future__ import annotations

import secrets
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime, timezone

from app.domain.exceptions import InvalidInputException, PaymentFailedException

# Minimum accepted donation in cents (SRS 1.3.2 — boundary cases).
MIN_DONATION_CENTS = 100  # $1.00
MAX_DONATION_CENTS = 1_000_000_00  # $1,000,000


@dataclass(frozen=True)
class TransactionResult:
    """Immutable receipt returned by :meth:`PaymentProcessor.charge`."""

    transaction_ref: str
    provider: str
    amount_cents: int
    currency: str
    final_status: str
    processed_at: datetime


class PaymentProcessor(ABC):
    """Interface :class:`Donation` calls into.

    Concrete adapters wrap a specific external provider (Stripe, PayPal,
    etc.) and are interchangeable. The :class:`Donation` class never sees
    provider-specific request/response shapes.
    """

    name: str = "abstract"

    @abstractmethod
    def charge(
        self, *, amount_cents: int, currency: str, donor_label: str
    ) -> TransactionResult:
        """Execute a single charge and return its outcome.

        Raises :class:`PaymentFailedException` on a non-recoverable error.
        Raises :class:`InvalidInputException` if the amount is out of
        bounds.
        """

    # ------------------------------------------------------------------ #
    # Shared boundary validation                                         #
    # ------------------------------------------------------------------ #
    @staticmethod
    def _validate_amount(amount_cents: int) -> None:
        if amount_cents < MIN_DONATION_CENTS:
            raise InvalidInputException(
                "amount", f"Minimum donation is ${MIN_DONATION_CENTS / 100:.2f}."
            )
        if amount_cents > MAX_DONATION_CENTS:
            raise InvalidInputException("amount", "Amount exceeds the allowed maximum.")


class MockPaymentProcessor(PaymentProcessor):
    """Simulated provider used in the Assignment 3 prototype.

    Always succeeds — donation scenarios are demonstrable without a real
    payment gateway.
    """

    name = "MockProvider"

    def charge(
        self, *, amount_cents: int, currency: str, donor_label: str
    ) -> TransactionResult:
        self._validate_amount(amount_cents)
        if currency.upper() not in {"USD", "EUR", "MYR", "SGD", "GBP"}:
            raise InvalidInputException("currency", "Unsupported currency.")
        return TransactionResult(
            transaction_ref=f"TXN-{secrets.token_hex(8).upper()}",
            provider=self.name,
            amount_cents=amount_cents,
            currency=currency.upper(),
            final_status="succeeded",
            processed_at=datetime.now(timezone.utc),
        )


class FailingPaymentProcessor(PaymentProcessor):
    """Test-only adapter that always declines. Useful for the failure-path
    sequence diagram in SRS Figure 6.
    """

    name = "FailingProvider"

    def charge(
        self, *, amount_cents: int, currency: str, donor_label: str
    ) -> TransactionResult:
        self._validate_amount(amount_cents)
        raise PaymentFailedException("Card was declined by the provider.")
