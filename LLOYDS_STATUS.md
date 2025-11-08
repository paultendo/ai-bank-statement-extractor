# Lloyds Bank Support Status

## Current Status: ✅ Native PDF Support Verified (Vision/OCR fallback available for scans)

### Regression Run (2025-11-08)

Command:
```
python3 -m src.cli extract "statements/Lloyds - Deborah Prime.pdf" --output output/lloyds_deborah.xlsx
```

Highlights:
- Auto-detected bank: **Lloyds**.
- Extraction path: `pdftotext` (digital PDF, no OCR/Vision fallback triggered).
- Statement metadata: Account 41764268, period **1 Jan 2023 – 31 Jan 2023**.
- Transactions parsed: **79** (multi-line descriptions + foreign currency filtering handled by parser).
- Balances calculated from transactions: Opening £5,683.84 → Closing £445.69.
- Excel export saved to `output/lloyds_deborah.xlsx` (3 sheets).
- Totals row (Transactions sheet, row 82): Money In **£16,270.69**, Money Out **£21,508.84**. Balance reconciliation ✓, confidence 97.5% (slightly lower due to a handful of description-only rows).

### What Works ✅
- Native Lloyds parser handles right-aligned columns and multi-line descriptions.
- Balance validator reconciles the entire month despite gaps in statement metadata.
- Excel exporter captures totals, metadata, and audit log correctly.

### Outstanding Items ❌
1. **Regression Harness**: Add this PDF to automated smoke tests (esp. to guard bbox column detection changes).
2. **Low-quality Samples**: Need at least one Lloyds scan/photo to validate Vision/OCR fallback.
3. **Docs Sync**: Update README/PROJECT_STATUS bank lists to explicitly mark Lloyds as validated alongside NatWest/Halifax/HSBC.

### Next Bank Target
- Continue down the statements list (e.g., Barclays or Santander) to expand the verified regression set before enabling batch automation.

