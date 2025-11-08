# TSB Parser Notes (Nov 2025)

## Issue Discovered
- `TSB Savings account - Mark Wilcox.pdf` produced 34 pseudo-transactions and failed the balance safety check.
- Root cause: the universal skip pattern (`Closing balance`) skipped the `STATEMENT CLOSING BALANCE` line before the parser could break, so the loop kept ingesting the FSCS footer text. The footer lines contained numbers, so they were misinterpreted as transactions.
- Header text on each page ("Statement number", "Easy Saver", etc.) also leaked into descriptions because the PDF merged words (e.g., `Statementnumber`), so the original skip regexes didn't match.

## Fix Implemented
1. **Closing/Opening handling moved ahead of skip logic** in `src/parsers/tsb_parser.py`. We now:
   - Detect `STATEMENT CLOSING BALANCE` before running `_is_skip_line`, ensuring we exit the loop immediately.
   - Capture `STATEMENT OPENING BALANCE` even if the line matches a skip pattern, and default the date to the statement-start when available.
2. **Skip patterns updated** in `data/bank_templates/tsb.yaml` to cover condensed text (`Statementnumber`, `Moneyin`, `FinancialServicesCompensation`, etc.), preventing FSCS blocks from entering descriptions.

## Result
- CLI run now parses **31 transactions**, outputs `output/tsb_mark.xlsx`, and reconciles balances with 100 % confidence:
  - Money In £2,700.00, Money Out £2,420.00, Closing £532.24.

## Future Enhancements
- If we need even cleaner text, pdfplumber supports `layout=True` and custom `x_tolerance`/`y_tolerance`; see `https://github.com/jsvine/pdfplumber` for the knobs.
- Add an automated regression test that loads this PDF and asserts:
  - Transactions == 31
  - Closing balance == £532.24
  - No description contains "Financial Services Compensation".
