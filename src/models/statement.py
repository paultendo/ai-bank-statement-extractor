"""Bank statement metadata model."""
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Statement:
    """
    Represents bank statement metadata.

    Attributes:
        bank_name: Name of the bank
        account_number: Last 4 digits of account number
        account_holder: Account holder name (if available)
        statement_start_date: Statement period start date
        statement_end_date: Statement period end date
        opening_balance: Opening balance
        closing_balance: Closing balance
        currency: Currency code (e.g., 'GBP', 'USD')
        sort_code: Bank sort code (if available)
    """
    bank_name: str
    account_number: str
    statement_start_date: datetime
    statement_end_date: datetime
    opening_balance: float
    closing_balance: float
    currency: str = "GBP"
    account_holder: Optional[str] = None
    sort_code: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert statement metadata to dictionary."""
        return {
            'bank_name': self.bank_name,
            'account_number': self.account_number,
            'account_holder': self.account_holder,
            'statement_start_date': self.statement_start_date.strftime('%Y-%m-%d'),
            'statement_end_date': self.statement_end_date.strftime('%Y-%m-%d'),
            'opening_balance': round(self.opening_balance, 2),
            'closing_balance': round(self.closing_balance, 2),
            'currency': self.currency,
            'sort_code': self.sort_code
        }
