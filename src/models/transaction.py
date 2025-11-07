"""Transaction data model."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from enum import Enum


class TransactionType(Enum):
    """Transaction type enumeration."""
    DIRECT_DEBIT = "Direct Debit"
    STANDING_ORDER = "Standing Order"
    CARD_PAYMENT = "Card Payment"
    CASH_WITHDRAWAL = "Cash Withdrawal"
    TRANSFER = "Transfer"
    BANK_CREDIT = "Bank Credit"
    CHEQUE = "Cheque"
    FEE = "Fee"
    INTEREST = "Interest"
    OTHER = "Other"


@dataclass
class Transaction:
    """
    Represents a single bank transaction.

    Attributes:
        date: Transaction date
        description: Transaction description
        money_in: Amount credited (0.00 if none)
        money_out: Amount debited (0.00 if none)
        balance: Account balance after transaction
        transaction_type: Type of transaction
        confidence: Confidence score (0-100)
        raw_text: Original text from statement
        page_number: Page number in statement
        description_translated: English translation of description (for non-English banks)
    """
    date: datetime
    description: str
    money_in: float
    money_out: float
    balance: float
    transaction_type: Optional[TransactionType] = None
    confidence: float = 100.0
    raw_text: Optional[str] = None
    page_number: Optional[int] = None
    description_translated: Optional[str] = None

    def __post_init__(self):
        """Validate transaction data."""
        if self.money_in < 0:
            raise ValueError("money_in cannot be negative")
        if self.money_out < 0:
            raise ValueError("money_out cannot be negative")
        if self.confidence < 0 or self.confidence > 100:
            raise ValueError("confidence must be between 0 and 100")

    def to_dict(self) -> dict:
        """Convert transaction to dictionary."""
        result = {
            'date': self.date.strftime('%Y-%m-%d'),
            'description': self.description,
            'money_in': round(self.money_in, 2),
            'money_out': round(self.money_out, 2),
            'balance': round(self.balance, 2),
            'transaction_type': self.transaction_type.value if self.transaction_type else None,
            'confidence': round(self.confidence, 2),
            'page_number': self.page_number
        }
        if self.description_translated:
            result['description_translated'] = self.description_translated
        return result
