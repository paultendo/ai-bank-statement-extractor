# Monzo Bank Support Status

## Current Status: ✅ Native PDF Support Verified (combined statement)

### Regression Run (2025-11-08)
```
python3 -m src.cli extract "statements/monzo-bidmead.pdf" --output output/monzo_bidmead.xlsx
```

- Detected bank: **Monzo** (personal account + pots, combined statement).
- Extraction path: `pdftotext` → Monzo parser.
- Statement metadata: Account 52167010, combined range **1 May 2024 – 31 Oct 2024** (12 periods).
- Transactions parsed: **1,035** (after internal period splits), Money In £27,354.56, Money Out £27,060.97, balances reconciled.
- Excel export: `output/monzo_bidmead.xlsx`, confidence 100 %. Includes a new **Pot Summaries** sheet with period, balance, and total in/out per pot.

### Observations
- Parser logged expected `DATE-SPLIT` markers while inferring years across periods; no intervention required.
- Pot statements (House Fund, Holiday, etc.) parsed cleanly into structured summaries even when they reported “There were no transactions during this period.”
- Totals row still only shows Money In/Out (balance column blank) – cosmetic improvement for later.

### Next Steps
- Add this combined Monzo PDF to the smoke/regression suite once scripted.
- Collect a single-month Monzo statement (non-combined) for variety.
- Keep an eye on the exporter totals row formatting (optional UI polish).
