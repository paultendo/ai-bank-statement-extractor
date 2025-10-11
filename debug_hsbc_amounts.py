#!/usr/bin/env python3
"""Debug script to trace HSBC amount extraction for transaction 0025812290"""

import re
from src.utils.currency_parser import parse_currency

# Simulate the parser processing these lines
amount_pattern = re.compile(r'([\d,]+\.\d{2})(?!\d)')

PAID_OUT_THRESHOLD = 78
PAID_IN_THRESHOLD = 103
MIN_AMOUNT_POSITION = 50  # NEW: Ignore amounts in description text

lines = [
    "             VIS     INT'L 0025812290",
    "                     PG *MUNDPAY ()",
    "                     RIO DE JANEIR",
    "                     BRL 57.50 @ 7.5360",
    "                     Visa Rate                                        7.63",
    "             DR      Non-Sterling",
    "                     Transaction Fee                                  0.20                                         35,527.73"
]

current_payment_type = None
description_lines = []
current_date = "2024-12-10"

payment_type_pattern = re.compile(r'^\s*(VIS|DD|SO|BP|ATM|CR|DR|\)\)\))')

for i, line in enumerate(lines):
    print(f"\n--- Line {i}: {line[:70]}")

    # Check for payment type
    payment_match = payment_type_pattern.search(line)
    if payment_match:
        current_payment_type = payment_match.group(1)
        desc_from_payment_line = line[payment_match.end():].strip()
        print(f"  → Payment type: {current_payment_type}")
        print(f"  → Description start: {desc_from_payment_line[:50]}")
        description_lines = [desc_from_payment_line]

    # Find amounts on this line (with position filtering)
    amounts_with_pos = []
    for match in re.finditer(amount_pattern, line):
        amt_str = match.group(1)
        pos = match.start()
        print(f"  → Found amount: {amt_str} at position {pos}", end="")
        if pos >= MIN_AMOUNT_POSITION:
            amounts_with_pos.append((amt_str, pos))
            print(" ✓ (≥50)")
        else:
            print(f" ✗ (ignored, <{MIN_AMOUNT_POSITION})")

    # Check if this line completes a transaction
    if amounts_with_pos and current_payment_type:
        print(f"  → COMPLETES TRANSACTION (has amounts + payment_type={current_payment_type})")

        # Add description part before amount
        if not payment_match and line.strip():
            first_amount_pos = amounts_with_pos[0][1]
            desc_part = line[:first_amount_pos].strip()
            if desc_part:
                description_lines.append(desc_part)
                print(f"  → Added description part: {desc_part}")

        full_description = ' '.join(description_lines)
        print(f"  → Full description: {full_description[:60]}")

        # Classify amounts
        money_in = 0.0
        money_out = 0.0
        balance = None

        for amt_str, pos in amounts_with_pos:
            amt_val = parse_currency(amt_str) or 0.0

            if pos <= PAID_OUT_THRESHOLD:
                money_out = amt_val
                print(f"  → Classified {amt_str} at pos {pos} as MONEY OUT (≤{PAID_OUT_THRESHOLD})")
            elif pos <= PAID_IN_THRESHOLD:
                money_in = amt_val
                print(f"  → Classified {amt_str} at pos {pos} as MONEY IN (≤{PAID_IN_THRESHOLD})")
            else:
                balance = amt_val
                print(f"  → Classified {amt_str} at pos {pos} as BALANCE (>{PAID_IN_THRESHOLD})")

        print(f"  ✓ Transaction: In={money_in}, Out={money_out}, Balance={balance}")

        # Reset
        description_lines = []
        current_payment_type = None

    elif line.strip():
        # Description continuation
        if not payment_match:
            description_lines.append(line.strip())
            print(f"  → Description continuation")
