"""NatWest bank statement parser.

Handles NatWest-specific statement format with dynamic column detection,
balance validation, and self-healing for PDF errors.

Format characteristics:
- Date tracking (one date applies to multiple transactions)
- Description lines before amount lines (need lookback)
- Dynamic column positions (varies across pages)
- Both column orders supported: "Paid In, Withdrawn" or "Withdrawn, Paid In"
- Both date formats: "DD/MM/YYYY" and "DD MMM YYYY"
- OD/CR/DB suffixes after amounts
- Balance validation with self-healing (swaps direction if needed)
- BROUGHT FORWARD handling with balance recalculation for cascading errors
- Foreign currency transactions (3+ amounts on one line)
"""

import calendar
import logging
import re
from datetime import datetime
from typing import Optional, List

from .base_parser import BaseTransactionParser
from ..models import Transaction
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)


class NatWestParser(BaseTransactionParser):
    """Parser for NatWest bank statements."""

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse NatWest statement text with lookback description collection.

        NatWest format characteristics:
        - Transactions have description on one or more lines
        - Followed by a line with amounts
        - Date tracking (one date applies to multiple transactions)
        - Dynamic column positions (detect from header)

        Args:
            text: Extracted text
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of parsed transactions
        """
        lines = text.split('\n')
        transactions = []

        logger.info(f"Parsing NatWest statement: {len(lines)} lines")

        # Pattern to match lines with amounts (these are transaction lines)
        amount_line_pattern = re.compile(r'.*\s+([\d,]+\.\d{2})(?:\s+([\d,]+\.\d{2}))?(?:\s+(?:OD|CR|DB))?\s*$', re.IGNORECASE)

        # Pattern for table header (to detect column positions dynamically)
        # Handles two formats:
        # Format 1: "Date Description ... Paid In ... Withdrawn ... Balance"
        # Format 2: "Date Type Description ... Paid in ... Paid out ... Balance"
        header_pattern = re.compile(
            r'Date\s+(?:Type\s+)?(Description|Details).*(Paid\s+[Ii]n.*(Withdrawn|Paid\s+out)|Withdrawn.*Paid\s+[Ii]n).*Balance',
            re.IGNORECASE
        )

        # Dynamic column thresholds (will be updated when we find headers)
        PAID_IN_THRESHOLD = 73  # Default from first page
        WITHDRAWN_THRESHOLD = 86

        # Track current date (one date applies to multiple transactions in NatWest format)
        current_date_str = None

        # NatWest-specific: Track if we need to recalculate balances
        recalculate_balances = False

        # Find table header to determine start position
        header_line_idx = self._find_natwest_header(lines)
        start_idx = (header_line_idx + 1) if header_line_idx is not None else 0

        # Detect format variant by checking if header has "Type" column
        # Format A (old): "Date Description ... Paid In ... Withdrawn ... Balance"
        # Format B (new): "Date Type Description ... Paid in ... Paid out ... Balance"
        has_type_column = False
        if header_line_idx is not None:
            header_line = lines[header_line_idx]
            has_type_column = bool(re.search(r'Date\s+Type\s+Description', header_line, re.IGNORECASE))
            logger.info(f"NatWest format variant: {'B (with Type column)' if has_type_column else 'A (without Type column)'}")

        # For Format B, use HSBC-style parsing (dates and amounts on same line)
        if has_type_column:
            return self._parse_format_b(lines, start_idx, statement_start_date, statement_end_date)

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
                # Try both "Paid In" and "Paid in", "Withdrawn" and "Paid out"
                paid_in_match = re.search(r'Paid\s+[Ii]n', line, re.IGNORECASE)
                withdrawn_match = re.search(r'Withdrawn|Paid\s+out', line, re.IGNORECASE)
                balance_match = re.search(r'Balance', line, re.IGNORECASE)

                if paid_in_match and withdrawn_match and balance_match:
                    paid_in_start = paid_in_match.start()
                    withdrawn_start = withdrawn_match.start()
                    balance_start = balance_match.start()

                    # Calculate thresholds (mid-points between columns)
                    # Handle both column orders
                    if withdrawn_start < paid_in_start:
                        # Order: Withdrawn/Paid out, Paid in, Balance
                        WITHDRAWN_THRESHOLD = (withdrawn_start + paid_in_start) // 2
                        PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2
                    else:
                        # Order: Paid in, Withdrawn/Paid out, Balance
                        PAID_IN_THRESHOLD = (paid_in_start + withdrawn_start) // 2
                        WITHDRAWN_THRESHOLD = (withdrawn_start + balance_start) // 2

                    logger.debug(f"Updated NatWest column thresholds: Withdrawn/Out={WITHDRAWN_THRESHOLD}, Paid In={PAID_IN_THRESHOLD}")

                idx += 1
                continue

            # Check if this line starts with a date - update current date
            # Supports both "18 DEC 2024" (month name) and "16/04/2024" (numeric) formats
            date_match = re.match(
                r'^\s*(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Z]{3}(?:\s+\d{2,4})?|\d{1,2}[A-Z]{3}\d{2,4})',
                line,
                re.IGNORECASE
            )
            if date_match:
                current_date_str = self._normalize_date_token(date_match.group(1))
                logger.debug(f"Found date: {current_date_str}")

            # Check if this line has amounts (is a transaction line)
            if amount_match := amount_line_pattern.search(line):
                # This line has amounts - it's a transaction line
                # Look backwards to collect description lines
                description_lines = []

                # Look backwards for description (up to 5 lines)
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
                    desc_line = re.sub(r'^\s*\d{1,2}/\d{1,2}/\d{4}\s*|^\s*\d{1,2}\s+[A-Z]{3}(?:\s+\d{2,4})?\s*', '', prev_line, flags=re.IGNORECASE).strip()
                    if desc_line:
                        description_lines.insert(0, desc_line)

                # Combine description lines
                full_description = ' '.join(description_lines) if description_lines else ''

                # Parse the transaction
                try:
                    transaction = self._parse_natwest_transaction(
                        line=line,
                        description=full_description,
                        date_str=current_date_str,
                        statement_start_date=statement_start_date,
                        statement_end_date=statement_end_date,
                        paid_in_threshold=PAID_IN_THRESHOLD,
                        withdrawn_threshold=WITHDRAWN_THRESHOLD
                    )

                    if transaction:
                        # Skip balance validation for BROUGHT FORWARD transactions
                        is_current_bf = 'BROUGHT FORWARD' in transaction.description.upper()

                        # Reset balance recalculation flag at new BROUGHT FORWARD
                        if is_current_bf:
                            recalculate_balances = False

                        # NatWest PDF quirk: Recalculate balances if cascading errors detected
                        if recalculate_balances and len(transactions) > 0 and not is_current_bf:
                            prev_balance = transactions[-1].balance
                            calculated_balance = prev_balance + transaction.money_in - transaction.money_out
                            if abs(transaction.balance - calculated_balance) > 0.01:
                                logger.debug(f"Recalculating balance for {transaction.description[:40]}")
                                transaction.balance = calculated_balance

                        # BALANCE VALIDATION: Auto-correct money_in/money_out direction
                        # Note: Changed from 'balance > 0' to 'balance is not None' to handle zero/OD balances
                        if transaction.balance is not None and len(transactions) > 0 and not is_current_bf:
                            prev_transaction = transactions[-1]
                            prev_balance = prev_transaction.balance
                            balance_change = transaction.balance - prev_balance
                            calculated_change = transaction.money_in - transaction.money_out

                            # Check for BROUGHT FORWARD quirk
                            is_brought_forward = ((prev_transaction.money_in == 0 or prev_transaction.money_in is None) and
                                                (prev_transaction.money_out == 0 or prev_transaction.money_out is None) and
                                                'BROUGHT FORWARD' in prev_transaction.description.upper())

                            if is_brought_forward and abs(balance_change) < 0.01 and (transaction.money_in > 0 or transaction.money_out > 0):
                                # First transaction after BF with balance showing BF amount
                                corrected_balance = prev_balance + transaction.money_in - transaction.money_out
                                logger.info(f"NatWest BF quirk detected. Correcting balance for {transaction.description[:30]}")
                                transaction.balance = corrected_balance
                                balance_change = corrected_balance - prev_balance
                                calculated_change = transaction.money_in - transaction.money_out
                                recalculate_balances = True

                            # If calculated change doesn't match actual balance change, swap direction
                            if abs(calculated_change - balance_change) > 0.01:
                                logger.debug(f"Swapping direction for {transaction.description[:30]}")
                                transaction.money_in, transaction.money_out = transaction.money_out, transaction.money_in

                                # If it STILL doesn't match, the PDF balance itself is wrong
                                calculated_change_after_swap = transaction.money_in - transaction.money_out
                                if abs(calculated_change_after_swap - balance_change) > 0.01:
                                    corrected_balance = prev_balance + transaction.money_in - transaction.money_out
                                    logger.debug(f"Correcting balance from {transaction.balance:.2f} to {corrected_balance:.2f}")
                                    transaction.balance = corrected_balance

                        transactions.append(transaction)
                        logger.debug(f"Parsed: {transaction.date} {transaction.description[:30]}")

                except Exception as e:
                    logger.warning(f"Failed to parse transaction on line {idx}: {e}")

            idx += 1

        logger.info(f"Successfully parsed {len(transactions)} NatWest transactions")
        return transactions

    def _parse_format_b(
        self,
        lines: List[str],
        start_idx: int,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse NatWest Format B (with Type column).

        Format B structure:
        - Date on left (applies to multiple transactions)
        - Type in middle-left (e.g., "DEBIT CARD TRANSACTION", "AUTOMATED CREDIT")
        - Description spans multiple lines
        - Amounts on far right (Paid in, Paid out, Balance)

        Similar to HSBC format.
        """
        transactions = []
        current_date = None
        current_type = None
        description_lines = []

        # Patterns
        # Note: Allow leading whitespace for dates
        date_pattern = re.compile(r'^\s*(\d{1,2}\s+\w+\s+\d{2,4})\s+')
        # Amount pattern: optionally captures minus sign for overdraft balances (e.g., £-450.51)
        amount_pattern = re.compile(r'(-?[\d,]+\.\d{2})')
        header_pattern = re.compile(r'Date\s+Type\s+Description.*Paid\s+in.*Paid\s+out.*Balance', re.IGNORECASE)

        # Type pattern - known types from the format
        # Supports both long names and short codes (POS, BAC, D/D, C/L, etc.)
        type_pattern = re.compile(
            r'^\s{10,30}(DEBIT CARD TRANSACTION|AUTOMATED CREDIT|ATM TRANSACTION|DIRECT DEBIT|STANDING ORDER|FASTER PAYMENT|POS|BAC|D/D|C/L|FP|SO|ATM)',
            re.IGNORECASE
        )

        # Column thresholds (will be updated from header)
        PAID_IN_THRESHOLD = 128  # Midpoint between 118 and 139
        PAID_OUT_THRESHOLD = 151  # Midpoint between 139 and 163

        # Pre-scan to find header and set column thresholds
        for i in range(max(0, start_idx - 5), min(start_idx + 5, len(lines))):
            line = lines[i]
            if header_pattern.search(line):
                paid_in_match = re.search(r'Paid\s+in', line, re.IGNORECASE)
                paid_out_match = re.search(r'Paid\s+out', line, re.IGNORECASE)
                balance_match = re.search(r'Balance', line, re.IGNORECASE)

                if paid_in_match and paid_out_match and balance_match:
                    PAID_IN_THRESHOLD = (paid_in_match.start() + paid_out_match.start()) // 2
                    PAID_OUT_THRESHOLD = (paid_out_match.start() + balance_match.start()) // 2
                    logger.debug(f"Format B thresholds from header at line {i}: Paid In={PAID_IN_THRESHOLD}, Paid Out={PAID_OUT_THRESHOLD}")
                    break

        idx = start_idx
        while idx < len(lines):
            line = lines[idx]

            # Skip blank lines
            if not line.strip():
                idx += 1
                continue

            # Skip footers
            if re.search(r'National Westminster Bank|Registered|Authorised|downloaded from', line, re.IGNORECASE):
                idx += 1
                continue

            # Update column thresholds if we hit a header
            if header_pattern.search(line):
                paid_in_match = re.search(r'Paid\s+in', line, re.IGNORECASE)
                paid_out_match = re.search(r'Paid\s+out', line, re.IGNORECASE)
                balance_match = re.search(r'Balance', line, re.IGNORECASE)

                if paid_in_match and paid_out_match and balance_match:
                    PAID_IN_THRESHOLD = (paid_in_match.start() + paid_out_match.start()) // 2
                    PAID_OUT_THRESHOLD = (paid_out_match.start() + balance_match.start()) // 2
                    print(f"[DEBUG] Updated Format B thresholds: PAID_IN={PAID_IN_THRESHOLD}, PAID_OUT={PAID_OUT_THRESHOLD}")
                    logger.debug(f"Format B thresholds: Paid In={PAID_IN_THRESHOLD}, Paid Out={PAID_OUT_THRESHOLD}")

                idx += 1
                continue

            # Check for date
            date_match = date_pattern.match(line)
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

            # Check for type
            type_match = type_pattern.match(line)
            if type_match:
                current_type = type_match.group(1)
                logger.debug(f"Found type: {current_type}")

            # Check if line has amounts (indicates transaction line)
            amounts_with_pos = []
            # Use Paid In column start minus a buffer as minimum position
            # Need to allow for amounts slightly left of the threshold due to PDF alignment
            MIN_AMOUNT_POSITION = max(PAID_IN_THRESHOLD - 15, 60)  # Amounts in description are before this position
            for match in amount_pattern.finditer(line):
                amt_str = match.group(1)
                pos = match.start()
                if pos >= MIN_AMOUNT_POSITION:
                    amounts_with_pos.append((amt_str, pos))
                else:
                    logger.debug(f"Ignoring amount {amt_str} at position {pos} - likely in description")

            if amounts_with_pos and current_date:
                # This line completes a transaction
                # Extract description part (everything before first amount)
                first_amount_pos = amounts_with_pos[0][1]
                desc_part = line[:first_amount_pos].strip()

                # Remove date and type from description
                desc_part = re.sub(r'^\d{1,2}\s+\w+\s+\d{2,4}\s*', '', desc_part)
                desc_part = re.sub(r'^\s*(DEBIT CARD TRANSACTION|AUTOMATED CREDIT|ATM TRANSACTION|DIRECT DEBIT|STANDING ORDER|FASTER PAYMENT)\s*', '', desc_part, flags=re.IGNORECASE)

                if desc_part:
                    description_lines.append(desc_part)

                full_description = ' '.join(description_lines).strip()

                # Parse amounts by count (more reliable than position due to PDF alignment issues)
                # Typical patterns:
                # - 2 amounts: [paid_out, balance] or [paid_in, balance]
                # - 3 amounts: [paid_in, paid_out, balance]
                money_in = 0.0
                money_out = 0.0
                balance = None

                num_amounts = len(amounts_with_pos)

                if num_amounts == 1:
                    # Only one amount - must be balance
                    amt_val = parse_currency(amounts_with_pos[0][0]) or 0.0
                    balance = amt_val
                elif num_amounts == 2:
                    # Two amounts - last is always balance, first is paid in or paid out
                    # Use '-' character to determine which column is empty
                    first_amt_str, first_pos = amounts_with_pos[0]
                    second_amt_str, second_pos = amounts_with_pos[1]

                    first_val = abs(parse_currency(first_amt_str) or 0.0)
                    balance = parse_currency(second_amt_str) or 0.0

                    # Check where the '-' dash is relative to the first amount
                    # Pattern 1: "- £amount1 £amount2" → dash before first amount → amount1 is Money Out
                    # Pattern 2: "£amount1 - £amount2" → dash after first amount → amount1 is Money In

                    # Look for standalone dash before first amount
                    # Check if there's a dash in the column area (position > 60) before the first amount
                    # This avoids matching dashes in descriptions (which are typically before position 60)
                    text_before_first = line[:first_pos]

                    # Find the last dash before the first amount
                    dash_matches = list(re.finditer(r'\s-\s', text_before_first))
                    if dash_matches:
                        last_dash = dash_matches[-1]
                        # Check if this dash is in the column area (position > 55)
                        dash_before = last_dash.start() > 55
                    else:
                        dash_before = False

                    if dash_before:
                        # Dash is BEFORE first amount → Paid In is empty → first amount is Money Out
                        money_out = first_val
                    else:
                        # Dash must be AFTER first amount (between amounts) → Paid Out is empty → first amount is Money In
                        money_in = first_val
                elif num_amounts >= 3:
                    # Three or more amounts: first is paid in, second is paid out, last is balance
                    money_in = abs(parse_currency(amounts_with_pos[0][0]) or 0.0)
                    money_out = abs(parse_currency(amounts_with_pos[1][0]) or 0.0)
                    balance = parse_currency(amounts_with_pos[-1][0]) or 0.0

                # If no balance, calculate from previous
                if balance is None and transactions:
                    prev_balance = transactions[-1].balance
                    balance = prev_balance + money_in - money_out

                # Create transaction
                if current_date and balance is not None:
                    transaction_type = self._detect_transaction_type(full_description) or current_type

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
                    logger.debug(f"Parsed: {current_date} {full_description[:30]} In:£{money_in:.2f} Out:£{money_out:.2f} Bal:£{balance:.2f}")

                # Reset for next transaction
                description_lines = []
                current_type = None

                idx += 1
                continue

            # Otherwise, this is a description continuation line
            if line.strip() and not type_match:
                description_lines.append(line.strip())

            idx += 1

        # Check if transactions are in reverse chronological order (newest first)
        # Some NatWest Format B statements (like online statements) are in reverse order
        if len(transactions) >= 2:
            first_date = transactions[0].date
            last_date = transactions[-1].date
            if first_date > last_date:
                logger.info(f"Transactions are in reverse chronological order - reversing to chronological order")
                transactions.reverse()

        logger.info(f"Successfully parsed {len(transactions)} NatWest Format B transactions")
        return transactions

    def _find_natwest_header(self, lines: List[str]) -> Optional[int]:
        """Find the NatWest transaction table header."""
        header_pattern = re.compile(
            r'Date\s+(?:Type\s+)?(Description|Details).*(Paid\s+[Ii]n.*(Withdrawn|Paid\s+out)|Withdrawn.*Paid\s+[Ii]n).*Balance',
            re.IGNORECASE
        )

        for idx, line in enumerate(lines):
            if header_pattern.search(line):
                return idx

        return None

    def _parse_natwest_transaction(
        self,
        line: str,
        description: str,
        date_str: Optional[str],
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime],
        paid_in_threshold: int,
        withdrawn_threshold: int
    ) -> Optional[Transaction]:
        """
        Parse NatWest transaction from line with amounts.

        Args:
            line: Line containing amounts
            description: Combined description from previous lines
            date_str: Date string (if found)
            statement_start_date: Statement period start
            statement_end_date: Statement period end
            paid_in_threshold: Column threshold for paid in
            withdrawn_threshold: Column threshold for withdrawn

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
            date_for_inference = self._apply_leap_year_hint(date_str, statement_start_date, statement_end_date)
            transaction_date = infer_year_from_period(
                date_for_inference,
                statement_start_date,
                statement_end_date
            )
        else:
            transaction_date = parse_date(date_str, self.config.date_formats)

        if not transaction_date:
            logger.warning(f"Could not parse date: {date_str}")
            return None

        # Build full description
        if not description:
            description = line[:line.find(amount_matches[0])].strip()

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

            # Classify using column position
            amount_pos = line.find(amount_matches[0])
            if amount_pos <= withdrawn_threshold:
                money_out = transaction_amount
            else:
                money_in = transaction_amount
        else:
            # More than 2 amounts (e.g., foreign currency with exchange rate and fees)
            # Pattern: "USD 20.00 VRATE 1.2730 N-S TRN FEE 0.43    16.14    42,193.81"
            # Last amount = balance, second-to-last = transaction amount
            if self._is_forex_or_fee_line(line):
                logger.debug(f"Handling FX/fee line with {len(amount_matches)} amounts: {line[:80]}")
            else:
                logger.warning(f"Found {len(amount_matches)} amounts, expected 1 or 2: {line[:80]}")
            balance = parse_currency(amount_matches[-1]) or 0.0
            transaction_amount = parse_currency(amount_matches[-2]) or 0.0

            # Classify the transaction amount using column position
            amount_pos = line.find(amount_matches[-2])
            if amount_pos <= withdrawn_threshold:
                money_out = transaction_amount
            else:
                money_in = transaction_amount

        if 'N-S TRN FEE' in line.upper() and 'N-S TRN FEE' not in description.upper():
            description = f"{description} N-S TRN FEE".strip()

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

        return Transaction(
            date=transaction_date,
            description=description,
            money_in=money_in,
            money_out=money_out,
            balance=balance,
            transaction_type=transaction_type,
            confidence=confidence,
            raw_text=line[:100]
        )

    @staticmethod
    def _normalize_date_token(token: str) -> str:
        """Normalize compact NatWest date tokens like 21FEB24 or 29 FEB."""
        if not token:
            return token
        compact = re.match(r'^(\d{1,2})([A-Z]{3})(\d{2,4})?$', token.strip(), re.IGNORECASE)
        if compact:
            parts = [compact.group(1), compact.group(2)]
            if compact.group(3):
                parts.append(compact.group(3))
            token = ' '.join(parts)
        return token.title()

    @staticmethod
    def _is_forex_or_fee_line(line: str) -> bool:
        """Heuristically detect FX rate / non-sterling fee rows with extra numbers."""
        if not line:
            return False
        keywords = ['N-S TRN FEE', 'VRATE', 'NON STERLING', 'FX RATE', 'CASH BACK', 'XFER']
        upper_line = line.upper()
        return any(keyword in upper_line for keyword in keywords)

    @staticmethod
    def _apply_leap_year_hint(date_str: str, period_start: datetime, period_end: datetime) -> str:
        """Append a leap-year hint for bare '29 FEB' dates to avoid parse warnings."""
        if not date_str or re.search(r'\d{4}', date_str):
            return date_str
        compact = re.match(r'^\s*(\d{1,2})\s+([A-Z]{3})\s*$', date_str.upper())
        if not compact:
            return date_str
        day = int(compact.group(1))
        month = compact.group(2)
        if day != 29 or month != 'FEB':
            return date_str
        for year in {period_start.year, period_end.year}:
            if calendar.isleap(year):
                return f"{day:02d} Feb {year}"
        return date_str
