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

        # Column positions for debit/credit classification (Monopoly pattern)
        self.paid_in_pos = None
        self.withdrawn_pos = None
        self.header_line_idx = None

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

    def _find_table_header(self, lines: list[str]) -> Optional[int]:
        """
        Find the table header line index.

        Looks for line containing column headers like "Date Description Paid In"

        Args:
            lines: All lines from statement

        Returns:
            Line index of header, or None if not found
        """
        header_patterns = [
            r'Date\s+Description\s+Paid\s+In.*Withdrawn.*Balance',
            r'Date\s+Description.*Paid.*Withdrawn.*Balance',
            r'Date.*Description.*Money\s+In.*Money\s+Out',
        ]

        for idx, line in enumerate(lines):
            for pattern in header_patterns:
                if re.search(pattern, line, re.IGNORECASE):
                    logger.debug(f"Found table header at line {idx}: {line[:80]}")
                    return idx

        logger.warning("Table header not found")
        return None

    def _extract_column_positions(self, header_line: str):
        """
        Extract column positions from header line (Monopoly pattern).

        Args:
            header_line: The header line containing column names
        """
        # Find "Paid In" position (end of column name)
        paid_in_match = re.search(r'Paid\s+In\s*\(\s*£\s*\)', header_line, re.IGNORECASE)
        if paid_in_match:
            # Right-aligned: use end position
            self.paid_in_pos = paid_in_match.end()
            logger.debug(f"Paid In column ends at position {self.paid_in_pos}")

        # Find "Withdrawn" position (end of column name)
        withdrawn_match = re.search(r'Withdrawn\s*\(\s*£\s*\)', header_line, re.IGNORECASE)
        if withdrawn_match:
            # Right-aligned: use end position
            self.withdrawn_pos = withdrawn_match.end()
            logger.debug(f"Withdrawn column ends at position {self.withdrawn_pos}")

        if not self.paid_in_pos or not self.withdrawn_pos:
            logger.warning("Could not extract column positions from header")

    def _classify_amount_by_position(self, line: str, amount_str: str, description: str) -> str:
        """
        Classify amount as paid_in or withdrawn.

        Uses keyword-based classification (more reliable with pdfplumber).
        Column position approach doesn't work well because pdfplumber doesn't preserve exact spacing.

        Args:
            line: The line containing the amount
            amount_str: The amount string to classify
            description: Full transaction description

        Returns:
            'paid_in' or 'withdrawn'
        """
        # Use keyword-based classification (more reliable)
        return self._classify_amount_by_keywords(description)

    def _classify_amount_by_keywords(self, description: str) -> str:
        """
        Fallback: Classify amount based on keywords in description.

        For NatWest statements:
        - "Automated Credit" = money IN
        - "OnLine Transaction", "Card Transaction", "Direct Debit" = money OUT
        - Default = money OUT

        Args:
            description: Transaction description

        Returns:
            'paid_in' or 'withdrawn'
        """
        description_lower = description.lower()

        # Money IN indicators (specific to UK banking)
        # ORDER MATTERS: Check specific phrases before generic ones
        money_in_keywords = [
            'automated credit',  # NatWest specific
            'cash & dep',  # Cash and Deposit Machine
            'deposit',
            'credit',
            'paid in',
            'salary',
            'refund',
            'cashback',
            'interest',
            ' from ',  # Transfer FROM someone (e.g., "FROM HUBBY")
            'received from',
        ]

        # Check for money in first
        if any(keyword in description_lower for keyword in money_in_keywords):
            return 'paid_in'

        # Money OUT indicators
        # ORDER MATTERS: Check specific phrases before generic ones
        money_out_keywords = [
            'cash withdrawal',  # Explicit withdrawal
            'atm',
            'card transaction',
            'card payment',
            'direct debit',
            'standing order',
            ' to ',  # Transfer TO someone
            'payment to',
            'pymt',  # Payment abbreviation
        ]

        if any(keyword in description_lower for keyword in money_out_keywords):
            return 'withdrawn'

        # Default: if "online transaction" without clear FROM/TO, assume withdrawal
        return 'withdrawn'

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

        # Find table header and extract column positions (Monopoly pattern)
        self.header_line_idx = self._find_table_header(lines)
        if self.header_line_idx is not None:
            self._extract_column_positions(lines[self.header_line_idx])

        # Only process lines after the header
        start_idx = (self.header_line_idx + 1) if self.header_line_idx is not None else 0

        # Pattern to match lines with amounts (these are transaction lines)
        # Note: Only requires 1+ spaces before amount (not 2+) to catch all transaction lines
        amount_line_pattern = re.compile(r'.*\s+([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?\s*$')

        # Track current date (one date applies to multiple transactions in NatWest format)
        current_date_str = None

        idx = start_idx
        while idx < len(lines):
            line = lines[idx]

            # Skip blank lines and footer lines
            if not line.strip():
                idx += 1
                continue
            if re.search(r'National Westminster Bank|Registered|Authorised|RETSTMT', line, re.IGNORECASE):
                idx += 1
                continue

            # Check if this line starts with a date - update current date
            date_match = re.match(r'^(\d{1,2}\s+[A-Z]{3}(?:\s+\d{4})?)', line)
            if date_match:
                current_date_str = date_match.group(1)
                logger.debug(f"Found date: {current_date_str}")

            # Check if this line has amounts (is a transaction line)
            if amount_match := amount_line_pattern.search(line):
                # This line has amounts - it's a transaction line
                # Look backwards to collect description lines (up to previous amount line)
                description_lines = []

                # Look backwards for description (up to 5 lines, stop at blank or another amount line)
                for lookback_idx in range(idx - 1, max(start_idx, idx - 6), -1):
                    prev_line = lines[lookback_idx]

                    if not prev_line.strip():
                        # Hit blank line, stop
                        break

                    # If previous line also has amounts, it's another transaction - stop
                    if amount_line_pattern.search(prev_line):
                        break

                    # This is a description line - add it
                    # Remove date prefix if present (dates are tracked separately)
                    desc_line = re.sub(r'^\d{1,2}\s+[A-Z]{3}(?:\s+\d{4})?\s*', '', prev_line).strip()
                    if desc_line:
                        description_lines.insert(0, desc_line)

                # Combine description lines
                full_description = ' '.join(description_lines) if description_lines else ''

                # Parse the transaction
                try:
                    transaction = self._parse_transaction_from_parts(
                        line=line,
                        description=full_description,
                        date_str=current_date_str,
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
                    logger.warning(f"Failed to parse transaction on line {idx}: {e}")

            idx += 1

        logger.info(f"Successfully parsed {len(transactions)} transactions")
        return transactions

    def _parse_transaction_from_parts(
        self,
        line: str,
        description: str,
        date_str: Optional[str],
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> Optional[Transaction]:
        """
        Parse transaction from separated parts.

        Args:
            line: Line containing amounts
            description: Combined description from previous lines
            date_str: Date string (if found)
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            Transaction object or None
        """
        # Extract amounts from the line
        amount_pattern = re.compile(r'([\d,]+\.\d{2})')
        amount_matches = amount_pattern.findall(line)

        if not amount_matches:
            logger.warning(f"No amounts found in line: {line[:80]}")
            return None

        # Parse date
        if not date_str:
            logger.warning(f"No date found for transaction: {description[:50]}")
            return None

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

        # Build full description (combine with any description text on the amount line)
        line_desc_match = re.match(r'(.+?)\s+[\d,]+\.\d{2}', line)
        if line_desc_match:
            line_desc = line_desc_match.group(1).strip()
            # Remove date from line description if present
            line_desc = re.sub(r'^\d{1,2}\s+[A-Z]{3}(?:\s+\d{4})?\s*', '', line_desc)
            if line_desc:
                full_description = f"{description} {line_desc}".strip() if description else line_desc
            else:
                full_description = description
        else:
            full_description = description

        if not full_description:
            logger.warning(f"No description found for transaction on line: {line[:80]}")
            return None

        # Parse amounts based on how many we found
        money_in = 0.0
        money_out = 0.0
        balance = 0.0

        if len(amount_matches) == 1:
            # Single amount = balance only (BROUGHT FORWARD, etc.)
            balance = parse_currency(amount_matches[0]) or 0.0
        elif len(amount_matches) == 2:
            # Two amounts: transaction + balance
            transaction_amount = parse_currency(amount_matches[0]) or 0.0
            balance = parse_currency(amount_matches[1]) or 0.0

            # Classify using keywords from description
            classification = self._classify_amount_by_position(line, amount_matches[0], full_description)
            if classification == 'paid_in':
                money_in = transaction_amount
            else:
                money_out = transaction_amount
        else:
            # More than 2 amounts - unclear, use last as balance
            logger.warning(f"Found {len(amount_matches)} amounts, expected 1 or 2: {line[:80]}")
            balance = parse_currency(amount_matches[-1]) or 0.0

        # Detect transaction type
        transaction_type = self._detect_transaction_type(full_description)

        # Calculate confidence
        confidence = self._calculate_confidence(
            date=transaction_date,
            description=full_description,
            money_in=money_in,
            money_out=money_out,
            balance=balance
        )

        return Transaction(
            date=transaction_date,
            description=full_description,
            money_in=money_in,
            money_out=money_out,
            balance=balance,
            transaction_type=transaction_type,
            confidence=confidence,
            raw_text=line[:100]
        )

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

        # Extract date - if not in this line, look backwards
        date_str = groups.get('date', '')
        if not date_str:
            # NatWest format: date might be on previous line(s)
            # Look backwards for a date pattern
            import re
            for prev_idx in range(max(0, line_index - 5), line_index):
                prev_line = all_lines[prev_idx]
                date_match = re.search(r'(\d{1,2}\s+[A-Z]{3}(?:\s+\d{4})?)', prev_line)
                if date_match:
                    date_str = date_match.group(1)
                    logger.debug(f"Found date on previous line {prev_idx}: {date_str}")
                    break

        if not date_str:
            logger.warning("No date found in transaction or previous lines")
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

        # For NatWest: if description looks like a reference number, get real description from previous line
        if description and re.match(r'^[A-Z0-9\s\-\*]+$', description) and len(description) < 50:
            # Look back for actual description
            for prev_idx in range(max(0, line_index - 3), line_index):
                prev_line = all_lines[prev_idx].strip()
                if prev_line and not re.match(r'^\s*[\d,]+\.\d{2}\s', prev_line):
                    # This looks like a description line, not an amount line
                    # Append current line as reference
                    full_desc = prev_line + " " + description
                    description = full_desc.strip()
                    logger.debug(f"Combined description from line {prev_idx}: {description[:50]}...")
                    break

        # Extract amounts using field mapping
        money_in = 0.0
        money_out = 0.0
        balance = 0.0

        # Get balance (might be None for single-amount lines)
        balance_str = groups.get('balance')
        amount_str = groups.get('amount')

        # NatWest special case: if balance is None, amount IS the balance (BROUGHT FORWARD, etc.)
        if amount_str and not balance_str:
            # Single amount line - it's the balance only
            balance = parse_currency(amount_str) or 0.0
            # No transaction amount (money_in and money_out stay 0)
        elif amount_str and balance_str:
            # Two amounts: first is transaction, second is balance
            amount = parse_currency(amount_str) or 0.0
            balance = parse_currency(balance_str) or 0.0

            # Classify using column position (Monopoly pattern)
            classification = self._classify_amount_by_position(line, amount_str)
            if classification == 'paid_in':
                money_in = amount
            else:
                money_out = amount
        elif balance_str:
            # Only balance provided
            balance = parse_currency(balance_str) or 0.0
        else:
            # Standard format with separate paid_in/withdrawn fields
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
