# Santander Bank Support Status

## Current Status: ✅ Native PDF Support Verified

### Regression Run (2025-11-08)
```
python3 -m src.cli extract "statements/CurrentAccountStatement_08022024.pdf" --output output/santander_current_202402.xlsx
```

- Bank auto-detected as **Santander** (YAML identifiers + sort-code fallback).
- Extraction path: `pdftotext` → Santander parser (no OCR/Vision needed).
- Statement metadata: Account 12836321, period **9 Jan 2024 – 7 Feb 2024**.
- Transactions parsed: **212**.
- Excel export: `output/santander_current_202402.xlsx` (3 sheets).
- Totals row (Transactions sheet, row 215): Money In **£5,341.71**, Money Out **£5,323.10**.
- Balances reconciled ✓, confidence 100%.

### Next Steps
- Add this PDF (and, ideally, a second Santander period) to regression tests.
- Gather a low-quality scan/photo to exercise Vision/OCR fallbacks for Santander layouts.
- Update README/PROJECT_STATUS supported-bank lists.
