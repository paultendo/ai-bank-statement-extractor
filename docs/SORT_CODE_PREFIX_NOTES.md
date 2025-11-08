# UK Sort Code Prefix Notes

This file captures researched prefix → bank mappings so we have them handy when building new parsers. Only the ranges corresponding to implemented banks are wired into `BankConfigLoader.SORT_CODE_PREFIXES`; the rest live here until we add configs + regression tests.

| Prefix | Bank / Provider | Status | Reference |
|--------|-----------------|--------|-----------|
| 07-xx-xx | Nationwide Building Society | ✅ mapped | UK Payments allocations (legacy Building Societies)
| 08-xx-xx | Nationwide Building Society (secondary) | ✅ mapped | UK Payments allocations
| 09-xx-xx | Santander UK / ex-Abbey / Girobank | ✅ mapped | Santander help centre, UK sort code registers
| 11/12/15-xx-xx | Halifax (Bank of Scotland) | ✅ mapped | Lloyds Banking Group documentation
| 20-xx-xx | Barclays Bank UK PLC | ✅ mapped | Clearing House tables
| 30/31-xx-xx | Lloyds Bank / Bank of Scotland subsidiaries | ✅ mapped | Clearing House tables
| 40-xx-xx | HSBC UK Bank plc | ✅ mapped | Clearing House tables
| 50/60/61/62/83-xx-xx | NatWest & Royal Bank of Scotland | ✅ mapped | UK Payments allocations, NatWest docs
| 04-00-04 / 04-00-03 / other 04-00 ranges | Monzo Bank | ⏳ partially mapped (Monzo parser exists) | Monzo help article
| 04-00-75 | Revolut/Modulr GBP accounts | ⚪ planned | Wise sort code lookup, Revolut support
| 60-83-71 | Starling Bank | ⚪ planned | Starling help centre
| 60-84-07 | Chase UK (JPMorgan) | ⚪ planned | Sort code directory (NatWest clearing)
| 60-83-12 | Atom Bank | ⚪ planned | Sort code directory (NatWest clearing)
| 60-84-00 | Zopa Bank | ⚪ planned | Sort code directory (NatWest clearing)
| 82-xx-xx | Virgin Money (Clydesdale/Yorkshire) | ⚪ planned | Sort code directory (CYBG)

Legend:
- ✅ mapped = prefix currently used for automatic detection because we have a parser.
- ⏳ partially mapped = subset wired up; may expand once configs/tests improve.
- ⚪ planned = kept here for future work; not active in the loader.

When onboarding a new bank:
1. Confirm the prefix in an authoritative source (Payments Association, bank help centre, sort-code lookup).
2. Add or update the YAML config + parser/tests.
3. Move the prefix from "planned" to "mapped" in both this file and `BankConfigLoader.SORT_CODE_PREFIXES`.
