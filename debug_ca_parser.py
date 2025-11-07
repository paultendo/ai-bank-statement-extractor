"""Debug script to test Crédit Agricole parser logic."""
import re

# Test lines from the PDF
test_lines = [
    # Should be Money IN (has ¨ near amount)
    ("                                         02.04    02.04    Virement    Groupe Esc Clermont                                                                                1 764,00   ¨", "IN"),
    ("                                         02.09    02.09    Virement    Aesio Mutuelle Ex Adrea                                                                              13,50  ¨", "IN"),

    # Should be Money OUT (¨ far from amount, in empty Crédit column)
    ("                                         04.08    04.08    Carte      X0531 Crf Vichy             03/08                                                 55,00                        ¨", "OUT"),
    (" 31.12   31.12   Virement    Ag Madame Ferguson Nicola                                                         3 000,00", "OUT"),
    ("                                         02.04    02.04    Carte      X0531 Intermarche Vichy          01/04                                             5,22", "OUT"),
]

# Pattern from parser
amount_pattern = re.compile(r'(?<![/\d])(\d{1,3}(?:[\s]\d{3})*,\d{2})(?![/\d])')

print("=== TESTING NEW LOGIC ===\n")

correct = 0
total = 0

for line, expected in test_lines:
    total += 1
    # Split like parser does
    parts = line.split(None, 2)
    remainder = parts[2] if len(parts) > 2 else ""

    # Extract amounts FIRST
    amounts = amount_pattern.findall(remainder)

    # NEW LOGIC: Check if ¨ appears within 15 chars after amount
    is_credit_column = False
    if amounts and '¨' in remainder:
        last_amount = amounts[-1]
        amount_pos = remainder.rfind(last_amount)
        if amount_pos != -1:
            text_after_amount = remainder[amount_pos + len(last_amount):amount_pos + len(last_amount) + 15]
            is_credit_column = '¨' in text_after_amount

    result = "IN" if is_credit_column else "OUT"
    status = "✓" if result == expected else "✗"

    if result == expected:
        correct += 1

    print(f"{status} Expected: {expected:3s}, Got: {result:3s}")
    print(f"   Amount: {amounts[-1] if amounts else 'NONE':10s}, ¨ near amount: {is_credit_column}")
    print(f"   Line: {line[:80]}...\n")

print(f"=== RESULTS: {correct}/{total} correct ===")

