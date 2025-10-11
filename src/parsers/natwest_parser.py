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
        header_pattern = re.compile(r'Date\s+(Description|Details).*(Paid In.*Withdrawn|Withdrawn.*Paid In).*Balance', re.IGNORECASE)

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
                    # Handle both column orders
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
            date_match = re.match(r'^\s*(\d{1,2}/\d{1,2}/\d{4}|\d{1,2}\s+[A-Z]{3}(?:\s+\d{2,4})?)', line, re.IGNORECASE)
            if date_match:
                current_date_str = date_match.group(1)
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
                        if transaction.balance > 0 and len(transactions) > 0 and not is_current_bf:
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

    def _find_natwest_header(self, lines: List[str]) -> Optional[int]:
        """Find the NatWest transaction table header."""
        header_pattern = re.compile(r'Date\s+(Description|Details).*(Paid In.*Withdrawn|Withdrawn.*Paid In).*Balance', re.IGNORECASE)

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
            logger.warning(f"Found {len(amount_matches)} amounts, expected 1 or 2: {line[:80]}")
            balance = parse_currency(amount_matches[-1]) or 0.0
            transaction_amount = parse_currency(amount_matches[-2]) or 0.0

            # Classify the transaction amount using column position
            amount_pos = line.find(amount_matches[-2])
            if amount_pos <= withdrawn_threshold:
                money_out = transaction_amount
            else:
                money_in = transaction_amount

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
