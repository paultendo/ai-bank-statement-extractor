"""Transaction parser with multi-line description support."""
import logging
import re
import sys
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
        self.multiline_extractor = None
        if self.transaction_pattern:
            self.multiline_extractor = MultilineDescriptionExtractor(
                self.transaction_pattern
            )

        # Column positions for debit/credit classification (Monopoly pattern)
        self.paid_in_pos = None
        self.withdrawn_pos = None
        self.header_line_idx = None

    def _compile_pattern(self) -> Optional[re.Pattern]:
        """Compile transaction regex pattern from config."""
        pattern_dict = self.config.transaction_patterns

        # Banks with custom parsers (Halifax, HSBC) don't need patterns
        if self.config.bank_name.lower() in ['halifax', 'hsbc']:
            return None

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
        # For Halifax: Use transaction type code (FPI, FPO, DD, etc.)
        if self.config.bank_name.lower() == 'halifax':
            return self._classify_halifax_by_type_code(line)

        # For other banks: Use keyword-based classification
        return self._classify_amount_by_keywords(description)

    def _classify_halifax_by_type_code(self, line: str) -> str:
        """
        Classify Halifax transaction using type code.

        Halifax has explicit type codes:
        - FPI, PI = money IN
        - FPO, DD, CHG, DEB, FEE, SO = money OUT

        Args:
            line: Transaction line containing type code

        Returns:
            'paid_in' or 'withdrawn'
        """
        # Extract type code (2-4 uppercase letters)
        type_match = re.search(r'\b([A-Z]{2,4})\b', line)
        if type_match:
            type_code = type_match.group(1)

            # Money IN codes
            if type_code in ['FPI', 'PI']:
                return 'paid_in'

            # Money OUT codes
            if type_code in ['FPO', 'DD', 'CHG', 'DEB', 'FEE', 'SO']:
                return 'withdrawn'

        # Default to withdrawn if can't determine
        logger.warning(f"Could not determine Halifax type code from line: {line[:80]}")
        return 'withdrawn'

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
        # Use bank-specific parsing logic
        logger.info(f"Parsing with bank: '{self.config.bank_name}'")
        if self.config.bank_name.lower() == 'halifax':
            return self._parse_halifax_text(text, statement_start_date, statement_end_date)
        elif self.config.bank_name.lower() == 'hsbc':
            logger.info("Routing to HSBC parser")
            return self._parse_hsbc_text(text, statement_start_date, statement_end_date)

        # Default parsing for NatWest and others
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
        # Allow for optional OD (overdrawn), CR (credit), DB (debit) suffixes after amounts
        amount_line_pattern = re.compile(r'.*\s+([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?(?:\s+(?:OD|CR|DB))?\s*$', re.IGNORECASE)

        # Pattern for table header (to detect column positions dynamically)
        # Supports both "Description" and "Details", and both column orders
        header_pattern = re.compile(r'Date\s+(Description|Details).*(Paid In.*Withdrawn|Withdrawn.*Paid In).*Balance', re.IGNORECASE)

        # Dynamic column thresholds (will be updated when we find headers)
        PAID_IN_THRESHOLD = 73  # Default from first page
        WITHDRAWN_THRESHOLD = 86

        # Track current date (one date applies to multiple transactions in NatWest format)
        current_date_str = None

        # NatWest-specific: Track if we just saw a BROUGHT FORWARD with balance error
        # If so, we need to calculate balances ourselves instead of trusting PDF
        recalculate_balances = False

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

            # Check for table header (update column thresholds dynamically)
            if header_pattern.search(line):
                # Extract column positions from header
                paid_in_match = re.search(r'Paid In', line, re.IGNORECASE)
                withdrawn_match = re.search(r'Withdrawn', line, re.IGNORECASE)
                balance_match = re.search(r'Balance', line, re.IGNORECASE)

                if paid_in_match and withdrawn_match and balance_match:
                    paid_in_start = paid_in_match.start()
                    withdrawn_start = withdrawn_match.start()
                    balance_start = balance_match.start()

                    # Calculate thresholds (mid-points between columns)
                    # Handle both column orders: "Paid In, Withdrawn" or "Withdrawn, Paid In"
                    if withdrawn_start < paid_in_start:
                        # Order: Withdrawn, Paid In, Balance
                        WITHDRAWN_THRESHOLD = (withdrawn_start + paid_in_start) // 2
                        PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2
                    else:
                        # Order: Paid In, Withdrawn, Balance
                        PAID_IN_THRESHOLD = (paid_in_start + withdrawn_start) // 2
                        WITHDRAWN_THRESHOLD = (withdrawn_start + balance_start) // 2

                    logger.debug(f"Updated NatWest column thresholds: Withdrawn={WITHDRAWN_THRESHOLD}, Paid In={PAID_IN_THRESHOLD}")

                idx += 1
                continue

            # Check if this line starts with a date - update current date
            # Supports both "18 DEC 2024" (month name) and "16/04/2024" (numeric) formats
            # Allow optional leading whitespace
            date_match = re.match(r'^\s*(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Z]{3}(?:\s+\d{2,4})?)', line, re.IGNORECASE)
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

                    # If previous line is a table header, stop
                    if header_pattern.search(prev_line):
                        break

                    # If previous line also has amounts, it's another transaction - stop
                    if amount_line_pattern.search(prev_line):
                        break

                    # This is a description line - add it
                    # Remove date prefix if present (dates are tracked separately)
                    # Supports both "18 DEC 2024" (month name) and "16/04/2024" (numeric) formats
                    desc_line = re.sub(r'^\s*\d{1,2}/\d{1,2}/\d{4}\s*|^\s*\d{1,2}\s+[A-Z]{3}(?:\s+\d{2,4})?\s*', '', prev_line, flags=re.IGNORECASE).strip()
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
                        # Skip balance validation for BROUGHT FORWARD transactions (period boundaries)
                        is_current_bf = 'BROUGHT FORWARD' in transaction.description.upper()

                        # Reset balance recalculation flag at new BROUGHT FORWARD
                        if is_current_bf:
                            recalculate_balances = False

                        # NatWest PDF quirk: If we need to recalculate balances (due to cascading errors),
                        # calculate balance from previous transaction instead of trusting PDF
                        if recalculate_balances and len(transactions) > 0 and not is_current_bf:
                            prev_balance = transactions[-1].balance
                            calculated_balance = prev_balance + transaction.money_in - transaction.money_out
                            if abs(transaction.balance - calculated_balance) > 0.01:
                                logger.debug(f"Recalculating balance from {transaction.balance:.2f} to {calculated_balance:.2f} for {transaction.description[:40]}")
                                transaction.balance = calculated_balance

                        # BALANCE VALIDATION: Auto-correct money_in/money_out direction and balance errors
                        # This is the self-healing pattern from Halifax/HSBC
                        # Only validate within periods, not across BROUGHT FORWARD boundaries
                        if transaction.balance > 0 and len(transactions) > 0 and not is_current_bf:
                            prev_transaction = transactions[-1]
                            prev_balance = prev_transaction.balance
                            balance_change = transaction.balance - prev_balance
                            calculated_change = transaction.money_in - transaction.money_out

                            # Special case for NatWest: First transaction after BROUGHT FORWARD shows
                            # the BF balance instead of the actual balance after the transaction.
                            # Detect this: previous transaction is BROUGHT FORWARD (has no money in/out)
                            # and current transaction's balance equals the BF balance
                            is_brought_forward = ((prev_transaction.money_in == 0 or prev_transaction.money_in is None or prev_transaction.money_in != prev_transaction.money_in) and
                                                (prev_transaction.money_out == 0 or prev_transaction.money_out is None or prev_transaction.money_out != prev_transaction.money_out) and
                                                'BROUGHT FORWARD' in prev_transaction.description.upper())

                            if is_brought_forward and abs(balance_change) < 0.01 and (transaction.money_in > 0 or transaction.money_out > 0):
                                # This is the first transaction after BF with balance showing BF amount
                                # Calculate the correct balance
                                corrected_balance = prev_balance + transaction.money_in - transaction.money_out
                                logger.info(
                                    f"Balance validation: NatWest BF quirk detected. "
                                    f"Correcting {transaction.description[:30]}... from {transaction.balance:.2f} to {corrected_balance:.2f}"
                                )
                                transaction.balance = corrected_balance
                                balance_change = corrected_balance - prev_balance
                                calculated_change = transaction.money_in - transaction.money_out
                                # Enable balance recalculation for subsequent transactions in this period
                                recalculate_balances = True

                            # If calculated change doesn't match actual balance change, swap direction
                            if abs(calculated_change - balance_change) > 0.01:
                                logger.debug(
                                    f"Balance validation: Swapping direction for {transaction.description[:30]}... "
                                    f"(calculated: {calculated_change:.2f}, actual: {balance_change:.2f})"
                                )
                                # Swap money_in and money_out
                                transaction.money_in, transaction.money_out = transaction.money_out, transaction.money_in

                                # Recalculate the expected change after swap
                                calculated_change_after_swap = transaction.money_in - transaction.money_out

                                # If it STILL doesn't match, the PDF balance itself is wrong
                                # (cascading error from previous transactions)
                                # Trust our calculated balance instead
                                if abs(calculated_change_after_swap - balance_change) > 0.01:
                                    corrected_balance = prev_balance + transaction.money_in - transaction.money_out
                                    logger.debug(
                                        f"Balance validation: Correcting balance from {transaction.balance:.2f} to {corrected_balance:.2f}"
                                    )
                                    transaction.balance = corrected_balance

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

    def _parse_halifax_text(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> list[Transaction]:
        """
        Parse Halifax statement text with period detection.

        Halifax combined PDFs contain multiple statements. Each statement starts with:
        - "Page 1 of X" indicator
        - "Document requested by:" with customer info
        - Statement period: "01 August 2024 to 31 August 2024"
        - Opening/closing balance lines (but these are AFTER first transactions!)

        We detect "Page 1 of" to identify statement boundaries and calculate the true
        opening balance by working backwards from the first transaction.

        Args:
            text: Extracted text
            statement_start_date: Statement period start (ignored for combined statements)
            statement_end_date: Statement period end (ignored for combined statements)

        Returns:
            List of transactions with BROUGHT FORWARD markers at period boundaries
        """
        lines = text.split('\n')
        transactions = []

        logger.info(f"Parsing Halifax combined statement: {len(lines)} lines")

        # Pattern for page 1 (new statement): "Page 1 of 5"
        page_one_pattern = re.compile(r'Page 1 of \d+')

        # Pattern for period headers: "01 December 2024 to 31 December 2024"
        period_pattern = re.compile(
            r'(\d{2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})\s+to\s+(\d{2}\s+(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{4})'
        )

        # Pattern for Halifax transaction line
        # Format: Date  Description  Type  [amounts...]  Balance
        # Capture the full line to preserve column positions
        transaction_pattern = re.compile(
            r'^(\d{2}\s+\w+\s+\d{2})\s{2,}(.+?)\s{2,}([A-Z]{2,4})(.+?)(-?[\d,]+\.\d{2})\s*$'
        )

        current_period_start = None
        current_period_end = None
        found_page_one = False
        first_transaction_in_period = None
        period_count = 0

        for idx, line in enumerate(lines):
            # Skip blank lines
            if not line.strip():
                continue

            # Check for "Page 1 of X" - indicates new statement period
            if page_one_pattern.search(line):
                found_page_one = True
                first_transaction_in_period = None
                logger.debug(f"Found 'Page 1 of' at line {idx} - new statement period")
                continue

            # Check for period header
            period_match = period_pattern.search(line)
            if period_match and found_page_one:
                period_start_str = period_match.group(1)
                period_end_str = period_match.group(2)
                current_period_start = parse_date(period_start_str, ["%d %B %Y"])
                current_period_end = parse_date(period_end_str, ["%d %B %Y"])
                period_count += 1
                logger.info(f"Period {period_count}: {period_start_str} to {period_end_str}")
                found_page_one = False  # Reset flag
                continue

            # Try to match transaction pattern
            match = transaction_pattern.search(line)
            if not match:
                continue

            try:
                date_str = match.group(1)  # "01 Aug 24"
                description = match.group(2).strip()  # "BRITISH GAS"
                type_code = match.group(3)  # "DD"
                amounts_text = match.group(4)  # Everything between Type and Balance
                balance_str = match.group(5)  # "-431.69"

                # Parse date with year inference using current period if available
                if current_period_start and current_period_end:
                    transaction_date = infer_year_from_period(
                        date_str,
                        current_period_start,
                        current_period_end
                    )
                else:
                    transaction_date = parse_date(date_str, self.config.date_formats)

                if not transaction_date:
                    logger.warning(f"Could not parse date: {date_str}")
                    continue

                # Extract all amounts from the amounts_text region
                amount_pattern = re.compile(r'([\d,]+\.\d{2})')
                amounts = amount_pattern.findall(amounts_text)

                balance = parse_currency(balance_str) or 0.0

                # Determine money in/out based on number of amounts and their positions
                money_in = 0.0
                money_out = 0.0

                if len(amounts) == 0:
                    # No transaction amount, only balance (shouldn't happen for normal transactions)
                    pass
                elif len(amounts) == 1:
                    # Single amount - need to determine if it's IN or OUT
                    amount_val = parse_currency(amounts[0]) or 0.0
                    amount_pos_in_line = line.find(amounts[0])

                    # HYBRID APPROACH: Use type code + position for better accuracy
                    # Some Halifax PDFs have inconsistent column alignment between pages

                    # First check if type code gives us a clear answer
                    if type_code in ['FPI', 'PI', 'BGC', 'DEP']:
                        # Type codes that are ALWAYS money in
                        money_in = amount_val
                    elif type_code in ['FPO', 'DD', 'CHG', 'FEE', 'SO', 'CPT']:
                        # Type codes that are ALWAYS money out
                        money_out = amount_val
                    else:
                        # Ambiguous type codes (like DEB) - use relative position from balance
                        # The balance is always the last amount in the line
                        balance_pos = line.rfind(balance_str)
                        distance_from_balance = balance_pos - amount_pos_in_line

                        # Money In is typically 50-60 chars before balance
                        # Money Out is typically 20-30 chars before balance
                        # Use 40 as threshold
                        if distance_from_balance > 40:
                            money_in = amount_val
                        else:
                            money_out = amount_val
                elif len(amounts) == 2:
                    # Two amounts: first is Money In, second is Money Out
                    money_in = parse_currency(amounts[0]) or 0.0
                    money_out = parse_currency(amounts[1]) or 0.0
                else:
                    # More than 2 amounts - unexpected, log warning
                    logger.warning(f"Found {len(amounts)} amounts in line: {line[:80]}")
                    # Assume first is in, last before balance is out
                    money_in = parse_currency(amounts[0]) or 0.0
                    money_out = parse_currency(amounts[-1]) or 0.0

                # VALIDATE DIRECTION: Use balance change as source of truth
                # If we have a previous transaction, verify the direction makes sense
                if len(transactions) > 0:
                    prev_balance = transactions[-1].balance
                    balance_change = balance - prev_balance

                    # Check if our classification matches the balance change
                    calculated_change = money_in - money_out

                    if abs(calculated_change - balance_change) > 0.01:
                        # Direction is wrong! Swap IN and OUT
                        logger.debug(f"Correcting direction for {description[:30]}: balance change {balance_change:.2f} != calculated {calculated_change:.2f}")
                        money_in, money_out = money_out, money_in

                # If this is the first transaction in a new period, insert BROUGHT FORWARD
                if first_transaction_in_period is None and current_period_start:
                    # Calculate opening balance by working backwards from first transaction
                    opening_balance = balance - money_in + money_out

                    brought_forward = Transaction(
                        date=current_period_start,
                        description="BROUGHT FORWARD",
                        money_in=0.0,
                        money_out=0.0,
                        balance=opening_balance,
                        transaction_type=None,
                        confidence=100.0,
                        raw_text=f"Calculated from first transaction"
                    )
                    transactions.append(brought_forward)
                    logger.debug(f"Added BROUGHT FORWARD: {current_period_start} £{opening_balance:.2f}")
                    first_transaction_in_period = True

                # Detect transaction type
                transaction_type = self._detect_transaction_type(description)

                # Calculate confidence
                confidence = self._calculate_confidence(
                    date=transaction_date,
                    description=description,
                    money_in=money_in,
                    money_out=money_out,
                    balance=balance
                )

                transaction = Transaction(
                    date=transaction_date,
                    description=description,
                    money_in=money_in,
                    money_out=money_out,
                    balance=balance,
                    transaction_type=transaction_type,
                    confidence=confidence,
                    raw_text=line[:100]
                )

                transactions.append(transaction)

            except Exception as e:
                logger.warning(f"Failed to parse Halifax transaction on line {idx}: {e}")
                continue

        logger.info(f"Successfully parsed {len(transactions)} Halifax transactions across {period_count} periods")
        return transactions

    def _parse_hsbc_text(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> list[Transaction]:
        """
        Parse HSBC statement text.

        HSBC format combines NatWest and Halifax characteristics:
        - Date tracking (one date applies to multiple transactions)
        - Multi-line descriptions
        - Payment type codes (VIS, CR, ))), DD, SO, BP, ATM, PIM)
        - "Paid out" and "Paid in" columns
        - Balance shown intermittently (not after every transaction)
        - Balance validation to auto-correct direction

        Args:
            text: Extracted text
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of transactions with balance validation
        """
        lines = text.split('\n')
        transactions = []

        logger.info(f"Parsing HSBC statement: {len(lines)} lines")
        logger.info(f"Statement dates: {statement_start_date} to {statement_end_date}")

        # Pattern for date line: "07 Feb 23" or similar at start of line
        date_pattern = re.compile(r'^(\d{1,2}\s+\w+\s+\d{2,4})\s+')

        # Pattern for payment type: VIS, CR, ))), DD, SO, BP, ATM, PIM, CHQ, TFR, DR
        payment_type_pattern = re.compile(r'^\s*(VIS|CR|\)\)\)|DD|SO|BP|ATM|PIM|CHQ|TFR|DR)\s+(.+)$')

        # Pattern for BALANCE BROUGHT/CARRIED FORWARD
        balance_marker_pattern = re.compile(r'BALANCE\s+(BROUGHT|CARRIED)\s+FORWARD')

        # Pattern for amounts and balance at end of line
        # Format: description    [paid_out]    [paid_in]    balance
        amount_pattern = re.compile(r'([\d,]+\.\d{2})')

        # Pattern for table header (to detect column positions)
        header_pattern = re.compile(r'Paid\s+out.*Paid\s+in.*Balance')

        current_date = None
        current_payment_type = None
        description_lines = []

        # Column thresholds (will be updated when header is found)
        PAID_OUT_THRESHOLD = 64  # Default
        PAID_IN_THRESHOLD = 90   # Default

        # PRE-SCAN: Find first header to set correct thresholds before processing
        # This fixes issues where transactions appear before the header in PDF
        for line in lines:
            if header_pattern.search(line):
                paid_out_match = re.search(r'Paid\s+out', line)
                paid_in_match = re.search(r'Paid\s+in', line)
                balance_match = re.search(r'Balance', line)

                if paid_out_match and paid_in_match and balance_match:
                    paid_out_start = paid_out_match.start()
                    paid_in_start = paid_in_match.start()
                    balance_start = balance_match.start()

                    # Calculate thresholds (mid-points between columns)
                    PAID_OUT_THRESHOLD = (paid_out_start + paid_in_start) // 2
                    PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2

                    logger.info(f"Pre-scan: Set column thresholds from header: Paid out ≤{PAID_OUT_THRESHOLD}, Paid in ≤{PAID_IN_THRESHOLD}")
                    break  # Use first header found

        idx = 0
        amount_lines_found = 0
        transactions_created = 0
        while idx < len(lines):
            line = lines[idx]

            # Skip blank lines
            if not line.strip():
                idx += 1
                continue

            # Check for table header (update column thresholds)
            if header_pattern.search(line):
                # Extract column positions from header
                paid_out_match = re.search(r'Paid\s+out', line)
                paid_in_match = re.search(r'Paid\s+in', line)
                balance_match = re.search(r'Balance', line)

                if paid_out_match and paid_in_match and balance_match:
                    paid_out_start = paid_out_match.start()
                    paid_in_start = paid_in_match.start()
                    balance_start = balance_match.start()

                    # Calculate thresholds (mid-points between columns)
                    PAID_OUT_THRESHOLD = (paid_out_start + paid_in_start) // 2
                    PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2

                    logger.debug(f"Updated column thresholds: Paid out ≤{PAID_OUT_THRESHOLD}, Paid in ≤{PAID_IN_THRESHOLD}, Balance >{PAID_IN_THRESHOLD}")

                idx += 1
                continue

            # Check for BALANCE BROUGHT/CARRIED FORWARD
            if balance_marker_pattern.search(line):
                # Extract balance from THIS LINE ONLY (not subsequent lines)
                amounts = amount_pattern.findall(line)
                if amounts:
                    # Take the rightmost amount (balance column)
                    balance = parse_currency(amounts[-1]) or 0.0

                    # Add BROUGHT FORWARD marker
                    if 'BROUGHT' in line and current_date:
                        brought_forward = Transaction(
                            date=current_date if current_date else statement_start_date,
                            description="BALANCE BROUGHT FORWARD",
                            money_in=0.0,
                            money_out=0.0,
                            balance=balance,
                            transaction_type=None,
                            confidence=100.0,
                            raw_text=line[:100]
                        )
                        transactions.append(brought_forward)
                        logger.debug(f"Added BROUGHT FORWARD: £{balance:.2f}")

                idx += 1
                continue

            # Check for new date
            date_match = date_pattern.search(line)
            if date_match:
                current_date_str = date_match.group(1)
                if statement_start_date and statement_end_date:
                    current_date = infer_year_from_period(
                        current_date_str,
                        statement_start_date,
                        statement_end_date
                    )
                else:
                    current_date = parse_date(current_date_str, self.config.date_formats)

                logger.debug(f"Found date: {current_date}")

                # Check if this line also has BALANCE BROUGHT FORWARD
                if balance_marker_pattern.search(line):
                    amounts = amount_pattern.findall(line)
                    if amounts:
                        balance = parse_currency(amounts[-1]) or 0.0
                        if 'BROUGHT' in line:
                            brought_forward = Transaction(
                                date=current_date,
                                description="BALANCE BROUGHT FORWARD",
                                money_in=0.0,
                                money_out=0.0,
                                balance=balance,
                                transaction_type=None,
                                confidence=100.0,
                                raw_text=line[:100]
                            )
                            transactions.append(brought_forward)
                            logger.debug(f"Added BROUGHT FORWARD: £{balance:.2f}")
                    idx += 1
                    continue

                # Rest of line after date might be payment type + description
                rest_of_line = line[date_match.end():]
                payment_match_in_date_line = payment_type_pattern.search(rest_of_line)
                if payment_match_in_date_line:
                    current_payment_type = payment_match_in_date_line.group(1)
                    desc_from_payment_line = payment_match_in_date_line.group(2).strip()

                    # Check if this line also has amounts
                    temp_amounts = []
                    for match in re.finditer(amount_pattern, line):
                        temp_amounts.append((match.group(1), match.start()))

                    if temp_amounts:
                        # Extract description before first amount
                        first_amt_pos = temp_amounts[0][1]
                        # Find where description ends (before first amount)
                        desc_part = desc_from_payment_line
                        for amt_str, _ in temp_amounts:
                            if amt_str in desc_part:
                                desc_part = desc_part[:desc_part.find(amt_str)].strip()
                                break
                        description_lines = [desc_part] if desc_part else [desc_from_payment_line]
                        # Don't continue - fall through to amount processing with payment_match set
                        payment_match = payment_match_in_date_line
                    else:
                        # No amounts on this line
                        description_lines = [desc_from_payment_line]
                        idx += 1
                        continue
                else:
                    # Date but no payment type
                    idx += 1
                    continue

            # Check for payment type (without date) - only if not already processed above
            if not date_match:
                payment_match = payment_type_pattern.search(line)
            else:
                payment_match = None

            if payment_match:
                # New transaction starts
                current_payment_type = payment_match.group(1)
                desc_from_payment_line = payment_match.group(2).strip()

                # Extract description part (everything before amounts if any)
                # Check if this line has amounts
                temp_amounts = []
                for match in re.finditer(amount_pattern, line):
                    temp_amounts.append((match.group(1), match.start()))

                if temp_amounts:
                    # Payment type line has amounts - extract description before first amount
                    first_amt_pos = temp_amounts[0][1]
                    # desc_from_payment_line already has text after payment type, use that
                    description_lines = [desc_from_payment_line[:desc_from_payment_line.find(temp_amounts[0][0])].strip()]
                else:
                    # No amounts on this line
                    description_lines = [desc_from_payment_line]

            # Check if this line has amounts (indicates end of transaction)
            amounts_with_pos = []
            for match in re.finditer(amount_pattern, line):
                amt_str = match.group(1)
                pos = match.start()
                # IMPORTANT: Ignore amounts that appear too far left (in description text)
                # E.g., "BRL 57.50 @ 7.5360" - the 57.50 is just descriptive, not the actual amount
                # Real transaction amounts appear in columns starting around position 60+
                MIN_AMOUNT_POSITION = 50
                if pos >= MIN_AMOUNT_POSITION:
                    amounts_with_pos.append((amt_str, pos))
                else:
                    logger.debug(f"Ignoring amount {amt_str} at position {pos} (< {MIN_AMOUNT_POSITION}) - likely description text")

            if amounts_with_pos and current_payment_type:
                amount_lines_found += 1
                logger.debug(f"Line {idx} has amounts: {amounts_with_pos}, payment_type={current_payment_type}")

                # If this is NOT a payment type line, add description continuation
                if not payment_match and line.strip():
                    # Extract description part (everything before first amount)
                    first_amount_pos = amounts_with_pos[0][1]
                    desc_part = line[:first_amount_pos].strip()
                    if desc_part:
                        description_lines.append(desc_part)

                # This line completes a transaction
                full_description = ' '.join(description_lines).strip() if description_lines else line.strip()

                # Use column thresholds detected from header
                # (These are updated when we see a new header line)

                money_in = 0.0
                money_out = 0.0
                balance = None

                # Classify amounts by position
                for amt_str, pos in amounts_with_pos:
                    amt_val = parse_currency(amt_str) or 0.0

                    if pos <= PAID_OUT_THRESHOLD:
                        money_out = amt_val
                    elif pos <= PAID_IN_THRESHOLD:
                        money_in = amt_val
                    else:
                        # Position indicates balance column
                        balance = amt_val

                # If no balance found on this line, use previous balance
                if balance is None and transactions:
                    # Calculate expected balance
                    prev_balance = transactions[-1].balance
                    balance = prev_balance + money_in - money_out

                # BALANCE VALIDATION: Auto-correct based on balance change
                if balance is not None and len(transactions) > 0:
                    prev_balance = transactions[-1].balance
                    balance_change = balance - prev_balance
                    calculated_change = money_in - money_out

                    if abs(calculated_change - balance_change) > 0.01:
                        # Check if swapping would improve the match
                        error_before = abs(calculated_change - balance_change)
                        calculated_after_swap = money_out - money_in
                        error_after = abs(calculated_after_swap - balance_change)

                        # Only swap if it actually improves things
                        if error_after < error_before:
                            logger.debug(f"Correcting HSBC direction for {full_description[:30]}: balance change {balance_change:.2f} != calculated {calculated_change:.2f} (error reduces from {error_before:.2f} to {error_after:.2f})")
                            money_in, money_out = money_out, money_in
                        else:
                            logger.debug(f"HSBC keeping original classification for {full_description[:30]}: swapping would make it worse (error {error_before:.2f} vs {error_after:.2f}), likely PDF rounding error")

                # Create transaction
                if current_date and full_description and balance is not None:
                    transaction_type = self._detect_transaction_type(full_description)
                    confidence = self._calculate_confidence(
                        date=current_date,
                        description=full_description,
                        money_in=money_in,
                        money_out=money_out,
                        balance=balance
                    )

                    transaction = Transaction(
                        date=current_date,
                        description=full_description,
                        money_in=money_in,
                        money_out=money_out,
                        balance=balance,
                        transaction_type=transaction_type,
                        confidence=confidence,
                        raw_text=line[:100]
                    )
                    transactions.append(transaction)
                    transactions_created += 1
                    logger.debug(f"Parsed HSBC: {current_date} {full_description[:20]} In: £{money_in:.2f} Out: £{money_out:.2f} Bal: £{balance:.2f}")

                # Reset for next transaction
                description_lines = []
                current_payment_type = None

                idx += 1
                continue

            # Otherwise, this is a description continuation line
            if line.strip() and not balance_marker_pattern.search(line):
                description_lines.append(line.strip())

            idx += 1

        logger.info(f"Successfully parsed {len(transactions)} HSBC transactions")
        logger.info(f"Debug stats: amount_lines_found={amount_lines_found}, transactions_created={transactions_created}")
        if len(transactions) == 0:
            logger.warning("No HSBC transactions found - check parsing logic")
            logger.debug(f"Final state: current_date={current_date}, current_payment_type={current_payment_type}, description_lines={description_lines}")
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
            # More than 2 amounts (e.g., foreign currency with exchange rate and fees)
            # Pattern: "USD 20.00 VRATE 1.2730 N-S TRN FEE 0.43    16.14    42,193.81"
            # Last amount = balance, second-to-last = transaction amount
            logger.warning(f"Found {len(amount_matches)} amounts, expected 1 or 2: {line[:80]}")
            balance = parse_currency(amount_matches[-1]) or 0.0
            transaction_amount = parse_currency(amount_matches[-2]) or 0.0

            # Classify the transaction amount
            classification = self._classify_amount_by_position(line, amount_matches[-2], full_description)
            if classification == 'paid_in':
                money_in = transaction_amount
            else:
                money_out = transaction_amount

        # Note: Balance validation is performed in the main parse loop
        # after this transaction is returned (see parse_text method)

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
