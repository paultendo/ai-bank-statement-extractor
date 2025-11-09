# NatWest Parser Status (November 2025)

## Scope
- Statements under `statements/Y Jones` still mix two NatWest layouts:
  1. **Legacy (pre‑mid‑2023)** – `Date | Type | Description | Paid in | Paid out | Balance`, with BROUGHT FORWARD rows embedded inside the first page summary.
  2. **Select Account (mid‑2023 onward)** – `Date | Description | Paid In(£) | Withdrawn(£) | Balance(£)` with single numeric columns and long multi‑line descriptions.

## Current Behaviour (as of Nov 2025)
- Parser is now entirely pdfplumber-driven (NatWest config sets `force_pdfplumber`, `capture_word_layout`, dynamic bbox).
- Amount classification uses each token’s right edge (`x₁`) so right‑aligned Paid In/Out/Balance columns stay stable even when NatWest only prints one numeric cell.
- Direction hints act only when geometry cannot determine a column (e.g., single-amount rows printed inside the description span). “To A/C … Via Mobile Xfer” rows now fall back to debit, and “From A/C …” to credit.
- BROUGHT FORWARD rows reset the running balance but keep the current date so the next transaction inherits the correct date even if NatWest omits it.
- Pipeline rewrites opening/closing balances from the ledger (BROUGHT FORWARD + last balance) regardless of what the PDF header says, so negative openings survive into the metadata.
- Result: the full 80‑file Y Jones regression now finishes **80/80 reconciled** with no warnings.

## Work Done in this pass
- Added `force_pdfplumber` support + NatWest config change → always re-extract with pdfplumber and capture word layout.
- Replaced midpoint heuristics with `x₁` alignment and guarded direction hints so they only fire when both Money In/Out are still zero.
- Improved layout parser to stop description lookbacks at a new date line (prevents merging adjacent transactions) and to keep `current_date` after BROUGHT FORWARD markers.
- Added a “Select Account” regression test that ensures rows with a single amount (e.g., £18,000 Via Mobile Xfer) parse with the correct direction.
- Pipeline now always trusts BROUGHT FORWARD / last transaction balances to set `statement.opening_balance`/`statement.closing_balance`, overriding incorrect summary boxes in legacy PDFs.

## Remaining Work / Nice-to-haves
1. **Automatic period breaks** – One combined PDF (`13‑07‑2023–11‑08‑2023`) still contains two discrete periods. We should detect subsequent BROUGHT FORWARD rows within the same document and insert `PERIOD_BREAK` markers so the validator reports each period separately instead of a combined-statement warning.
2. **Explicit metadata reconciliation flag** – Now that the ledger overwrites header balances, add a validator note when we correct the metadata (e.g., “summary box disagreed by £120, corrected from ledger”) so reviewers know why a header changed.
3. **Focused regression set** – Capture a minimal fixture set (legacy, select-account short statement, FX-heavy statement) so future parser tweaks can run a small targeted test suite without reprocessing all 80 PDFs.

With the layout/metadata fixes above the existing dataset reconciles 100%; new edge cases should be addressed with targeted fixtures rather than broad heuristics. EOF
