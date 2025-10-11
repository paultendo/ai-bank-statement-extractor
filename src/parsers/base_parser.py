"""Base transaction parser with shared utilities for all bank parsers.

This module provides the abstract base class and shared utilities that all
bank-specific parsers inherit from. Following the Template Method pattern,
it defines the parsing interface while allowing subclasses to implement
bank-specific logic.

Design Principles:
- Single Responsibility: Each bank parser handles only its format
- Open/Closed: Easy to add new banks without modifying existing code
- Liskov Substitution: All parsers can be used interchangeably
- Interface Segregation: Only implement what's needed
- Dependency Inversion: Depend on abstractions, not concrete implementations
"""

import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional, List

from ..models import Transaction, TransactionType
from ..config import BankConfig
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)

MIN_BREAK_GAP = 20  # Minimum gap between words and numbers to trigger break


class MultilineDescriptionExtractor:
    """
    Handles extraction and combination of multiline descriptions.

    This utility class helps parsers combine transaction descriptions
    that span multiple lines in PDF statements.

    Based on Monopoly's DescriptionExtractor pattern.
    See: reference/monopoly/src/monopoly/statements/base.py:35-136
    """

    def __init__(self, transaction_pattern: Optional[re.Pattern] = None):
        """
        Initialize extractor.

        Args:
            transaction_pattern: Compiled regex pattern for transaction lines
                                (optional for banks with custom parsers)
        """
        self.transaction_pattern = transaction_pattern
        self.words_pattern = re.compile(r"\s[A-Za-z]+")
        self.numbers_pattern = re.compile(r"[\d,]+\.?\d*")

    def get_multiline_description(
        self,
        initial_description: str,
        line_index: int,
        all_lines: List[str],
        description_position: int,
        description_margin: int = 3
    ) -> str:
        """
        Combine a transaction description spanning multiple lines.

        Args:
            initial_description: First line of description
            line_index: Current line index in all_lines
            all_lines: All lines from the page
            description_position: Character position where description starts
            description_margin: Allowed position deviation for continuation lines

        Returns:
            Combined description string
        """
        description = initial_description

        # Include subsequent lines until a break condition is met
        for next_line in all_lines[line_index + 1:]:
            if self._should_break_at_line(
                next_line,
                description_position,
                description_margin
            ):
                break

            # Append the continuation line
            description += f" {next_line.strip()}"

        return description.strip()

    def _should_break_at_line(
        self,
        line: str,
        description_pos: int,
        margin: int
    ) -> bool:
        """
        Determine if processing should stop at the current line.

        Break conditions:
        1. Blank line
        2. New transaction line (matches transaction pattern)
        3. Line starts too far left/right (outside margin)
        4. Line looks like a footer (words followed by numbers with large gap)

        Args:
            line: Line to check
            description_pos: Expected character position
            margin: Allowed position deviation

        Returns:
            True if should stop processing
        """
        # 1. Blank line
        if not line.strip():
            return True

        # 2. New transaction line (if pattern available)
        if self.transaction_pattern and self.transaction_pattern.match(line):
            return True

        # 3. Check position alignment
        first_char_pos = len(line) - len(line.lstrip())
        if abs(first_char_pos - description_pos) > margin:
            return True

        # 4. Footer detection (words followed by large gap then numbers)
        words_match = self.words_pattern.search(line)
        numbers_match = self.numbers_pattern.search(line)

        if words_match and numbers_match:
            gap = numbers_match.start() - words_match.end()
            if gap >= MIN_BREAK_GAP:
                return True

        return False


