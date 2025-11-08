"""Monzo Bank statement parser.

Monzo statements have a unique format where dates are split across lines:
- DD/MM/YYY on one line (year's last digit missing)
- Final digit on a separate line after the transaction

Two transaction layouts:
A) Date + Description on same line:
   31/05/202        Description
                                                -19.00               0.23
   4                Optional continuation

B) Date alone:
   30/05/202
                    Description                 -15.02             19.23
   4
"""

import logging
import re
from datetime import datetime
from typing import List, Optional

from .base_parser import BaseTransactionParser
from ..models import Transaction, TransactionType
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)


class MonzoTransactionParser(BaseTransactionParser):
    """Parser for Monzo bank statements."""

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime] = None,
        statement_end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """
        Parse Monzo transactions with split-date handling.

        Monzo format:
        - Dates appear as DD/MM/YYY (missing last digit)
        - Final digit appears on separate line after transaction
        - Two layouts: date+desc same line, or date alone

        Args:
            text: Raw text from PDF
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of Transaction objects
        """
        lines = text.split('\n')
        transactions = []

        # Find ALL Personal Account sections and Pot sections
        # Structure: "Personal Account" on one line, "statement" on next line
        # Strategy: Mark ranges as either "personal" or "pot", then parse only "personal" ranges

        section_markers = []  # List of (line_idx, section_type)

        for idx, line in enumerate(lines):
            # Check for "Personal Account statement" (standard format - single line)
            if 'Personal Account statement' in line:
                section_markers.append((idx, 'personal'))
                logger.debug(f"Found Personal Account statement section (single line) at line {idx}")
            # Check for "Personal Account" followed by "statement" on next line (large print format)
            elif 'Personal Account' in line and idx + 1 < len(lines) and 'statement' in lines[idx + 1]:
                section_markers.append((idx, 'personal'))
                logger.debug(f"Found Personal Account statement section (split lines) at line {idx}")
            # Check for "Pot statement"
            elif 'Pot statement' in line:
                section_markers.append((idx, 'pot'))
                logger.debug(f"Found Pot statement section at line {idx}")

        if not section_markers:
            logger.error("Could not find any Personal Account or Pot sections")
            return []

        # Build ranges for personal accounts and pots
        parse_ranges = []
        pot_ranges = []
        for i, (start_idx, section_type) in enumerate(section_markers):
            if i + 1 < len(section_markers):
                end_idx = section_markers[i + 1][0]
            else:
                end_idx = len(lines)

            if section_type == 'personal':
                parse_ranges.append((start_idx, end_idx, section_type))
                logger.debug(f"Personal Account range: lines {start_idx} to {end_idx}")
            elif section_type == 'pot':
                pot_ranges.append((start_idx, end_idx))
                logger.debug(f"Pot statement range: lines {start_idx} to {end_idx}")

        if not parse_ranges:
            logger.error("No Personal Account sections found")
            return []

        if pot_ranges:
            pot_data = self._parse_pot_sections(lines, pot_ranges)
            if pot_data:
                self.additional_data['pots'] = pot_data

        # Pattern for date line - supports TWO formats:
        # 1. Complete: DD/MM/YYYY (standard Monzo format)
        # 2. Split: DD/MM/YYY (large print format, missing last digit)
        date_pattern_complete = re.compile(r'^\s*(\d{1,2}/\d{1,2}/\d{4})')
        date_pattern_split = re.compile(r'^\s*(\d{1,2}/\d{1,2}/\d{3})')

        # Pattern for single digit (year's last digit) - only needed for split format
        year_digit_pattern = re.compile(r'^\s*(\d)(?:\s+(.*))?$')

        # Amount pattern
        amount_pattern = re.compile(r'(-?[\d,]+\.\d{2})')

        # Compile footer patterns ONCE for performance
        footer_compiled = re.compile(
            r'Monzo Bank Limited|Registered Office|Financial Services|'
            r'Prudential Regulation Authority|Financial Conduct Authority|'
            r'--- Page \d+ ---|^\s*Page \d+\s*$|Important information|'
            r'FSCS|www\.monzo\.com|Compensation Scheme|'
            r'^\s*\(GBP\)\s*\(GBP\)\s*$|authorised by the|regulated by the|'
            r'Date\s+Description\s+Amount\s+Balance|Personal Account\s*$|'
            r'^\s*statement\s*$|Balance in Pots|Total outgoings|Total deposits|'
            r'Excluding all Pots|Regular Pots with Monzo|Savings Pots with external|'
            r'Sort code:|Account number:|BIC:|IBAN:',
            re.IGNORECASE
        )

        # Parse each section range (Personal Account and Pots)
        for period_idx, (range_start, range_end, section_type) in enumerate(parse_ranges):
            logger.warning(f"===== PARSING RANGE {period_idx}: lines {range_start} to {range_end} ({section_type}) =====")
            # Find transaction table header in this range
            # Two formats:
            # 1. Large print: "Date    Description    Amount    Balance" (all on one line)
            # 2. Standard: "Date" on one line, "Description" on next, etc. (split lines)
            header_idx = None
            for idx in range(range_start, range_end):
                # Check for single-line header (both formats)
                # Large print: "Date    Description    Amount    Balance"
                # Standard: "Date    Description    (GBP) Amount    (GBP) Balance"
                if re.search(r'Date\s+Description\s+(\(GBP\)\s+)?Amount\s+(\(GBP\)\s+)?Balance', lines[idx], re.IGNORECASE):
                    header_idx = idx
                    logger.debug(f"Found transaction header (single line) at line {idx}")
                    break
                # Check for multi-line header (standard format)
                # "Date" on one line, "Description" within next 3 lines
                if lines[idx].strip() == 'Date':
                    # Look ahead for "Description"
                    for look_ahead in range(1, min(4, range_end - idx)):
                        if 'Description' in lines[idx + look_ahead]:
                            header_idx = idx
                            logger.debug(f"Found transaction header (multi-line) starting at line {idx}")
                            break
                    if header_idx:
                        break

            if header_idx is None:
                logger.debug(f"No transaction header found in {section_type} section range {range_start}-{range_end} (likely empty)")
                continue

            # Track LAST transaction we parse from this period
            # (which will be chronologically FIRST after sorting, since PDF is reverse-chronological)
            last_txn_of_period = None

            # Helper functions for emit-on-completion pattern
            def txn_is_complete():
                """Check if current transaction has all required components"""
                return bool(current_date_incomplete) and not pending_year_digit and len(current_amounts) >= 2

            def emit_current():
                """Emit the current transaction and track it"""
                nonlocal last_txn_of_period
                if 'Kashia' in ' '.join(current_description_lines) or 'APPERATOR' in ' '.join(current_description_lines):
                    logger.warning(f"FX-EMIT: Emitting transaction with desc={' '.join(current_description_lines)[:60]}, amounts={current_amounts}, date={current_date_incomplete}")
                transaction = self._build_monzo_transaction(
                    current_date_incomplete,
                    current_description_lines,
                    current_amounts,
                    statement_start_date,
                    statement_end_date
                )
                if transaction:
                    transactions.append(transaction)
                    last_txn_of_period = transaction

            # State machine for this range
            current_date_incomplete = None  # e.g., "31/05/202"
            current_description_lines = []
            current_amounts = []
            pending_year_digit = False

            # Carry-over buffer for next transaction (GPT-5 Pro fix)
            carry_over_desc = None  # Lines that belong to NEXT transaction

            i = header_idx + 1
            while i < range_end:
                line = lines[i]
                i += 1

                # Debug specific lines
                if 'Kashia' in line or ('APPERATOR' in line and 'Edinburgh' in line):
                    # Dump actual array content
                    current_i = i - 1  # Current line we just read
                    dump_start = max(0, current_i - 2)
                    dump_end = min(len(lines), current_i + 8)
                    logger.warning(f"TRACE-LINE: line='{line.strip()[:60]}' at index={current_i}")
                    for j in range(dump_start, dump_end):
                        marker = " <-- HERE" if j == current_i else ""
                        logger.warning(f"  lines[{j}]: '{lines[j].strip()[:50]}'{marker}")
                    logger.warning(f"  State: desc={current_description_lines}, amounts={len(current_amounts)}, pending_year={pending_year_digit}")

                # Skip footer/header/page break lines (use pre-compiled pattern for speed)
                if footer_compiled.search(line):
                    if 'Amount:' in line or 'rate:' in line or (line.strip() and re.match(r'^-?\d+\.\d{2}$', line.strip())):
                        logger.warning(f"FOOTER-SKIP: Skipping line that looks like FX data: '{line.strip()[:60]}'")
                    continue

                # Trace ALL lines during Kashia/APPERATOR transactions
                if any(kw in ' '.join(current_description_lines) for kw in ['Kashia', 'APPERATOR']):
                    logger.warning(f"TRACE-ALL: Processing line='{line.strip()[:60]}', desc_count={len(current_description_lines)}, amounts={len(current_amounts)}, pending_year={pending_year_digit}")

                # ALWAYS check for date line first (even if pending_year_digit)
                # Check for COMPLETE date first (DD/MM/YYYY), then split date (DD/MM/YYY)
                date_match_complete = date_pattern_complete.match(line)
                date_match_split = date_pattern_split.match(line) if not date_match_complete else None

                if date_match_complete:
                    # Complete date format - no need to wait for year digit
                    logger.warning(f"DATE-COMPLETE: line='{line.strip()[:40]}', matched complete date={date_match_complete.group(1)}")
                    # Save previous transaction if complete
                    if txn_is_complete():
                        emit_current()

                    # Start new transaction with complete date
                    current_date_incomplete = date_match_complete.group(1)
                    current_description_lines = []
                    current_amounts = []
                    pending_year_digit = False  # Date is already complete!

                    # ATTACH CARRY-OVER: Description lines that appeared BEFORE this date line
                    if carry_over_desc:
                        logger.warning(f"CARRY-OVER-ATTACH: Attaching {len(carry_over_desc)} buffered lines for complete date {current_date_incomplete}")
                        current_description_lines.extend(carry_over_desc)
                        carry_over_desc = None

                    # Check if description is on same line (Layout A)
                    remainder = line[date_match_complete.end():].strip()
                    if remainder:
                        remainder_for_amounts = re.sub(r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?', 'Amount: [FOREIGN]', remainder, flags=re.IGNORECASE)
                        amounts_in_remainder = amount_pattern.findall(remainder_for_amounts)
                        if amounts_in_remainder:
                            current_amounts.extend(amounts_in_remainder)
                            desc_part = remainder
                            for amt in amounts_in_remainder:
                                desc_part = desc_part.replace(amt, ' ', 1)
                            current_description_lines.append(desc_part.strip())
                        else:
                            current_description_lines.append(remainder)

                    continue

                elif date_match_split:
                    # Split date format - need to wait for year digit
                    logger.warning(f"DATE-SPLIT: line='{line.strip()[:40]}', matched date prefix={date_match_split.group(1)}, setting pending_year=True")
                    # Save previous transaction if complete
                    if txn_is_complete():
                        emit_current()

                    # Start new transaction
                    current_date_incomplete = date_match_split.group(1)
                    current_description_lines = []
                    current_amounts = []
                    pending_year_digit = True

                    # Check if description is on same line (Layout A)
                    remainder = line[date_match_split.end():].strip()
                    if remainder:
                        remainder_for_amounts = re.sub(r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?', 'Amount: [FOREIGN]', remainder, flags=re.IGNORECASE)
                        amounts_in_remainder = amount_pattern.findall(remainder_for_amounts)
                        if amounts_in_remainder:
                            current_amounts.extend(amounts_in_remainder)
                            desc_part = remainder
                            for amt in amounts_in_remainder:
                                desc_part = desc_part.replace(amt, ' ', 1)
                            current_description_lines.append(desc_part.strip())
                        else:
                            current_description_lines.append(remainder)

                    continue

                # Check for year's final digit (ONLY if no date match above)
                if pending_year_digit:
                    year_digit_match = year_digit_pattern.match(line)
                    if year_digit_match:
                        # Complete the date
                        current_date_incomplete += year_digit_match.group(1)
                        pending_year_digit = False

                        # ATTACH CARRY-OVER: Merchant lines that belong to THIS transaction
                        if carry_over_desc:
                            logger.warning(f"CARRY-OVER-ATTACH: Attaching {len(carry_over_desc)} buffered lines after date {current_date_incomplete}")
                            current_description_lines.extend(carry_over_desc)
                            carry_over_desc = None

                        # Check if there's continuation text after the digit
                        trailing = year_digit_match.group(2)
                        if trailing and trailing.strip():
                            current_description_lines.append(trailing.strip())
                        continue

                # Check for FX transaction markers (description lines, but may have GBP amounts!)
                # With -layout flag, FX lines can have GBP amounts on same line
                if 'Amount:' in line and ('EUR' in line or 'USD' in line):
                    # FX info line: "Amount: EUR -109.50. Conversion" (may have GBP amounts too)
                    # Attach carry-over FIRST (merchant name)
                    if carry_over_desc:
                        logger.warning(f"FX-AMOUNT: Attaching carry-over before FX info")
                        current_description_lines.extend(carry_over_desc)
                        carry_over_desc = None

                    # Extract GBP amounts if present (with -layout, they're on same line)
                    # BUT: Skip foreign currency amounts in "Amount: USD -38.06" part
                    # Strategy: Remove the "Amount: CUR -XX.XX" part first, then extract amounts
                    line_for_amounts = re.sub(r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?', 'Amount: [FOREIGN]', line, flags=re.IGNORECASE)
                    amounts_in_line = amount_pattern.findall(line_for_amounts)
                    if amounts_in_line:
                        if 'Kashia' in ' '.join(current_description_lines) or 'APPERATOR' in ' '.join(current_description_lines):
                            logger.warning(f"FX-AMOUNT-WITH-AMOUNTS: Found GBP amounts {amounts_in_line} (after filtering foreign currency)")
                        current_amounts.extend(amounts_in_line)

                    # Add description (remove amounts)
                    desc_part = line
                    for amt in amounts_in_line:
                        desc_part = desc_part.replace(amt, ' ', 1)
                    current_description_lines.append(desc_part.strip())

                    # Check if transaction is now complete
                    if txn_is_complete():
                        if 'Kashia' in ' '.join(current_description_lines) or 'APPERATOR' in ' '.join(current_description_lines):
                            logger.warning(f"FX-COMPLETE: Transaction complete after FX line")
                        emit_current()
                        current_description_lines = []
                        current_amounts = []
                    continue

                if 'rate:' in line.lower():
                    # Rate continuation line: "rate: 1.170122."
                    # Attach carry-over FIRST
                    if carry_over_desc:
                        logger.warning(f"FX-RATE: Attaching carry-over before rate info")
                        current_description_lines.extend(carry_over_desc)
                        carry_over_desc = None
                    current_description_lines.append(line.strip())
                    continue

                # Extract amounts from line
                amounts_in_line = amount_pattern.findall(line)

                if amounts_in_line:
                    # This line has amounts - likely the amount line (completes transaction)
                    current_amounts.extend(amounts_in_line)

                    # Extract description from this line (before amounts)
                    # Remove amounts to get description
                    desc_part = line
                    for amt in amounts_in_line:
                        desc_part = desc_part.replace(amt, ' ', 1)
                    desc_part = desc_part.strip()

                    if desc_part:
                        current_description_lines.append(desc_part)

                    # DON'T emit immediately - keep accumulating description lines
                    # Transaction will be emitted when we see the next date line

                else:
                    # No amounts - might be continuation line or carry-over for next transaction
                    stripped = line.strip()
                    if stripped and not re.search(r'^\(GBP\)', stripped):
                        # Check if previous transaction is complete (has amounts but not yet emitted)
                        if len(current_amounts) >= 2 and not pending_year_digit:
                            # Transaction is complete but not emitted yet
                            # This line could be:
                            # 1. Trailing description (like "Hdhd" after amounts) - add to current
                            # 2. Merchant name for NEXT transaction - will become carry-over when we see next date
                            # Solution: Add to current for now. When we see next DATE, we'll emit current
                            # and any remaining description will be carry-over
                            current_description_lines.append(stripped)
                        else:
                            # Normal continuation line for current transaction
                            current_description_lines.append(stripped)

            # Handle final transaction for this range
            if txn_is_complete():
                emit_current()

            # Mark the chronologically-first transaction of this period (last one we parsed)
            if last_txn_of_period and period_idx > 0:
                last_txn_of_period._period_start = True
                logger.debug(f"Marked transaction as period {period_idx + 1} start: {last_txn_of_period.date.date()}")

        # Monzo statements are in reverse chronological order (newest first)
        # We need to reverse to get chronological order, but preserve within-day ordering
        # Add index to each transaction to track original order
        indexed_transactions = [(i, t) for i, t in enumerate(transactions)]

        # Sort by date (ascending), then by REVERSE index (to flip the order)
        # This gives us: earliest dates first, and within each date, original PDF order reversed
        indexed_transactions.sort(key=lambda x: (x[1].date, -x[0]))

        # Extract transactions and insert period markers
        final_transactions = []
        previous_balance = 0.0
        for _, txn in indexed_transactions:
            # Insert period marker before transactions that start a new period
            if hasattr(txn, '_period_start') and txn._period_start:
                # Calculate opening balance of new period from first transaction
                # Opening = Current Balance - Money In + Money Out
                opening_balance = txn.balance - txn.money_in + txn.money_out

                marker = Transaction(
                    date=txn.date,  # Same date as first transaction of new period
                    description="MONZO_PERIOD_BREAK",
                    money_in=0.0,
                    money_out=0.0,
                    balance=opening_balance,  # Use actual opening balance of new period
                    transaction_type=TransactionType.OTHER,
                    confidence=100.0
                )
                final_transactions.append(marker)

                # Log if there's a discrepancy between periods
                if abs(previous_balance - opening_balance) > 0.01:
                    logger.warning(
                        f"Period break at {txn.date.date()}: Previous closing balance £{previous_balance:.2f} "
                        f"!= New opening balance £{opening_balance:.2f} (diff: £{opening_balance - previous_balance:.2f})"
                    )
                else:
                    logger.debug(f"Inserted period marker before {txn.date.date()} with balance £{opening_balance:.2f}")

                # Clean up the marker attribute
                delattr(txn, '_period_start')

            final_transactions.append(txn)
            # Track balance for next period marker
            previous_balance = txn.balance

        logger.info(f"✓ Parsed {len(final_transactions)} Monzo transactions (sorted chronologically, with period markers)")
        return final_transactions

    def _parse_pot_sections(self, lines: List[str], pot_ranges: List[tuple]) -> List[dict]:
        """Extract pot summaries (balance, totals, metadata) from pot statement sections."""
        pot_summaries: List[dict] = []
        period_pattern = re.compile(r'(\d{2}/\d{2}/\d{4})\s*-\s*(\d{2}/\d{2}/\d{4})')
        seen_keys = set()

        def extract_amount(value: Optional[str]) -> Optional[float]:
            if not value:
                return None
            match = re.search(r'[+\-]?£?[\d,]+\.\d{2}', value)
            return parse_currency(match.group(0)) if match else None

        for start_idx, end_idx in pot_ranges:
            summary = {
                'pot_name': None,
                'pot_type': None,
                'pot_balance': None,
                'total_in': None,
                'total_out': None,
                'period_start': None,
                'period_end': None,
                'has_transactions': None,
            }

            # Determine period
            for idx in range(start_idx, min(end_idx, start_idx + 5)):
                match = period_pattern.search(lines[idx])
                if match:
                    summary['period_start'] = parse_date(match.group(1), ["%d/%m/%Y"])
                    summary['period_end'] = parse_date(match.group(2), ["%d/%m/%Y"])
                    break

            prev_text = None
            prev_amount = None

            for idx in range(start_idx, end_idx):
                stripped = lines[idx].strip()
                if not stripped:
                    continue

                lowered = stripped.lower()

                if 'pot statement' in lowered:
                    continue

                if 'there were no transactions' in lowered:
                    summary['has_transactions'] = False
                    continue

                if 'pot balance' in lowered and summary.get('pot_balance') is None:
                    summary['pot_balance'] = prev_amount
                    continue

                if 'total outgoings' in lowered and summary.get('total_out') is None:
                    summary['total_out'] = prev_amount
                    continue

                if 'total deposits' in lowered and summary.get('total_in') is None:
                    summary['total_in'] = prev_amount
                    continue

                if lowered == 'pot type' and summary.get('pot_type') is None:
                    summary['pot_type'] = prev_text
                    continue

                if lowered == 'pot name' and summary.get('pot_name') is None:
                    summary['pot_name'] = prev_text
                    continue

                # Update trackers
                amount_val = extract_amount(stripped)
                if amount_val is not None:
                    prev_amount = amount_val
                else:
                    prev_amount = None

                prev_text = stripped

            key = (
                summary.get('pot_name'),
                summary.get('period_start'),
                summary.get('period_end')
            )
            if key in seen_keys:
                continue
            seen_keys.add(key)
            pot_summaries.append(summary)

        return pot_summaries

    def _build_monzo_transaction(
        self,
        date_str: str,
        description_lines: List[str],
        amounts: List[str],
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> Optional[Transaction]:
        """
        Build a Monzo transaction from parsed components.

        Args:
            date_str: Date string (DD/MM/YYYY)
            description_lines: List of description line fragments
            amounts: List of amount strings (usually 2: amount + balance)
            statement_start_date: For date inference
            statement_end_date: For date inference

        Returns:
            Transaction object or None
        """
        # Parse date - it's already complete (DD/MM/YYYY) from split-date reconstruction
        transaction_date = parse_date(date_str, self.config.date_formats)

        if not transaction_date:
            return None

        # Build description
        full_description = ' '.join(description_lines).strip()
        if not full_description:
            full_description = "Unknown"

        # Parse amounts
        # Monzo format: [amount, balance] or just [balance]
        money_in = 0.0
        money_out = 0.0
        balance = 0.0

        if len(amounts) >= 2:
            # Two amounts: transaction amount + balance
            amount_value = parse_currency(amounts[0])
            balance = parse_currency(amounts[1])

            if amount_value < 0:
                money_out = abs(amount_value)
            else:
                money_in = amount_value

        elif len(amounts) == 1:
            # Single amount - assume it's the balance
            balance = parse_currency(amounts[0])

        return Transaction(
            date=transaction_date,
            description=full_description,
            money_in=money_in,
            money_out=money_out,
            balance=balance,
            transaction_type=None
        )
