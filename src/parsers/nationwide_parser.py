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

        # Extract year from statement date or first transaction
        year = statement_end_date.year if statement_end_date else datetime.now().year

        # Define column names for detection
        column_names = ["£ Out", "£ In", "£ Balance"]
        column_pairs = [("£ Out", "£ In"), ("£ In", "£ Balance")]

        # Default thresholds based on typical Nationwide layout
        # Columns are right-aligned, so amounts appear at the END of each column
        # £ Out column: 57-105 (amounts around 70-90)
        # £ In column: 106-123 (amounts around 105-120)
        # £ Balance column: 124+ (amounts around 130-140)
        default_thresholds = {
            '£_out_threshold': 104,     # Just before £ In column starts
            '£_in_threshold': 123       # End of £ In column
        }

        # Use manual thresholds for Nationwide (amounts are right-aligned)
        # The pre_scan calculates midpoints which don't work for right-aligned columns
        thresholds = default_thresholds
        logger.info(f"Using column thresholds: {thresholds}")

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

            # Skip footer lines and informational text
            if re.search(r'Nationwide Building Society|Prudential Regulation|Head Office|Please check|Interest, Rates and Fees|Summary box|Credit interest|Arranged overdraft|AER stands for|Have you lost your card|As an example|For the.*example|incurred up to|withdrawal in a|us as a sterling|Non-Sterling Transaction', line, re.IGNORECASE):
                idx += 1
                continue

            # Check if this is a new date line
            date_match = date_pattern.match(line)

            if date_match:
                # This is a new date line - extract date
                date_str = date_match.group(1)

                # Parse date
                try:
                    current_date = parse_date(f"{date_str} {year}", self.config.date_formats)
                except:
                    current_date = None

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

                # Parse amounts by position using dynamic thresholds
                money_out = 0.0
                money_in = 0.0
                balance = None

                # Define column order for classification
                column_order = ['£_out', '£_in', '£_balance']

                for amt_str, pos in amounts_with_pos:
                    amt_val = parse_currency(amt_str) or 0.0

                    # Classify using dynamic column detection
                    column = classify_amount_by_position(pos, thresholds, column_order)

                    if column == '£_out':
                        money_out = abs(amt_val)
                    elif column == '£_in':
                        money_in = abs(amt_val)
                    else:  # £_balance
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
