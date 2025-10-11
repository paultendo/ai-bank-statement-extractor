"""HSBC bank statement parser.

Handles HSBC-specific statement format with stateful parsing,
payment type codes, and smart balance validation.

Format characteristics:
- Date tracking (one date applies to multiple transactions)
- Payment type codes: VIS, CR, ))), DD, SO, BP, ATM, PIM, CHQ, TFR, DR
- Multi-line descriptions accumulate until amounts found
- "Paid out" and "Paid in" columns (positions vary across pages)
- Balance shown intermittently (not after every transaction)
- MIN_AMOUNT_POSITION filter to ignore amounts in description text
- Smart swap validation (only corrects if error reduces)
- Pre-scan for column thresholds to handle transactions before headers
"""

import logging
import re
from datetime import datetime
from typing import Optional, List

from .base_parser import BaseTransactionParser
from ..models import Transaction
from ..utils import parse_currency, parse_date, infer_year_from_period

logger = logging.getLogger(__name__)


class HSBCParser(BaseTransactionParser):
    """Parser for HSBC bank statements."""

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse HSBC statement text with stateful line-by-line processing.

        HSBC format combines NatWest and Halifax characteristics:
        - Date tracking (one date applies to multiple transactions)
        - Multi-line descriptions
        - Payment type codes (VIS, CR, ))), DD, SO, BP, ATM, PIM, CHQ, TFR, DR)
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
        while idx < len(lines):
            line = lines[idx]

            # Skip blank lines
            if not line.strip():
                idx += 1
                continue

            # Check for table header (update column thresholds)
            if header_pattern.search(line):
                paid_out_match = re.search(r'Paid\s+out', line)
                paid_in_match = re.search(r'Paid\s+in', line)
                balance_match = re.search(r'Balance', line)

                if paid_out_match and paid_in_match and balance_match:
                    paid_out_start = paid_out_match.start()
                    paid_in_start = paid_in_match.start()
                    balance_start = balance_match.start()

                    PAID_OUT_THRESHOLD = (paid_out_start + paid_in_start) // 2
                    PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2

                    logger.debug(f"Updated column thresholds: Paid out ≤{PAID_OUT_THRESHOLD}, Paid in ≤{PAID_IN_THRESHOLD}")

                idx += 1
                continue

            # Check for BALANCE BROUGHT/CARRIED FORWARD
            if balance_marker_pattern.search(line):
                amounts = amount_pattern.findall(line)
                if amounts:
                    balance = parse_currency(amounts[-1]) or 0.0

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

                # Check if this line has amounts
                temp_amounts = []
                for match in re.finditer(amount_pattern, line):
                    temp_amounts.append((match.group(1), match.start()))

                if temp_amounts:
                    # Extract description before first amount
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
                MIN_AMOUNT_POSITION = 50
                if pos >= MIN_AMOUNT_POSITION:
                    amounts_with_pos.append((amt_str, pos))
                else:
                    logger.debug(f"Ignoring amount {amt_str} at position {pos} (< {MIN_AMOUNT_POSITION}) - likely description text")

            if amounts_with_pos and current_payment_type:
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
                            logger.debug(f"Correcting HSBC direction for {full_description[:30]}: balance change {balance_change:.2f} != calculated {calculated_change:.2f}")
                            money_in, money_out = money_out, money_in
                        else:
                            logger.debug(f"HSBC keeping original classification for {full_description[:30]}: likely PDF rounding error")

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
        return transactions
