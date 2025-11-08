"""Nationwide Building Society bank statement parser.

Handles Nationwide FlexAccount statements with format:
Date | Description | £ Out | £ In | £ Balance
"""

import logging
import re
from datetime import datetime
from typing import Optional, List

from .base_parser import BaseTransactionParser
from ..models import Transaction
from ..utils import parse_currency, parse_date, infer_year_from_period, classify_amount_by_position, pre_scan_for_thresholds

logger = logging.getLogger(__name__)


class NationwideParser(BaseTransactionParser):
    """Parser for Nationwide Building Society statements."""

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse Nationwide statement text.

        Format:
        Date        Description                               £ Out                £ In              £ Balance
        15 Jan      Payment to TONI MORRIS                     4.00
                    Transfer to 070246 20902348               30.00
                    Payment to TONI MORRIS                     5.00                                      0.50

        Args:
            text: Extracted text
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of parsed transactions
        """
        lines = text.split('\n')
        transactions = []

        logger.info(f"Parsing Nationwide statement: {len(lines)} lines")

        # Find the header line to determine column positions
        header_line_idx = self._find_header(lines)
        if header_line_idx is None:
            logger.warning("Could not find transaction table header")
            start_idx = 0
        else:
            start_idx = header_line_idx + 1
            header_line = lines[header_line_idx]
            logger.info(f"Found header at line {header_line_idx}: {header_line[:80]}")

        # Pattern to match date lines (starts with day + month)
        date_pattern = re.compile(r'^\s*(\d{1,2}\s+[A-Z][a-z]{2})\s+(.*)$')

        # Pattern to match amounts
        amount_pattern = re.compile(r'([\d,]+\.\d{2})')

        # Detect column thresholds from header (Nationwide uses right-aligned amounts)
        # For right-aligned amounts, threshold is right_column.start() - 1
        # Amounts ending before the threshold belong to the left column
        thresholds = self._detect_column_thresholds(
            lines,
            column_names=["£ Out", "£ In", "£ Balance"],
            column_pairs=[("£ Out", "£ In"), ("£ In", "£ Balance")],
            default_thresholds={'£_out_threshold': 104, '£_in_threshold': 123},
            use_right_aligned=True
        )

        # Extract thresholds with more standard naming
        MONEY_OUT_THRESHOLD = thresholds.get('£_out_threshold', 104)
        MONEY_IN_THRESHOLD = thresholds.get('£_in_threshold', 123)
        logger.info(f"Nationwide column thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")

        # The info box on the right starts around position 150
        # We need to filter out amounts from the info box
        INFO_BOX_START = 150

        current_date = None

        idx = start_idx
        while idx < len(lines):
            line = lines[idx]

            # Skip blank lines
            if not line.strip():
                idx += 1
                continue

            # Check for header on new page (update thresholds if found)
            # Header pattern: "Date Description ... £ Out ... £ In ... £ Balance"
            if re.search(r'Date\s+Description.*£\s*Out.*£\s*In.*£\s*Balance', line, re.IGNORECASE):
                updated = self._update_column_thresholds_from_header(
                    line,
                    column_names=["£ Out", "£ In", "£ Balance"],
                    column_pairs=[("£ Out", "£ In"), ("£ In", "£ Balance")],
                    use_right_aligned=True
                )
                if updated:
                    MONEY_OUT_THRESHOLD = updated.get('£_out_threshold', MONEY_OUT_THRESHOLD)
                    MONEY_IN_THRESHOLD = updated.get('£_in_threshold', MONEY_IN_THRESHOLD)
                    logger.debug(f"Updated Nationwide thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")

                idx += 1
                continue

            # Skip footers, headers, and other non-transaction lines
            # Uses shared skip patterns plus Nationwide-specific ones from config
            if self._is_skip_line(line):
                idx += 1
                continue

            # Check if this is a new date line
            date_match = date_pattern.match(line)

            if date_match:
                # This is a new date line - extract date
                date_str = date_match.group(1)

                # Parse date using infer_year_from_period for multi-month statements
                if statement_start_date and statement_end_date:
                    current_date = infer_year_from_period(
                        date_str,
                        statement_start_date,
                        statement_end_date,
                        date_formats=self.config.date_formats
                    )
                else:
                    current_date = parse_date(date_str, self.config.date_formats)

                if current_date:
                    logger.debug(f"Found date: {current_date.date()} from '{date_str}'")

            # Check if this line has amounts (each line with amounts = 1 transaction)
            amounts = amount_pattern.findall(line)

            if amounts and current_date:
                # Extract description (before position 57 where amounts start)
                desc_part = line[:57].strip()

                # Clean info box keywords from description
                info_box_keywords = [
                    'Average credit', 'Average debit', 'balance',
                    'Receiving an', 'International Payment', 'BIC', 'IBAN',
                    'Swift', 'Intermediary Bank', 'NAIAGB21', 'GB34 NAIA',
                    'MIDLGB22', '£115.04', '£0.00'
                ]
                for keyword in info_box_keywords:
                    desc_part = re.sub(keyword, '', desc_part, flags=re.IGNORECASE)

                # Clean up extra whitespace
                description = ' '.join(desc_part.split()).strip()

                # Skip the "Balance from statement" line
                if "Balance from statement" in description:
                    idx += 1
                    continue

                # Find amounts with their positions (excluding info box)
                amounts_with_pos = []
                for match in amount_pattern.finditer(line):
                    amt_str = match.group(1)
                    pos = match.start()
                    # Skip amounts in the info box (right side)
                    if pos < INFO_BOX_START:
                        amounts_with_pos.append((amt_str, pos))

                # Parse amounts by position using detected thresholds
                money_out = 0.0
                money_in = 0.0
                balance = None

                for amt_str, pos in amounts_with_pos:
                    amt_val = parse_currency(amt_str) or 0.0

                    # Classify by position (amounts are right-aligned, so we check where they END)
                    amt_end_pos = pos + len(amt_str)

                    if amt_end_pos <= MONEY_OUT_THRESHOLD:
                        money_out = abs(amt_val)
                    elif amt_end_pos <= MONEY_IN_THRESHOLD:
                        money_in = abs(amt_val)
                    else:
                        balance = amt_val

                # Detect transaction type
                transaction_type = self._detect_transaction_type(description)

                # Calculate confidence (balance can be None for intermediate transactions)
                confidence = self._calculate_confidence(
                    date=current_date,
                    description=description,
                    money_in=money_in,
                    money_out=money_out,
                    balance=balance
                ) if balance is not None else 85.0  # Default confidence for transactions without balance

                # Create transaction
                transaction = Transaction(
                    date=current_date,
                    description=description,
                    money_in=money_in,
                    money_out=money_out,
                    balance=balance,
                    transaction_type=transaction_type,
                    confidence=confidence,
                    raw_text=line[:100]
                )

                transactions.append(transaction)
                logger.debug(f"Parsed: {current_date.date()} {description[:40]} In:£{money_in:.2f} Out:£{money_out:.2f} Bal:{balance if balance is not None else 'N/A'}")

            idx += 1

        logger.info(f"Successfully parsed {len(transactions)} Nationwide transactions")
        return transactions

    def _find_header(self, lines: List[str]) -> Optional[int]:
        """Find the transaction table header line."""
        header_pattern = re.compile(
            r'Date\s+Description.*£\s*Out.*£\s*In.*£\s*Balance',
            re.IGNORECASE
        )

        for idx, line in enumerate(lines):
            if header_pattern.search(line):
                return idx

        return None
