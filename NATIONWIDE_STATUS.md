# Nationwide Support Status

## Current Status: ✅ Validated (multi-period PDF reconciles with layout parser)

### Regression Run (Marsh Bankstatements up to April 2024)
```
python3 -m src.cli extract "statements/Marsh Bankstatements up to April 2024.pdf" \
  --bank nationwide \
  --output output/nationwide_marsh.xlsx \
  --json output/nationwide_marsh.json
```

- Detected bank: **Nationwide** (FlexAccount, combined statements 132–144 spanning Jan–Dec 2023 + Q1 2024 headers).
- Extraction path: `pdftotext` ➝ `pdfplumber+bbox+text+words` with dynamic amount-bound x₁ and tightened `x_tolerance=1.0 / y_tolerance=1.2`.
- Transactions parsed: **623** (Money In £6,079.44, Money Out £6,136.32) with **13** `NATIONWIDE_PERIOD_BREAK` markers (one per statement-period start).
- Statement metadata refined to **2023-01-01 – 2023-12-30**; Excel + JSON snapshots written to `output/nationwide_marsh.*`.
- **Balance validation:** ✅ passes end-to-end; running balances reset at each period break and align with statement totals.

### Parser/Extractor Changes
- Added **coordinate-aware layout parser**: we now capture pdfplumber word geometry, bucket columns via header-derived x-positions, and rebuild rows directly from coordinates (no pdftotext heuristics).
- Introduced `capture_word_layout: true` + dynamic bbox strategy (`dynamic_amount_x1`) in `nationwide.yaml`, plus configurable `x_tolerance`/`y_tolerance` forwarding so `extract_words()` stays in sync with text extraction.
- `_parse_with_layout` now:
  - Filters info-box text via x-cutoff (Balance column + 20 pt) instead of keyword-only skips.
  - Detects `Balance from statement …` rows, injects `NATIONWIDE_PERIOD_BREAK` transactions, and resets running balances per block.
  - Reconstructs descriptions from bounded x ranges and appends merchant continuation lines automatically.
- Text-only fallback (`_parse_from_lines`) is still available but unused in the happy path.

### Next Steps
1. **Smoke harness** – add `statements/Marsh Bankstatements up to April 2024.pdf` to `smoke/run_smoke.py` with custom assertions (13 period breaks, per-period reconciliation).
2. **Documentation refresh** – mirror the new parser details in `docs/PROJECT_GUIDE.md` / README "Recent Updates" so other agents know the layout parser is required.
3. **Future-proofing** – consider surfacing layout diagnostics (max column x, num rows/page) in logs to catch future bbox regressions automatically.
