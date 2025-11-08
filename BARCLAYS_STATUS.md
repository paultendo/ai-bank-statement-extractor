# Barclays Bank Support Status

## Current Status: ✅ Native PDF Support Verified (Vision/OCR fallback available for scans)

### Regression Run (2025-11-08)

Command:
```
python3 -m src.cli extract "statements/Proudfoot/Statement 31-MAY-24 AC 33688186  02065716.pdf" --output output/proudfoot_2024-05.xlsx
```

Highlights:
- Auto-detected bank: **Barclays** via YAML identifiers.
- Extraction path: `pdftotext` (native text layer) with subsequent pdfplumber parsing.
- Statement metadata refined from single “statement date” to full period **1–31 May 2024** using BROUGHT FORWARD logic.
- Transactions parsed: **78** with multi-line descriptions preserved.
- Balances: Opening £278.34 → Closing £68.08 (calculated from transaction table).
- Excel export saved to `output/proudfoot_2024-05.xlsx`.
- Totals row (Transactions sheet, row 81): Money In **£1,814.84**, Money Out **£2,025.10**.
- Confidence 98.0%, reconciliation ✓.

### What Works ✅
- Barclays parser handles “statement date only” PDFs by inferring the full range from transactions.
- Balance validator reconciles the entire period once BROUGHT FORWARD is identified.
- Excel exporter + audit log capture totals/metadata as expected.

### Outstanding Items ❌
1. **Regression Coverage**: Add representative Barclays PDFs (at least one per account layout) to automated smoke tests.
2. **Additional Periods**: Run through a late-2024 or early-2025 Proudfoot statement to confirm stability across different layouts.
3. **Low-quality Inputs**: Acquire a scanned/photo Barclays statement to exercise Vision/OCR fallback paths.

### Next Bank Target
- With NatWest, Halifax, HSBC, Lloyds, and Barclays validated, move on to Santander (or another remaining YAML-configured bank) to round out the core UK set before enabling batch automation.

