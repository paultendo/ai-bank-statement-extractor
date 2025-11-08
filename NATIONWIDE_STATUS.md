# Nationwide Support Status

## Current Status: ⚠️ Partial (multi-statement PDF parses but balance check fails)

### Regression Run (Marsh Bankstatements up to April 2024)
```
python3 -m src.cli extract "statements/Marsh Bankstatements up to April 2024.pdf" \
  --output output/nationwide_marsh.xlsx \
  --json output/nationwide_marsh.json
```

- Detected bank: **Nationwide** (FlexAccount, combined statements 132–144).
- Extraction path: `pdftotext` with Nationwide bbox crop (x1=450) to strip the right-hand info box.
- Transactions parsed: **695** covering **1 Jan 2023 – 30 Dec 2023** (Money In £5,116.74, Money Out £5,359.83).
- Statement metadata defaults to the first statement date (23 March 2023) and is refined from transaction dates.
- Excel export + JSON snapshot written to `output/nationwide_marsh.*`.
- **Balance validation fails** (opening £8.69, closing £144.03) because the PDF bundles 12 monthly statements without clear period breaks—we currently treat it as a single statement, so balances jump when each new “Balance from statement …” line appears.

### Observations
- Nationwide PDFs omit spaces between digits and month names (e.g., `24Feb`). The parser now normalizes these before date matching.
- Header metadata is sparse; we introduced a more forgiving `statement_date` regex and whitespace normalizer to capture strings like `Statementdate: 23March 2023`.
- We record every “Balance from statement …” line but simply skip it; to reconcile multi-statement PDFs we should insert period-break markers (similar to the Monzo implementation) whenever we hit these lines.
- Pages past December 2023 still exist (statements 143/144), but they’re dominated by info-box summaries; actual 2024 transaction lines are interleaved with `Statementdate …` text, so we need to confirm whether bbox cropping is trimming any of them.

### Next Steps
1. Teach the Nationwide parser to detect `Balance from statement <n>` and insert synthetic `PERIOD_BREAK` markers so each monthly statement reconciles independently.
2. Verify whether the current bbox (x1=450) drops any 2024 transaction rows; adjust if necessary.
3. Once reconciliation passes, add this PDF to the smoke suite with per-period assertions.
