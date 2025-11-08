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

    INFO_BOX_KEYWORDS = [
        "credit interest",
        "average credit",
        "average debit",
        "receiving an",
        "international payment",
        "interest, rates and fees",
        "as an example",
        "non-sterling transaction",
        "non-sterling transaction fee",
        "monthly maximum charge",
        "chaps",
        "sepa",
        "is higher as we charge interest",
        "withdrawal in a",
        "us as a sterling",
        "summary box",
        "have you lost your card",
        "arranged overdraft",
        "notice of charges",
        "start balance",
        "start £",
        "end balance",
        "end £",
        "aer stands for",
        "example",
        "2.99%"
    ]

    INFO_BOX_PREFIXES = [
        "start balance",
        "start £",
        "end balance",
        "end £",
        "(2.99%",
        "balance £"
    ]

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

        header_line_idx = self._find_header(lines)
        if header_line_idx is None:
            logger.warning("Could not find transaction table header - falling back to raw line parsing")
            return self._parse_transactions_from_lines(
                lines,
                statement_start_date,
                statement_end_date
            )

        header_line = lines[header_line_idx]
        start_idx = header_line_idx + 1

        col_desc = header_line.lower().find('description')
        col_out = header_line.lower().find('£ out')
        col_in = header_line.lower().find('£ in')
        col_bal = header_line.lower().find('£ balance')

        # Fallbacks if header parsing fails
        if col_desc == -1:
            col_desc = 12
        if col_out == -1:
            col_out = col_desc + 38
        if col_in == -1:
            col_in = col_out + 22
        if col_bal == -1:
            col_bal = col_in + 20

        date_pattern = re.compile(r'^\s*(\d{1,2}\s+[A-Z][a-z]{2})\s+(.*)$')
        amount_pattern = re.compile(r'([\d,]+\.\d{2})')

        current_date = None
        pending_desc_lines: list[str] = []
        pending_period_marker = False
        pending_period_balance = None

        def _slice(segment_line: str, start: int, end: Optional[int] = None) -> str:
            if start >= len(segment_line):
                return ""
            if end is None or end > len(segment_line):
                end = len(segment_line)
            return segment_line[start:end]

        def _safe_parse_amount(segment: str) -> Optional[float]:
            cleaned = segment.replace('£', '').replace(',', '').strip()
            if not cleaned:
                return None
            if not re.match(r'^-?\d+(\.\d{2})?$', cleaned):
                return None
            return parse_currency(segment)

        idx = start_idx
        while idx < len(lines):
            line = lines[idx]
            line_for_date = re.sub(r'(\d)([A-Za-z])', r'\1 \2', line)
            line_for_date = re.sub(r'([A-Za-z])(\d)', r'\1 \2', line_for_date)
            line_lower = line.lower()

            # Skip blank lines
            if not line.strip():
                idx += 1
                continue

            # Skip page carry-over rows like "2023     20.22"
            if re.match(r'^\s*\d{4}\s+[\d,]+\.\d{2}\s*$', line):
                idx += 1
                continue

            line_stripped = line_lower.strip()
            if any(line_stripped.startswith(prefix) for prefix in self.INFO_BOX_PREFIXES):
                idx += 1
                continue

            if any(keyword in line_lower for keyword in self.INFO_BOX_KEYWORDS):
                has_amounts = bool(amount_pattern.search(line))
                if not re.match(r'^\s*\d{1,2}\s+[A-Z][a-z]{2}', line_for_date) and not has_amounts:
                    idx += 1
                    continue

            compact_line = re.sub(r'\s+', '', line_for_date.lower())
            if 'balancefromstatement' in compact_line:
                amounts = amount_pattern.findall(line)
                pending_period_balance = parse_currency(amounts[0]) if amounts else None
                pending_period_marker = True
                current_date = None
                pending_desc_lines = []
                idx += 1
                continue

            # Determine if this line introduces a new date
            date_match = date_pattern.match(line_for_date)
            if date_match:
                date_str = date_match.group(1)
                if statement_start_date and statement_end_date:
                    current_date = infer_year_from_period(
                        date_str,
                        statement_start_date,
                        statement_end_date,
                        date_formats=self.config.date_formats
                    )
                else:
                    current_date = parse_date(date_str, self.config.date_formats)
                pending_desc_lines = []

            if not current_date:
                idx += 1
                continue

            raw_desc_segment = _slice(line, col_desc, col_out)
            if raw_desc_segment.strip():
                pending_desc_lines.append(' '.join(raw_desc_segment.split()))

            raw_out_segment = _slice(line, col_out, col_in)
            raw_in_segment = _slice(line, col_in, col_bal)
            raw_bal_segment = _slice(line, col_bal, None)

            has_amounts = any(seg.strip() for seg in [raw_out_segment, raw_in_segment, raw_bal_segment])
            if not has_amounts:
                idx += 1
                continue

            money_out = _safe_parse_amount(raw_out_segment)
            money_in = _safe_parse_amount(raw_in_segment)
            balance = _safe_parse_amount(raw_bal_segment)

            money_out = abs(money_out) if money_out is not None else 0.0
            money_in = abs(money_in) if money_in is not None else 0.0

            description = ' '.join(pending_desc_lines).strip()
            if not description:
                description = raw_desc_segment.strip()

            if not description:
                idx += 1
                continue

            if "Balance from statement" in description:
                idx += 1
                continue

                desc_lower = description.lower()
                desc_compact = desc_lower.replace(' ', '')
                credit_keywords = [
                    "bankcredit",
                    "transferfrom",
                    "credit",
                    "returneddirectdebit",
                    "cashback",
                    "refund"
                ]
                if money_in == 0.0 and money_out > 0 and any(keyword in desc_compact for keyword in credit_keywords):
                    money_in = money_out
                    money_out = 0.0

                if money_in == 0.0 and money_out == 0.0:
                    primary_amount = (
                        parse_currency(raw_out_segment) or
                        parse_currency(raw_in_segment) or
                        0.0
                    )
                    if any(keyword in desc_compact for keyword in credit_keywords):
                        money_in = abs(primary_amount)
                    else:
                        money_out = abs(primary_amount)

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

                if pending_period_marker:
                    marker_balance = pending_period_balance
                    if marker_balance is None and balance is not None:
                        marker_balance = balance - money_in + money_out
                    marker = Transaction(
                        date=current_date,
                        description="NATIONWIDE_PERIOD_BREAK",
                        money_in=0.0,
                        money_out=0.0,
                        balance=marker_balance,
                        transaction_type=None,
                        confidence=100.0
                    )
                    transactions.append(marker)
                    pending_period_marker = False
                    pending_period_balance = None

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
