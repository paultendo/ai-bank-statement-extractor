# Crédit Agricole Support Status

## Current Status: ⚠️ Combined Statements Parse with Warnings (balance mismatches remain)

### Regression Run (2025-11-08)

Command:
```
python3 -m src.cli extract "statements/Nicola Ferguson/Nicola Ferguson - Bank Statements.pdf" --output output/nicola_bank.xlsx
```

Highlights:
- Bank auto-detected as **credit_agricole**.
- Extraction path: `pdftotext`.
- Combined statement detected (20 period markers) covering **2 Dec 2024 – 1 Oct 2025**.
- Transactions parsed: **682**.
- Excel export saved to `output/nicola_bank.xlsx`.
- Totals row (Transactions sheet, row 685): Money In **£35,757.13**, Money Out **£35,221.03**.

### Issues Observed ❌
1. **Per-transaction balance mismatch** at the very first entry (expected £1,584.60 vs stated £1,613.65, diff £29.05).
2. **Statement totals mismatch**: calculated closing £2,107.20 vs stated £1,571.10 (diff £536.10). Likely due to source PDF inconsistencies across merged periods.
3. **Confidence drop** to 90% because of unreconciled balances.

### Next Steps
- Verify whether the source PDF’s balances are incorrect (similar to NatWest combined statements) or whether parser logic needs adjustment for Crédit Agricole combined layouts.
- Add targeted regression fixtures (single-month Crédit Agricole) to isolate the discrepancy.
- Explore whether multi-currency rows require special handling (FX metadata filtering, decimals, etc.).

