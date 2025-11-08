# TSB Bank Support Status

## Current Status: ✅ Native PDF Support (post parser fixes)

### Regression Run (2025-11-08)
```
python3 -m src.cli extract "statements/TSB Savings account - Mark Wilcox.pdf" --output output/tsb_mark.xlsx
```

- Bank auto-detected as **TSB** via config identifiers.
- Extraction path: `pdftotext` → TSB parser.
- Statement metadata: Account 00034106, period **16 Oct 2023 – 12 Sep 2024**.
- Transactions parsed: **31** (after filtering footer noise).
- Excel export: `output/tsb_mark.xlsx` (Money In £2,700.00 / Money Out £2,420.00, reconciled).
- Confidence 100 %, balance validator passes.

### Fix Implemented
- TSB parser now handles `STATEMENT CLOSING BALANCE` before skip patterns and reuses statement-start date for the BROUGHT FORWARD entry.
- Added TSB-specific skip patterns for the FSCS block (“Basic information about the protection…”, etc.) so footer text stops polluting descriptions.

### Next Steps
- Fold this PDF into the smoke/regression harness once that’s scripted.
- Capture a second TSB statement (different account layout) for coverage.
- Add a scan/photo sample later to validate OCR/Vision fallback.