class BaseTransactionParser(ABC):
    """
    Abstract base class for bank-specific transaction parsers.

    This class defines the interface that all bank parsers must implement
    and provides shared utility methods for common parsing operations.

    Subclasses must implement:
    - parse_transactions(): Main parsing logic for their bank's format

    Subclasses can optionally override:
    - _find_table_header(): Custom header detection
    - _extract_column_positions(): Custom column extraction
    - _classify_amount(): Custom amount classification
    """

    def __init__(self, bank_config: BankConfig):
        """
        Initialize parser with bank configuration.

        Args:
            bank_config: Bank-specific configuration (patterns, formats, etc.)
        """
        self.config = bank_config
        self.transaction_pattern = self._compile_pattern()
        self.multiline_extractor = None
        if self.transaction_pattern:
            self.multiline_extractor = MultilineDescriptionExtractor(
                self.transaction_pattern
            )

        # Column positions (populated by subclasses if needed)
        self.paid_in_pos = None
        self.withdrawn_pos = None
        self.header_line_idx = None

    def _compile_pattern(self) -> Optional[re.Pattern]:
        """
        Compile transaction regex pattern from config.

        Banks with custom parsers (Halifax, HSBC, Barclays) may return None.

        Returns:
            Compiled regex pattern or None
        """
        pattern_dict = self.config.transaction_patterns

        # Banks with custom parsers don't need patterns
        if not pattern_dict:
            return None

        # Use the 'standard' pattern by default
        pattern_str = pattern_dict.get('standard')
        if not pattern_str:
            # Fallback to first pattern if 'standard' not found
            pattern_str = next(iter(pattern_dict.values()))

        if not pattern_str:
            logger.warning(f"No transaction patterns found for {self.config.bank_name}")
            return None

        try:
            return re.compile(pattern_str, re.MULTILINE | re.DOTALL)
        except re.error as e:
            logger.error(f"Invalid regex pattern for {self.config.bank_name}: {e}")
            return None

    @abstractmethod
    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse transactions from statement text.

        This is the main method that subclasses must implement with their
        bank-specific parsing logic.

        Args:
            text: Extracted text from statement
            statement_start_date: Statement period start (for year inference)
            statement_end_date: Statement period end (for year inference)

        Returns:
            List of parsed Transaction objects
        """
        pass

    def _find_table_header(self, lines: List[str]) -> Optional[int]:
        """
        Find the transaction table header line.

        Can be overridden by subclasses for custom header detection.

        Args:
            lines: All lines from statement

        Returns:
            Line index of header, or None if not found
        """
        # Default: Look for common header keywords
        header_keywords = ['date', 'description', 'amount', 'balance']

        for idx, line in enumerate(lines):
            line_lower = line.lower()
            matches = sum(1 for keyword in header_keywords if keyword in line_lower)
            if matches >= 3:  # At least 3 keywords present
                return idx

        return None

    def _extract_column_positions(self, header_line: str) -> None:
        """
        Extract column positions from header line.

        Can be overridden by subclasses for custom column extraction.

        Args:
            header_line: The header line containing column names
        """
        # Default implementation - subclasses should override
        pass

    def _classify_amount(
        self,
        line: str,
        amount: float,
        description: str
    ) -> str:
        """
        Classify whether amount is money in or money out.

        Can be overridden by subclasses for bank-specific classification logic.

        Args:
            line: Full transaction line
            amount: Parsed amount value
            description: Transaction description

        Returns:
            'paid_in' or 'withdrawn'
        """
        # Default: Use keyword-based classification
        return self._classify_amount_by_keywords(description)

    def _classify_amount_by_keywords(self, description: str) -> str:
        """
        Classify amount based on keywords in description.

        This is a fallback method that looks for common keywords
        indicating money in vs money out.

        Args:
            description: Transaction description

        Returns:
            'paid_in' or 'withdrawn'
        """
        description_lower = description.lower()

        # Money IN keywords
        money_in_keywords = [
            'deposit', 'credit', 'payment received', 'refund',
            'transfer in', 'interest', 'cashback', 'received',
            'salary', 'wages', 'benefit'
        ]

        # Money OUT keywords
        money_out_keywords = [
            'withdrawal', 'debit', 'payment to', 'purchase',
            'transfer out', 'fee', 'charge', 'direct debit',
            'standing order', 'card payment'
        ]

        # Check money IN keywords
        for keyword in money_in_keywords:
            if keyword in description_lower:
                return 'paid_in'

        # Check money OUT keywords
        for keyword in money_out_keywords:
            if keyword in description_lower:
                return 'withdrawn'

        # Default to withdrawn if can't determine
        return 'withdrawn'

    def _calculate_confidence(
        self,
        date: Optional[datetime],
        description: str,
        money_in: float,
        money_out: float,
        balance: float
    ) -> float:
        """
        Calculate confidence score for a transaction.

        Scores based on completeness and validity of extracted data.

        Args:
            date: Transaction date
            description: Transaction description
            money_in: Money in amount
            money_out: Money out amount
            balance: Account balance

        Returns:
            Confidence score (0-100)
        """
        score = 100.0

        # Deduct points for missing/invalid data
        if not date:
            score -= 30

        if not description or len(description) < 3:
            score -= 20

        if balance == 0.0:
            score -= 10

        if money_in == 0.0 and money_out == 0.0:
            score -= 25

        # Bonus for complete data
        if (money_in > 0 or money_out > 0) and balance > 0:
            score += 5

        # Bonus for reasonable description length
        if 10 <= len(description) <= 200:
            score += 5

        return max(0.0, min(100.0, score))

    def _detect_transaction_type(self, description: str) -> Optional[TransactionType]:
        """
        Detect transaction type from description keywords.

        Uses the transaction_types configuration from bank YAML to map
        keywords to transaction type enums.

        Args:
            description: Transaction description

        Returns:
            TransactionType enum or None
        """
        description_lower = description.lower()
        transaction_types = self.config.transaction_types

        if not transaction_types:
            return None

        for type_name, keywords in transaction_types.items():
            for keyword in keywords:
                if keyword.lower() in description_lower:
                    # Map type name to enum
                    type_map = {
                        'direct_debit': TransactionType.DIRECT_DEBIT,
                        'standing_order': TransactionType.STANDING_ORDER,
                        'card_payment': TransactionType.CARD_PAYMENT,
                        'online_transfer': TransactionType.TRANSFER,
                        'automated_credit': TransactionType.BANK_CREDIT,
                        'atm_withdrawal': TransactionType.CASH_WITHDRAWAL,
                        'interest': TransactionType.INTEREST,
                        'fee': TransactionType.FEE
                    }
                    return type_map.get(type_name, TransactionType.OTHER)

        return TransactionType.OTHER
