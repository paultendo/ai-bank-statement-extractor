# Bank Statement Extractor – Internal Reference Guide

This note is for our own context compression. It captures what the project does, what’s already working, how to exercise it, and what’s still on the roadmap. When I need to reload context quickly, start here.

---

## 1. Overview

- **Purpose:** Extract structured financial data (transactions, metadata, audit logs) from multi-format bank statements for Fifty Six Law. Output is Excel + optional JSON. Accuracy and auditability drive the design (legal evidence).
- **Architecture:** `ExtractionPipeline` orchestrates pdfplumber/pdftotext extraction → bank detection → bank-specific parser → validation → Excel/JSON export. Each bank has a YAML config + parser; shared logic lives under `src/parsers/base_parser.py` and `src/utils/`.
- **Current focus:** Stabilise the core UK banks (NatWest, Halifax, HSBC, Lloyds, Barclays, TSB, Santander, Monzo) plus document the gaps (Nationwide multi-statement, OCR fallback, batch CLI).

---

## 2. Current Capabilities

| Bank | Status | Notes |
|------|--------|-------|
| **NatWest** | ✅ | Statements 1–3 (combined) parse; balance reconciliation works via `MONZO_PERIOD_BREAK` logic. |
| **Halifax** | ✅ | Dec 24 & Jan 25 PDFs parse with bbox cropping; confidence 100 %. |
| **HSBC** | ✅ | "HSBC Combined Statements for Myah Wright" (195 txns) passes. |
| **Lloyds** | ✅ | “Lloyds – Deborah Prime.pdf” (79 txns) reconciles. |
| **Barclays** | ✅ | Proudfoot May 2024 statement (78 txns). |
| **Santander** | ✅ | `CurrentAccountStatement_08022024.pdf` (212 txns). |
| **TSB** | ✅ | “TSB Savings account – Mark Wilcox.pdf” (31 txns) after parser fix. |
| **Monzo** | ✅ | “monzo-bidmead.pdf” (1,035 txns) with pot summaries sheet. |
| **Nationwide** | ⚠️ | “Marsh Bankstatements up to April 2024.pdf” parses (695 txns) but multi-statement balances still drift; need smarter period handling. |

Supporting infrastructure:
- **CLI** (`python -m src.cli extract …`) now supports `--json` for machine-readable results.
- **Excel exporter** produces Transactions + Statement Metadata + Pot Summaries (if available) + Extraction Log.
- **Smoke suite** (`python3 smoke/run_smoke.py`) runs the CLI across validated PDFs, asserts reconciliation, and applies bank-specific checks (Monzo Pot sheet, TSB txn count/closing balance). Currently green for the validated banks above.

---

## 3. How to Use It

### 3.1 One-off extraction
```bash
python3 -m src.cli extract statements/HSBC\ Combined\ Statements\ for\ Myah\ Wright.pdf \
  --output output/hsbc_myah.xlsx \
  --json output/hsbc_myah.json
```
Outputs go to `output/…`. The JSON mirrors `ExtractionResult.to_dict()` (statement metadata, transaction count, reconciliation flag, timings, warnings).

Key CLI options:
- `--bank` to force a bank (otherwise auto-detects from YAML identifiers/sort code fallback).
- `--use-vision` reserved for forcing the Vision API extractor (rarely needed with current PDFs).
- `--format csv` (not heavily used yet; Excel is primary).

### 3.2 Smoke tests
The curated regression harness lives in `smoke/run_smoke.py`. It expects the statements under `statements/` and writes Excel+JSON suffixed with `_smoke`. Running it after significant parser changes is mandatory:
```bash
python3 smoke/run_smoke.py
```
Additional custom checks live alongside each case (TSB closing balance, Monzo Pot sheet). Nationwide will be added once reconciliation stabilises.

