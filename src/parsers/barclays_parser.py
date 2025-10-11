"""Barclays bank statement parser.

Handles Barclays-specific statement format with multi-line transactions
and transaction boundary detection via indentation patterns.

Format characteristics:
- Multiple transactions can share same date
- Descriptions span multiple lines
- Balance only appears on LAST line of transaction
- "Start balance" has no amounts (skipped)
- Transaction start detected by 10+ space indentation
- Date pattern excludes addresses like "5 SWEDEN PLACE"
- Column layout: Date | Description | Money out | Money in | Balance
- Rightmost amount is ALWAYS balance
"""

import logging
import re
from datetime import datetime
from typing import Optional, List

from .base_parser import BaseTransactionParser
from ..models import Transaction
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)


class BarclaysParser(BaseTransactionParser):
    """Parser for Barclays bank statements."""

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse Barclays statement using layout-based extraction.

        Barclays format:
        - Date column (0-12)
        - Description column (13-65) - MULTI-LINE
        - Money out column (65-85)
        - Money in column (85-105)
        - Balance column (105-125)

        Key characteristics:
        - Multiple transactions can share same date
        - Descriptions span multiple lines
        - Balance only appears on LAST line of transaction
        - "Start balance" has no amounts

        Args:
            text: Raw text from pdftotext
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of Transaction objects
        """
        lines = text.split('\n')
        transactions = []

        # Header pattern
        header_pattern = re.compile(r'Date\s+Description\s+Money out\s+Money in\s+Balance', re.IGNORECASE)

        # Find header to get column positions
        header_line_idx = None
        for idx, line in enumerate(lines):
            if header_pattern.search(line):
                header_line_idx = idx
                logger.debug(f"Found Barclays header at line {idx}")
                break

        if header_line_idx is None:
            logger.warning("Could not find Barclays transaction table header")
            return transactions

        # Extract column positions from header
        header_line = lines[header_line_idx]
        money_out_match = re.search(r'Money out', header_line)
        money_in_match = re.search(r'Money in', header_line)
        balance_match = re.search(r'Balance', header_line)

        if not (money_out_match and money_in_match and balance_match):
            logger.warning("Could not determine Barclays column positions")
            return transactions

        money_out_start = money_out_match.start()
        money_in_start = money_in_match.start()
        balance_start = balance_match.start()

        # Calculate thresholds (midpoints between columns)
        # NOTE: Amounts are right-aligned, so we need to account for this
        # Use midpoint as threshold, but check amount START position (not end)
        MONEY_OUT_THRESHOLD = (money_out_start + money_in_start) // 2
        MONEY_IN_THRESHOLD = (money_in_start + balance_start) // 2

        logger.info(f"Barclays column thresholds: money_out={MONEY_OUT_THRESHOLD}, money_in={MONEY_IN_THRESHOLD}")

        # Date pattern: "DD MMM" or "DD MMM YYYY" at start of line
        # This prevents matching addresses like "5 SWEDEN PLACE"
        date_pattern = re.compile(r'^(\d{1,2}\s+[A-Z][a-z]{2}(?:\s+\d{4})?)(?:\s|$)', re.IGNORECASE)

        # Amount pattern: decimal number with optional commas
        amount_pattern = re.compile(r'([\d,]+\.\d{2})')

        # Transaction start pattern: description starting around column 13
        # Typical: "             Card Payment to..." or "             Direct Debit to..."
        transaction_start_pattern = re.compile(
            r'^\s{10,}(Card Payment|Direct Debit|Bill Payment|Received From|Standing Order|Cash machine|Automated Payment|Card Purchase)',
            re.IGNORECASE
        )

        # Process lines after header
        current_date_str = None
        current_description_lines = []
        current_transaction_amounts = []  # Store (position, amount) tuples

        for idx in range(header_line_idx + 1, len(lines)):
            line = lines[idx]

            # Skip empty lines
            if not line.strip():
                continue

            # Skip summary section "Start balance" lines (these don't have dates at the start)
            # e.g., "    IP27 0LU                                                                                                                Start balance             £512.97"
            if "Start balance" in line and not re.match(r'^\d{1,2}\s+[A-Z][a-z]{2}', line):
                continue

            # Check if this line has a date
            date_match = date_pattern.match(line)

            # Check if this is the start of a new transaction description
            is_transaction_start = transaction_start_pattern.search(line)

            # Check if this line has amounts
            # IMPORTANT: Ignore amounts in description text (position < 50)
            # E.g., "National Lottery I 10.00 On 12 Dec" has 10.00 in description
            amounts_with_pos = []
            MIN_AMOUNT_POSITION = 50
            for match in amount_pattern.finditer(line):
                amt_str = match.group(1)
                pos = match.start()
                if pos >= MIN_AMOUNT_POSITION:
                    amounts_with_pos.append((amt_str, pos))
                else:
                    logger.debug(f"Ignoring amount {amt_str} at position {pos} (< {MIN_AMOUNT_POSITION}) - likely description text")

            # If we see a new transaction description starting, complete the previous one
            if is_transaction_start and current_description_lines:
                # Save previous transaction
                transaction = self._build_barclays_transaction(
                    current_date_str,
                    current_description_lines,
                    current_transaction_amounts,
                    MONEY_OUT_THRESHOLD,
                    MONEY_IN_THRESHOLD,
                    statement_start_date,
                    statement_end_date
                )
                if transaction:
                    transactions.append(transaction)

                # Start new transaction (keep same date)
                current_description_lines = [line]
                current_transaction_amounts = amounts_with_pos

            # If we have a date, start a new transaction group
            elif date_match:
                # Save previous transaction if any
                if current_description_lines and current_transaction_amounts:
                    transaction = self._build_barclays_transaction(
                        current_date_str,
                        current_description_lines,
                        current_transaction_amounts,
                        MONEY_OUT_THRESHOLD,
                        MONEY_IN_THRESHOLD,
                        statement_start_date,
                        statement_end_date
                    )
                    if transaction:
                        transactions.append(transaction)

                # Start new transaction
                current_date_str = date_match.group(1)
                current_description_lines = [line]
                current_transaction_amounts = amounts_with_pos

            # Otherwise, accumulate description lines (e.g., "On 11 Dec" continuation lines)
            else:
                if current_date_str:
                    current_description_lines.append(line)
                    current_transaction_amounts.extend(amounts_with_pos)

        # Handle final transaction
        if current_description_lines and current_transaction_amounts:
            transaction = self._build_barclays_transaction(
                current_date_str,
                current_description_lines,
                current_transaction_amounts,
                MONEY_OUT_THRESHOLD,
                MONEY_IN_THRESHOLD,
                statement_start_date,
                statement_end_date
            )
            if transaction:
                transactions.append(transaction)

        logger.info(f"Parsed {len(transactions)} Barclays transactions")

        # Post-process: Calculate running balances
        # Barclays only shows balance on LAST transaction per date group
        # Need to backfill balances for intermediate transactions
        transactions = self._calculate_running_balances(transactions)

        return transactions

    def _calculate_running_balances(self, transactions: List[Transaction]) -> List[Transaction]:
        """
        Calculate running balances for Barclays transactions.

        Barclays only shows balance on the LAST transaction for each date.
        We need to calculate balances for intermediate transactions by working
        backwards from transactions that have balances.

        Args:
            transactions: List of transactions with some missing balances

        Returns:
            List of transactions with all balances calculated
        """
        if not transactions:
            return transactions

        logger.debug("Calculating running balances for Barclays transactions")

        # Work through transactions and calculate missing balances
        for i in range(len(transactions)):
            if transactions[i].balance == 0.0 and i > 0:
                # No balance on this transaction - calculate from previous
                prev_balance = transactions[i - 1].balance
                calculated_balance = prev_balance + transactions[i].money_in - transactions[i].money_out
                transactions[i].balance = calculated_balance
                logger.debug(
                    f"Calculated balance for txn {i+1} ({transactions[i].description[:30]}): "
                    f"£{prev_balance:.2f} + £{transactions[i].money_in:.2f} - "
                    f"£{transactions[i].money_out:.2f} = £{calculated_balance:.2f}"
                )

        return transactions

    def _build_barclays_transaction(
        self,
        date_str: str,
        description_lines: List[str],
        amounts_with_pos: List[tuple],
        money_out_threshold: int,
        money_in_threshold: int,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> Optional[Transaction]:
        """
        Build a Barclays transaction from accumulated lines.

        Args:
            date_str: Date string (e.g., "13 Dec")
            description_lines: List of description lines
            amounts_with_pos: List of (amount_str, position) tuples
            money_out_threshold: Column threshold for money out
            money_in_threshold: Column threshold for money in
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            Transaction object or None
        """
        # Parse date with year inference
        transaction_date = None
        if statement_start_date and statement_end_date:
            transaction_date = infer_year_from_period(
                date_str,
                statement_start_date,
                statement_end_date
            )
        else:
            transaction_date = parse_date(date_str, self.config.date_formats)

        if not transaction_date:
            logger.warning(f"Could not parse Barclays date: {date_str}")
            return None

        # Build description from all lines
        # First, remove amounts from description lines (amounts are captured separately)
        clean_description_lines = []
        amount_pattern_for_removal = re.compile(r'([£]?[\d,]+\.\d{2})')
        for line in description_lines:
            # Remove amounts that appear after position 50 (column amounts, not description text)
            clean_line = line
            for match in amount_pattern_for_removal.finditer(line):
                if match.start() >= 50:
                    # Replace amount with spaces to preserve column structure
                    clean_line = clean_line[:match.start()] + ' ' * len(match.group(0)) + clean_line[match.end():]
            clean_description_lines.append(clean_line)

        full_description = ' '.join(clean_description_lines)
        # Remove date from description
        full_description = re.sub(r'^\s*\d{1,2}\s+[A-Z][a-z]{2}(?:\s+\d{4})?\s*', '', full_description, flags=re.IGNORECASE)
        full_description = ' '.join(full_description.split())  # Normalize whitespace

        # "Start balance" transactions: rename to BROUGHT FORWARD for consistency
        # These mark the start of each statement period (like Halifax/HSBC)
        is_brought_forward = "Start balance" in full_description
        if is_brought_forward:
            full_description = "BROUGHT FORWARD"
            logger.debug(f"Found Start balance (renamed to BROUGHT FORWARD)")

        # Classify amounts by position
        # Strategy: Rightmost amount is ALWAYS balance. Other amounts are transaction amounts.
        money_out = 0.0
        money_in = 0.0
        balance = 0.0

        # Special handling for BROUGHT FORWARD: amount is always the opening balance
        if is_brought_forward and len(amounts_with_pos) == 1:
            amt_str, _ = amounts_with_pos[0]
            balance = parse_currency(amt_str) or 0.0
            money_in = 0.0
            money_out = 0.0
        elif not amounts_with_pos:
            logger.warning(f"No amounts found for Barclays transaction: {full_description[:50]}")
        elif len(amounts_with_pos) == 1:
            # Single amount - determine which column by checking distance to column starts
            amt_str, pos = amounts_with_pos[0]
            amt = parse_currency(amt_str) or 0.0

            # Calculate distances to each column start (amounts are right-aligned)
            # Use the END position of the amount for better accuracy
            amt_end = pos + len(amt_str)

            # Distances from amount END to each column END (approximate)
            # Money out column ends around position 82 (before Money in at 85)
            # Money in column ends around position 102 (before Balance at 105)
            # Balance column ends around position 125
            dist_to_money_out = abs(amt_end - 82)
            dist_to_money_in = abs(amt_end - 102)
            dist_to_balance = abs(amt_end - 125)

            # Classify based on closest column
            min_dist = min(dist_to_money_out, dist_to_money_in, dist_to_balance)

            if min_dist == dist_to_balance:
                balance = amt
            elif min_dist == dist_to_money_in:
                money_in = amt
                balance = 0.0  # Will be calculated later
            else:
                money_out = amt
                balance = 0.0  # Will be calculated later
        else:
            # Multiple amounts: rightmost is balance, others are transaction amounts
            # Sort by position to find rightmost
            sorted_amounts = sorted(amounts_with_pos, key=lambda x: x[1])

            # Rightmost = balance
            balance_str, balance_pos = sorted_amounts[-1]
            balance = parse_currency(balance_str) or 0.0

            # Classify remaining amounts by their column position using distance method
            for amt_str, pos in sorted_amounts[:-1]:
                amt = parse_currency(amt_str) or 0.0
                amt_end = pos + len(amt_str)

                # Calculate distances to column ends
                dist_to_money_out = abs(amt_end - 82)
                dist_to_money_in = abs(amt_end - 102)

                # Classify based on closest column (balance already handled)
                # In case of tie, prefer money_in (as it's to the right)
                if dist_to_money_in <= dist_to_money_out:
                    money_in += amt  # Sum if multiple amounts in same column
                else:
                    money_out += amt

        # Calculate confidence
        confidence = self._calculate_confidence(
            transaction_date,
            full_description,
            money_in,
            money_out,
            balance
        )

        return Transaction(
            date=transaction_date,
            description=full_description,
            money_in=money_in,
            money_out=money_out,
            balance=balance,
            confidence=confidence
        )
