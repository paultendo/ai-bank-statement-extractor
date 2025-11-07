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

        # Column thresholds will be detected from header (if found)
        # Default thresholds as fallback (based on older Nationwide format)
        MONEY_OUT_THRESHOLD = 104
        MONEY_IN_THRESHOLD = 123

        # Try to detect column positions from header
        if header_line_idx is not None:
            header_line = lines[header_line_idx]
            money_out_match = re.search(r'£\s*Out', header_line, re.IGNORECASE)
            money_in_match = re.search(r'£\s*In', header_line, re.IGNORECASE)
            balance_match = re.search(r'£\s*Balance', header_line, re.IGNORECASE)

            if money_out_match and money_in_match and balance_match:
                # For right-aligned amounts, threshold is at the start of the next column
                # Amounts ending before Money In column start are in Money Out
                # Amounts ending before Balance column start are in Money In
                MONEY_OUT_THRESHOLD = money_in_match.start() - 1
                MONEY_IN_THRESHOLD = balance_match.start() - 1
                logger.info(f"Detected Nationwide column thresholds from header: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")
            else:
                logger.info(f"Using default Nationwide thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")
        else:
            logger.info(f"No header found, using default thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")

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
            header_pattern_inline = re.compile(
                r'Date\s+Description.*£\s*Out.*£\s*In.*£\s*Balance',
                re.IGNORECASE
            )
            if header_pattern_inline.search(line):
                money_out_match = re.search(r'£\s*Out', line, re.IGNORECASE)
                money_in_match = re.search(r'£\s*In', line, re.IGNORECASE)
                balance_match = re.search(r'£\s*Balance', line, re.IGNORECASE)

                if money_out_match and money_in_match and balance_match:
                    MONEY_OUT_THRESHOLD = money_in_match.start() - 1
                    MONEY_IN_THRESHOLD = balance_match.start() - 1
                    logger.debug(f"Updated Nationwide thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")

                idx += 1
                continue

            # Skip footer lines, informational text, and page boundaries
            skip_patterns = [
                r'Nationwide Building Society',
                r'Prudential Regulation',
                r'Head Office',
                r'Please check',
                r'Interest, Rates and Fees',
                r'Summary box',
                r'Credit interest',
                r'Arranged overdraft',
                r'AER stands for',
                r'Have you lost your card',
                r'As an example',
                r'For the.*example',
                r'incurred up to',
                r'withdrawal in a',
                r'us as a sterling',
                r'Non-Sterling Transaction',
                r'Page \d+ of \d+',
                r'Continued on next page',
                r'Financial Conduct Authority',
                r'Financial Services Compensation',
                r'is higher as we charge interest',  # Info box text that was parsed as transaction
                r'^\s*TOTALS\s*$',  # Summary totals line
                r'Statement no:',
                r'Statement date:',
                r'Sort code',
                r'Account no',
                r'FlexAccount',
                r'Your.*transactions',
                r'Registered Office',
                r'Balance from statement \d+',  # Already handled separately
            ]
            if any(re.search(pattern, line, re.IGNORECASE) for pattern in skip_patterns):
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