### 3.3 Manual debugging tips
- **pdftotext sanity check:** `pdftotext -layout file.pdf - | head` to inspect column alignment and see whether bbox cropping is needed.
- **pdfplumber experiments:** ``python3 - <<'PY'`` blocks to inspect page text, locate headers, and confirm column thresholds (`_detect_column_thresholds`).
- **JSON diffing:** Because the CLI emits JSON, we can compare before/after changes using `jq` or plain `diff` to ensure transaction counts, totals, and metadata remain consistent.

---

## 4. Known Issues & Gaps

1. **Nationwide combined statements** – each PDF bundles many months. We now insert `NATIONWIDE_PERIOD_BREAK` markers, but per-period opening balances still need to cascade correctly. Validation currently fails on early transactions due to info-box contamination. TODO:
   - Strip the info box more aggressively (maybe tighten bbox or detect lines with “Average credit/debit”).
   - When a “Balance from statement …” line appears, set the next transaction’s starting balance to that value so reconciliation restarts cleanly.
   - Once stable, add Nationwide to the smoke suite with assertions (e.g., number of period markers, per-period reconciliation).
2. **OCR fallback** – still missing. For scanned Halifax/Santander PDFs we’ll need a pytesseract-based extractor between pdftotext and Vision API.
3. **Batch CLI** – the `cli batch` command is still a stub. Users rely on the smoke harness or manual loops.
4. **pytest addopts** – `pytest.ini` references `--cov` but the runtime where this project executes might lack `pytest-cov`. Either vendor the dependency or guard the addopts.
5. **CSV export path** – seldom used and untested with newer features (e.g., pot summaries). Needs validation if clients expect CSV.

---

## 5. Roadmap Snapshot

Short-term (now → 2 weeks):
1. **Nationwide reconciliation** – finish period handling and make the smoke suite pass that PDF. Document the approach in `NATIONWIDE_STATUS.md`.
2. **Smoke automation** – hook the new JSON-enabled smoke runner into CI once the Nationwide case is stable.
3. **pytest re-enablement** – either ensure `pytest-cov` is available or adjust `pytest.ini` so `pytest -q` succeeds out of the box.

Medium-term (Q4 2025):
1. **OCR/Pot photo support** – implement `ocr_extractor.py` (pytesseract + preprocessing) and define heuristics for when to trigger OCR vs. Vision.
2. **Batch CLI** – finish `cli batch` using the smoke-runner patterns (result summary, per-file status, aggregated warnings).
3. **Bank expansion** – onboard remaining YAML-configured banks (e.g., Nationwide once done, additional statements for Barclays/Santander, maybe HSBC business accounts). Each addition should follow the “run CLI → document totals → update README + STATUS docs → smoke entry” workflow.

Long-term (2026+):
- **UI polish (Streamlit)** – integrate the pot summaries + JSON metadata into the Streamlit UI for manual review.
- **Vision fallback economics** – capture cost metrics per statement and add dynamic routing (pdfplumber → pdftotext → OCR → Vision) with logging.
- **Automation hooks** – expose a proper Python API in addition to the CLI for batch processing pipelines.

---

## 6. File Map / References

- `src/pipeline.py` – main workflow (updated to propagate parser `additional_data` and tolerate missing balances/dates).
- `src/parsers/` – bank-specific logic; Nationwide & Monzo have the latest complex handling (period breaks, pot parsing).
- `src/models/statement.py` / `transaction.py` – updated to handle optional fields for JSON export.
- `src/exporters/excel_exporter.py` – writes Transactions, Statement Metadata, Pot Summaries, Extraction Log.
- `smoke/run_smoke.py` – regression harness.
- `docs/*_STATUS.md` – per-bank status snapshots (Halifax, HSBC, Lloyds, Barclays, Santander, TSB, Monzo, Nationwide).
- `docs/SORT_CODE_PREFIX_NOTES.md` – sort-code research, including challenger banks not yet in the parser map.

Use this guide as the source of truth when reloading the context or briefing another agent. Update it whenever we pull a new bank into the “validated” list or alter the workflow materially.
