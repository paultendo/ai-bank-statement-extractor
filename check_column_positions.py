"""Check where amounts appear in Crédit vs Débit lines."""
import subprocess

# Extract a few sample lines
pdf_path = "/Users/pw/Code/ai-bank-statement-extractor/statements/Nicola Ferguson/Nicola Ferguson - Bank Statements.pdf"
result = subprocess.run(['pdftotext', '-layout', pdf_path, '-'], capture_output=True, text=True)
lines = result.stdout.split('\n')

# Find specific transactions
credit_line = None
debit_line = None

for line in lines:
    if '02.04' in line and '1 764,00' in line:
        credit_line = line
    if '04.08' in line and '55,00' in line and 'Crf Vichy' in line:
        debit_line = line

if credit_line:
    print("=== CRÉDIT LINE (Money IN) ===")
    print(f"Full line: '{credit_line}'")
    print(f"Line length: {len(credit_line)}")
    amount_pos = credit_line.find('1 764,00')
    print(f"Amount position: {amount_pos}")
    print(f"Characters after amount: {len(credit_line) - amount_pos - 8}")
    print()

if debit_line:
    print("=== DÉBIT LINE (Money OUT) ===")
    print(f"Full line: '{debit_line}'")
    print(f"Line length: {len(debit_line)}")
    amount_pos = debit_line.find('55,00')
    print(f"Amount position: {amount_pos}")
    print(f"Characters after amount: {len(debit_line) - amount_pos - 5}")
