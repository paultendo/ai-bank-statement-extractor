# HSBC Bank Support Status

## Current Status: ✅ Native PDF Support Verified (Vision/OCR fallback still available for scans)

### Latest Regression Run (2025-11-08)

Command:
```
python3 -m src.cli extract "statements/HSBC Combined Statements for Myah Wright.pdf" --output output/hsbc_myah.xlsx
```

Results:
- Bank auto-detected as **HSBC** via YAML identifiers.
- Extraction path: `pdftotext` (no Vision/OCR fallback needed).
- Statement period detected: **10 February 2025 – 9 March 2025** (combined multi-period PDF).
- Transactions parsed: **195** (multi-line descriptions + Type column handled).
- Balances recalculated from BROUGHT FORWARD: Opening £33,838.27 → Closing £19,840.97.
- Excel export: `output/hsbc_myah.xlsx` with 3-sheet workbook.
- Totals row (Transactions sheet): Money In **£47,039.28**, Money Out **£38,086.70** (row 198). Balances reconciled, confidence 100%.

### What Works ✅
- Native PDF extraction and parser pipeline for HSBC combined statements.
- Multi-period BROUGHT FORWARD logic (per-period balance corrections) mirrors NatWest approach.
- Excel exporter + audit log capture metadata, warnings, and low-confidence rows (none in this run).

### Remaining Gaps / Next Steps ❌
1. **Regression Coverage**: Add this PDF (and at least one single-period HSBC statement) to an automated smoke suite.
2. **BBox QA**: Confirm whether HSBC configs need bounding-box cropping; ensure toggles don’t clip the Type column.
3. **OCR/Vision Edge Cases**: Capture a low-quality HSBC scan/photo to drive upcoming OCR fallback testing.
4. **Documentation**: Update README/PROJECT_STATUS bank tables to reflect HSBC as validated alongside NatWest/Halifax.

### Next Bank Target
- Move on to **Lloyds** or **Barclays** statements in `/statements` using the same “extract → Excel → document totals” workflow, so we can build a multi-bank regression suite before enabling batch automation.

