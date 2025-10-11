"""Transaction parser with multi-line description support."""
import logging
import re
from typing import Optional
from datetime import datetime

from ..models import Transaction, TransactionType
from ..config import BankConfig
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)

MIN_BREAK_GAP = 20  # Minimum gap between words and numbers to trigger break


class MultilineDescriptionExtractor:
    """
    Handles extraction and combination of multiline descriptions.

    Based on Monopoly's DescriptionExtractor pattern.
    See: reference/monopoly/src/monopoly/statements/base.py:35-136
    """

    def __init__(self, transaction_pattern: re.Pattern):
        """
        Initialize extractor.

        Args:
            transaction_pattern: Compiled regex pattern for transaction lines
        """
        self.transaction_pattern = transaction_pattern
        self.words_pattern = re.compile(r"\s[A-Za-z]+")
        self.numbers_pattern = re.compile(r"[\d,]+\.?\d*")

    def get_multiline_description(
        self,
        initial_description: str,
        line_index: int,
        all_lines: list[str],
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

        # 2. New transaction line
        if self.transaction_pattern.search(line):
            return True

        # 3. Position check
        line_start_pos = self._get_start_position(line)
        if line_start_pos >= 0:
            if not self._is_within_margin(description_pos, line_start_pos, margin):
                return True

        # 4. Footer detection (words followed by numbers with large gap)
        words_match = self.words_pattern.search(line)
        numbers_match = self.numbers_pattern.search(line)

        if words_match and numbers_match:
            words_end = words_match.span()[1]
            numbers_start = numbers_match.span()[0]
            gap = numbers_start - words_end

            if gap > MIN_BREAK_GAP:
                logger.debug(f"Footer detected - gap of {gap} spaces")
                return True

        return False

    @staticmethod
    def _get_start_position(line: str) -> int:
        """Get the starting position of the first word in a line."""
        stripped = line.strip()
        if not stripped:
            return -1

        first_word = stripped.split()[0]
        return line.find(first_word)

    @staticmethod
    def _is_within_margin(pos1: int, pos2: int, margin: int) -> bool:
        """Check if two positions are within a specified margin."""
        return abs(pos1 - pos2) <= margin


class TransactionParser:
    """
    Parse transactions from extracted statement text.

    Uses bank-specific configuration to identify and extract transaction data.
    Supports multi-line descriptions, various date formats, and confidence scoring.
    """

    def __init__(self, bank_config: BankConfig):
        """
        Initialize transaction parser.

        Args:
            bank_config: Bank-specific configuration
        """
        self.config = bank_config
        self.transaction_pattern = self._compile_pattern()
        self.multiline_extractor = MultilineDescriptionExtractor(
            self.transaction_pattern
        )

    def _compile_pattern(self) -> re.Pattern:
        """Compile transaction regex pattern from config."""
        pattern_dict = self.config.transaction_patterns
        if not pattern_dict:
            raise ValueError(f"No transaction patterns defined for {self.config.bank_name}")

        # Use the 'standard' pattern by default
        pattern_str = pattern_dict.get('standard')
        if not pattern_str:
            # Fallback to first pattern if 'standard' not found
            pattern_str = next(iter(pattern_dict.values()))

        try:
            return re.compile(pattern_str, re.VERBOSE | re.MULTILINE)
        except re.error as e:
            raise ValueError(f"Invalid regex pattern for {self.config.bank_name}: {e}")

    def parse_text(
        self,
        text: str,
        statement_start_date: Optional[datetime] = None,
        statement_end_date: Optional[datetime] = None
    ) -> list[Transaction]:
        """
        Parse all transactions from statement text.

        Args:
            text: Extracted text from statement
            statement_start_date: Statement period start (for year inference)
            statement_end_date: Statement period end (for year inference)

        Returns:
            List of parsed transactions
        """
        lines = text.split('\n')
        transactions = []

        logger.info(f"Parsing {len(lines)} lines for transactions")

        for line_idx, line in enumerate(lines):
            if match := self.transaction_pattern.search(line):
                try:
                    transaction = self._parse_transaction(
                        match=match,
                        line=line,
                        line_index=line_idx,
                        all_lines=lines,
                        statement_start_date=statement_start_date,
                        statement_end_date=statement_end_date
                    )

                    if transaction:
                        transactions.append(transaction)
                        logger.debug(
                            f"Parsed transaction: {transaction.date} "
                            f"{transaction.description[:30]}... "
                            f"£{transaction.money_out or transaction.money_in}"
                        )

                except Exception as e:
                    logger.warning(f"Failed to parse transaction on line {line_idx}: {e}")
                    continue

        logger.info(f"Successfully parsed {len(transactions)} transactions")
        return transactions

    def _parse_transaction(
        self,
        match: re.Match,
        line: str,
        line_index: int,
        all_lines: list[str],
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> Optional[Transaction]:
        """
        Parse a single transaction from a regex match.

        Args:
            match: Regex match object
            line: Current line
            line_index: Index of current line
            all_lines: All lines from page
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            Transaction object or None if parsing fails
        """
        groups = match.groupdict()
        field_mapping = self.config.field_mapping

        # Extract date
        date_str = groups.get('date', '')
        if not date_str:
            logger.warning("No date found in transaction")
            return None

        # Parse date with year inference
        if statement_start_date and statement_end_date:
            transaction_date = infer_year_from_period(
                date_str,
                statement_start_date,
                statement_end_date
            )
        else:
            transaction_date = parse_date(date_str, self.config.date_formats)

        if not transaction_date:
            logger.warning(f"Could not parse date: {date_str}")
            return None

        # Extract description (with multi-line support)
        description = groups.get('description', '').strip()
        if not description:
            logger.warning("No description found in transaction")
            return None

        # Check if multi-line description
        description_pos = line.find(description)
        if description_pos >= 0 and line_index < len(all_lines) - 1:
            description = self.multiline_extractor.get_multiline_description(
                initial_description=description,
                line_index=line_index,
                all_lines=all_lines,
                description_position=description_pos,
                description_margin=3
            )

        # Extract amounts using field mapping
        money_in = 0.0
        money_out = 0.0
        balance = 0.0

        # Map bank-specific field names to our standard names
        paid_in_field = next(
            (k for k, v in field_mapping.items() if v == 'money_in'),
            'paid_in'
        )
        withdrawn_field = next(
            (k for k, v in field_mapping.items() if v == 'money_out'),
            'withdrawn'
        )

        if paid_in_str := groups.get(paid_in_field):
            money_in = parse_currency(paid_in_str) or 0.0

        if withdrawn_str := groups.get(withdrawn_field):
            money_out = parse_currency(withdrawn_str) or 0.0

        if balance_str := groups.get('balance'):
            balance = parse_currency(balance_str) or 0.0

        # Detect transaction type
        transaction_type = self._detect_transaction_type(description)

        # Calculate confidence score
        confidence = self._calculate_confidence(
            date=transaction_date,
            description=description,
            money_in=money_in,
            money_out=money_out,
            balance=balance
        )

        return Transaction(
            date=transaction_date,
            description=description,
            money_in=money_in,
            money_out=money_out,
            balance=balance,
            transaction_type=transaction_type,
            confidence=confidence,
            raw_text=line[:100]  # Store first 100 chars for debugging
        )

    def _detect_transaction_type(self, description: str) -> Optional[TransactionType]:
        """
        Detect transaction type from description keywords.

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

    def _calculate_confidence(
        self,
        date: datetime,
        description: str,
        money_in: float,
        money_out: float,
        balance: float
    ) -> float:
        """
        Calculate confidence score for the transaction.

        Args:
            date: Transaction date
            description: Transaction description
            money_in: Money in amount
            money_out: Money out amount
            balance: Balance after transaction

        Returns:
            Confidence score (0-100)
        """
        score = 100.0

        # Deduct points for issues
        if not date:
            score -= 30

        if not description or len(description) < 3:
            score -= 20

        if balance == 0.0:
            score -= 10

        if money_in == 0.0 and money_out == 0.0:
            score -= 25

        # Bonus for having both amounts and balance
        if (money_in > 0 or money_out > 0) and balance > 0:
            score += 5

        # Bonus for reasonable description length
        if 10 <= len(description) <= 200:
            score += 5

        return max(0.0, min(100.0, score))
