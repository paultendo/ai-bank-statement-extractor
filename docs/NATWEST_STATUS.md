# NatWest Parser Status (November 2025)

## Scope
- Statements under `statements/Y Jones` mix two NatWest layouts:
  1. **Old Format (pre-mid 2023)** – Table layout with `Date | Type | Description | Paid in | Paid out | Balance`. The PDF text flow has the type column sometimes on the next line, and "BROUGHT FORWARD" lines change column alignment.
  2. **New Format (post-mid 2023)** – More consistent, mostly Format A/B we already support.

## Current Behaviour
- Parser auto-detect chooses Format B for the "Type" column statements. It assumes:
  - Type tokens appear either on their own line (indented) or immediately after the date.
  - Amount columns line up enough to rely on threshold-based position detection.
- Issues arise in older statements:
  - The date and type frequently appear on the same line, but there is trailing text before the type keyword, so our regex misses it. Then `current_type` stays `None`, and downstream heuristics can't infer direction.
  - Lines like "BROUGHT FORWARD" include legacy balance values inside the description; the parser interprets the embedded number as Money In (because of the dash heuristics), and Money Out stays zero.
  - For multi-line descriptions, we combine rows but still rely purely on column positions + dash detection to classify In/Out. That fails when layout shifts (common in the old PDF design).
  - Result: Many statements show warnings like "Balance mismatch at transaction 1..." and the statement-level reconciliation fails. In regression runs, ~42/80 statements present issues.

## Work Done So Far
- Added `_infer_format_b_direction()` to force In vs Out based on known keywords in the type/description. Helps when two amounts appear (Paid In / balance) but column detection fails.
- Tweaked Type regex to look within the same line after the date token so we capture "ATM TRANSACTION" etc.
- These fixes address cases from other folders (e.g., Selena, Sivachanthiran), but Y Jones statements still fail because the parser can't see the type token reliably and the BROUGHT FORWARD/Interest lines have embedded balances that trip the heuristics.

## Next Steps
1. **Robust Type Capture**
   - After matching a date, scan the remainder of the line for known type keywords even if other text precedes it (e.g., newline spacing, manual spaces). The `inline_type_pattern` should skip whitespace and allow for digits/commas before the type keyword.
   - When no type is found on the date line, look ahead (next line) before resetting `current_type`.

2. **BROUGHT FORWARD Handling**
   - When description contains "BROUGHT FORWARD", treat the line as a balance-only row: set `money_in` and `money_out` to 0, only set `balance`. Do not read amounts embedded inside the description.
   - Similar logic for "BANK INTEREST", "DAILY OD INT", etc., where NatWest prints the new balance within the description column.

3. **Column-Independent Amount Classification**
   - For Format B, rely primarily on keywords and signs rather than column thresholds, especially when only two numeric tokens exist. If a line contains "DEBIT CARD" (or other debit cues) and two numbers, treat the smaller value as Paid Out and the larger as Balance when classification is ambiguous.

4. **Regression Harness**
   - Add a targeted regression suite for Y Jones statements (maybe 2-3 sample PDFs covering 2019, early 2020, mid 2023) to ensure future parser tweaks keep both formats stable.

Once these are in place, re-run `/statements/Y Jones` and expect 0 warnings. EOF
