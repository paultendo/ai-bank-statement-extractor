# Universal Parser Patterns and Best Practices

## Overview

This document identifies universal patterns across all bank statement parsers and provides guidance for:
1. **Recognizing** patterns that should be extracted to shared utilities
2. **Refactoring** existing parsers to use shared methods
3. **Implementing** new parsers with best practices from the start

## Universal Patterns (Already Extracted)

### 1. Cross-Year Date Handling ✅
**Status**: Fully extracted to `src/utils/date_parser.py`

**Used by**: 8/11 parsers (Barclays, HSBC, NatWest, Santander, Halifax, TSB, Monzo, Nationwide)

**Function**: `infer_year_from_period(date_str, period_start, period_end, date_formats)`

**Purpose**: Handles statements spanning year boundaries (e.g., Jan 2025 statement with Dec 2024 transactions)

**Example Usage**:
```python
if statement_start_date and statement_end_date:
    current_date = infer_year_from_period(
        date_str,
        statement_start_date,
        statement_end_date,
        date_formats=self.config.date_formats
    )
else:
    current_date = parse_date(date_str, self.config.date_formats)
```

**Key Features**:
- Detects if date string already contains year (2-digit or 4-digit)
- Tries both period start and end years (handles leap year issues like Feb 29)
- Cross-year detection: early year statement (Jan/Feb) with late year transaction (Nov/Dec)
- Falls back to period start year by default

---

### 2. Confidence Scoring ✅
**Status**: Fully extracted to `BaseTransactionParser._calculate_confidence()`

**Used by**: All 11 parsers (100% coverage)

**Purpose**: Scores transaction extraction quality (0-100) based on data completeness

**Scoring Logic**:
- Deduct 30 points: No date
- Deduct 20 points: No description or too short (<3 chars)
- Deduct 10 points: Zero balance
- Deduct 25 points: No money in AND no money out
- Bonus 5 points: Complete financial data (amount + balance)
- Bonus 5 points: Reasonable description length (10-200 chars)

**Example Usage**:
```python
confidence = self._calculate_confidence(
    date=current_date,
    description=description,
    money_in=money_in,
    money_out=money_out,
    balance=balance
)
```

---

### 3. Skip Patterns (Footer/Header Filtering) ✅
**Status**: Extracted to `BaseTransactionParser.UNIVERSAL_SKIP_PATTERNS` + `_is_skip_line()`

**Used by**: All 11 parsers (100% coverage)

**Purpose**: Filter out non-transaction lines (page markers, regulatory text, metadata)

**Universal Patterns** (shared across all banks):
```python
UNIVERSAL_SKIP_PATTERNS = [
    # Page markers
    r'Page \d+ of \d+',
    r'^\s*Page \d+\s*$',
    r'--- Page \d+ ---',
    r'Continued on next page',

    # Regulatory/compliance text
    r'Financial Conduct Authority',
    r'Financial Services Compensation',
    r'Prudential Regulation Authority',
    r'Prudential Regulation',
    r'FSCS',
    r'authorised by the',
    r'regulated by the',

    # Account metadata
    r'Sort code',
    r'Account number',
    r'Account no',
    r'Statement no:',
    r'Statement date:',
    r'BIC:',
    r'IBAN:',
    r'Swift',

    # Bank names and addresses
    r'Registered Office',
    r'Head Office',
    r'www\.',
    r'\.com',
    r'\.co\.uk',

    # Summary/totals lines
    r'^\s*TOTALS\s*$',
    r'Total deposits',
    r'Total outgoings',
    r'Total withdrawals',
    r'Total payments in',
    r'Total payments out',

    # Balance markers (when not part of transaction)
    r'^Balance on \d{1,2}',
    r'Opening balance',
    r'Closing balance',
]
```

**Bank-Specific Patterns**: Add to YAML config under `skip_patterns:`

**Example Usage**:
```python
# In parser loop
if self._is_skip_line(line):
    idx += 1
    continue
```

**TSB Example** ([tsb.yaml:72-83](../data/bank_templates/tsb.yaml)):
```yaml
skip_patterns:
  - "TSB Bank plc"
  - "DV015004A-\\d+-E-TSBS"  # Document reference
  - "^\\s*Money in\\s*$"     # Bare "Money in" (header/summary)
  - "^\\s*Money out\\s*$"    # Bare "Money out" (header/summary)
  - "Sort Code:\\s*\\d{2}-\\d{2}-\\d{2}"
  - "Account Number:\\s*\\d+"
  - "Statement number:"
  - "Easy Saver"
  - "Your Transactions"
  - "^\\s+\\d{2}/\\d{2}/\\d{4}\\s*$"  # Bare date line
  - "covered by these schemes"
```

**Refactoring Steps**:
1. Add bank-specific patterns to YAML config under `skip_patterns`
2. Replace inline skip pattern list with `self._is_skip_line(line)`
3. Test to ensure no transactions are accidentally filtered

---

### 4. Dynamic Column Detection ✅
**Status**: Extracted to `BaseTransactionParser._detect_column_thresholds()` + `_update_column_thresholds_from_header()`

**Used by**: 6 parsers (Barclays, HSBC, NatWest, Santander, TSB, Nationwide)

**Purpose**: Detect column positions from headers instead of hardcoding positions

**Why It's Universal**:
- PDF extraction positions vary between statement versions
- Multi-month PDFs may have different layouts on different pages
- Consolidated statements often have layout changes

**Two-Phase Approach**:

#### Phase 1: Pre-Scan (Before Processing)
Finds first header and sets initial thresholds:

```python
# At start of parse_transactions()
lines = text.split('\n')

# Pre-scan for column positions
thresholds = self._detect_column_thresholds(
    lines,
    column_names=["Money out", "Money in", "Balance"],
    column_pairs=[("Money out", "Money in"), ("Money in", "Balance")],
    default_thresholds={'money_out_threshold': 75, 'money_in_threshold': 95}
)

MONEY_OUT_THRESHOLD = thresholds['money_out_threshold']
MONEY_IN_THRESHOLD = thresholds['money_in_threshold']
```

#### Phase 2: Online Updates (During Processing)
Re-detect on each page for multi-layout PDFs:

```python
# In main processing loop
updated_thresholds = self._update_column_thresholds_from_header(
    line,
    column_names=["Money out", "Money in", "Balance"],
    column_pairs=[("Money out", "Money in"), ("Money in", "Balance")]
)

if updated_thresholds:
    MONEY_OUT_THRESHOLD = updated_thresholds['money_out_threshold']
    MONEY_IN_THRESHOLD = updated_thresholds['money_in_threshold']
    logger.debug(f"Updated thresholds: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")
    continue  # Skip the header line itself
```

**Threshold Calculation**:
For columns `[A, B, C]` with pairs `[(A,B), (B,C)]`:
- `A_threshold` = midpoint between A and B column positions
- `B_threshold` = midpoint between B and C column positions

**Amount Classification**:
```python
for amt_str, pos in amounts_with_pos:
    amt_val = parse_currency(amt_str)

    if pos <= MONEY_OUT_THRESHOLD:
        money_out = amt_val
    elif pos <= MONEY_IN_THRESHOLD:
        money_in = amt_val
    else:
        balance = amt_val
```

**Nationwide Example** ([nationwide_parser.py:66-88](../src/parsers/nationwide_parser.py)):
```python
# Pre-scan for initial thresholds
MONEY_OUT_THRESHOLD = 104  # Default
MONEY_IN_THRESHOLD = 123   # Default

if header_line_idx is not None:
    header_line = lines[header_line_idx]
    money_out_match = re.search(r'£\s*Out', header_line, re.IGNORECASE)
    money_in_match = re.search(r'£\s*In', header_line, re.IGNORECASE)
    balance_match = re.search(r'£\s*Balance', header_line, re.IGNORECASE)

    if money_out_match and money_in_match and balance_match:
        MONEY_OUT_THRESHOLD = money_in_match.start() - 1
        MONEY_IN_THRESHOLD = balance_match.start() - 1
        logger.info(f"Detected Nationwide column thresholds from header: Out<={MONEY_OUT_THRESHOLD}, In<={MONEY_IN_THRESHOLD}")
```

---

### 5. Balance Validation & Auto-Correction ✅
**Status**: Extracted to `BaseTransactionParser._validate_and_correct_balance()`

**Used by**: 5 parsers (Barclays, HSBC, NatWest, Halifax, TSB)

**Purpose**: Detect and fix Money In/Out direction swaps using balance reconciliation

**Problem**: PDFs sometimes misalign amounts with columns, causing:
- Money IN to be parsed as Money OUT (and vice versa)
- Balance mismatch: `opening + in - out ≠ closing`

**Solution**: Direction Swap Logic
```python
balance_change = current_balance - previous_balance  # Actual change
calculated_change = money_in - money_out             # Expected change

if abs(calculated_change - balance_change) > 0.01:
    # Try swapping
    error_before = abs(calculated_change - balance_change)
    error_after = abs((money_out - money_in) - balance_change)

    if error_after < error_before:
        # Swap improves accuracy
        money_in, money_out = money_out, money_in
```

**Example Usage**:
```python
for i, transaction in enumerate(transactions):
    prev_balance = transactions[i-1].balance if i > 0 else opening_balance

    transaction = self._validate_and_correct_balance(
        transaction,
        prev_balance=prev_balance,
        allow_direction_swap=True
    )

    transactions[i] = transaction
```

**HSBC Example** ([hsbc_parser.py:297-314](../src/parsers/hsbc_parser.py)):
```python
# BALANCE VALIDATION: Auto-correct based on balance change
if balance is not None and len(transactions) > 0:
    prev_balance = transactions[-1].balance
    balance_change = balance - prev_balance
    calculated_change = money_in - money_out

    if abs(calculated_change - balance_change) > 0.01:
        # Check if swapping would improve the match
        error_before = abs(calculated_change - balance_change)
        calculated_after_swap = money_out - money_in
        error_after = abs(calculated_after_swap - balance_change)

        # Only swap if it actually improves things
        if error_after < error_before:
            logger.debug(f"Correcting HSBC direction...")
            money_in, money_out = money_out, money_in
```

---

## Bank-Specific Patterns (Not Universal)

### 1. Accessibility Text Filtering (Lloyds Only)
**Used by**: 1 parser (Lloyds)

**Pattern**: Filter white-on-white text and tiny fonts for screen readers

```python
chars = [
    c for c in page.chars
    if not (
        c.get('non_stroking_color') == (1.0, 1.0, 1.0)  # White text
        or c.get('size', 9.0) < 1.0  # Tiny text (normal is ~9.0)
    )
]
```

**Why Not Universal**: Only Lloyds PDFs have this specific issue. Other banks extract cleanly.

**Recommendation**: Keep in Lloyds parser, don't extract.

---

### 2. Info Box Filtering (Nationwide Only)
**Used by**: 1 parser (Nationwide)

**Pattern**: Exclude amounts from right-side summary box

```python
INFO_BOX_START = 150

amounts_with_pos = []
for match in amount_pattern.finditer(line):
    amt_str = match.group(1)
    pos = match.start()
    if pos < INFO_BOX_START:  # Skip info box
        amounts_with_pos.append((amt_str, pos))
```

**Why Not Universal**: Only Nationwide has this layout. Other banks have different formats.

**Recommendation**: Keep in Nationwide parser.

---

## Right-Aligned Amount Detection

**Used by**: 3 parsers (Barclays, TSB, Nationwide)

**Pattern**: Check where amounts **END**, not where they START

**Problem**: Bank statement amounts are typically right-aligned:
```
Money Out    Money In    Balance
   45.67      100.00     1254.33
  145.67        0.00     1108.66
```

If "Money In" column starts at position 85, amount "100.00" (6 chars) starts at position 79 but **ends** at position 85.

**Wrong Approach** (check start position):
```python
if pos <= 85:  # Incorrectly classifies 100.00 as Money Out
    money_out = amt
```

**Right Approach** (check end position):
```python
amt_end = pos + len(amt_str)
if amt_end <= 85:  # Correctly classifies based on right edge
    money_out = amt
```

**Example** - Barclays ([barclays_parser.py:456-459](../src/parsers/barclays_parser.py)):
```python
# Use the END position of the amount for better accuracy
amt_end = pos + len(amt_str)

# Classify based on column ranges:
if amt_end >= 105:  # Balance column
    balance = amt
elif amt_end >= 85:  # Money in column
    money_in = amt
else:  # Money out column
    money_out = amt
```

**Recommendation**: Add `use_end_position` parameter to column detection utility:
```python
def classify_amount_by_position(
    position: int,
    amount_str: str,
    thresholds: dict,
    use_end_position: bool = False
):
    check_pos = (position + len(amount_str)) if use_end_position else position
    # ... threshold comparison
```

---

## Refactoring Checklist

When refactoring an existing parser to use universal patterns:

### Phase 1: Skip Patterns
- [ ] Extract bank-specific skip patterns to YAML config under `skip_patterns`
- [ ] Replace inline skip pattern loops with `self._is_skip_line(line)`
- [ ] Test: Verify same number of transactions extracted before/after

### Phase 2: Column Detection
- [ ] Identify column names (e.g., "Money out", "Money in", "Balance")
- [ ] Define column pairs for threshold calculation
- [ ] Add `_detect_column_thresholds()` call before main loop
- [ ] Add `_update_column_thresholds_from_header()` in main loop for multi-page support
- [ ] Replace hardcoded thresholds with dynamic thresholds
- [ ] Test: Verify amounts classified correctly for different statement layouts

### Phase 3: Balance Validation
- [ ] Add `_validate_and_correct_balance()` call after each transaction parse
- [ ] Pass previous balance for validation
- [ ] Test: Verify balance reconciliation passes after refactoring

### Phase 4: Cross-Year Dates
- [ ] Replace hardcoded year logic with `infer_year_from_period()`
- [ ] Pass statement_start_date and statement_end_date
- [ ] Test: Verify dates correct for multi-month statements (Jan 2025 with Dec 2024)

---

## New Parser Implementation Guide

When implementing a new bank parser, follow this checklist:

### 1. Parser Structure
```python
class NewBankParser(BaseTransactionParser):
    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        lines = text.split('\n')
        transactions = []

        # Pre-scan for column positions (if columnar format)
        thresholds = self._detect_column_thresholds(
            lines,
            column_names=["Column1", "Column2", "Column3"],
            column_pairs=[("Column1", "Column2"), ("Column2", "Column3")],
            default_thresholds={'col1_threshold': 50, 'col2_threshold': 80}
        )

        # Main parsing loop
        for line in lines:
            # Skip non-transaction lines
            if self._is_skip_line(line):
                continue

            # Update thresholds if new header found (multi-page)
            updated = self._update_column_thresholds_from_header(line, ...)
            if updated:
                thresholds.update(updated)
                continue

            # Parse transaction...
            # ...

            # Use cross-year date handling
            if statement_start_date and statement_end_date:
                date = infer_year_from_period(date_str, statement_start_date, statement_end_date)

            # Calculate confidence
            confidence = self._calculate_confidence(date, description, money_in, money_out, balance)

            # Create transaction
            txn = Transaction(...)

            # Validate balance
            txn = self._validate_and_correct_balance(
                txn,
                prev_balance=transactions[-1].balance if transactions else None
            )

            transactions.append(txn)

        return transactions
```

### 2. YAML Configuration
```yaml
newbank:
  identifiers:
    - "New Bank Name"
    - "newbank.co.uk"

  date_formats:
    - "%d/%m/%Y"
    - "%d %b %Y"

  # Bank-specific skip patterns (universal ones automatic)
  skip_patterns:
    - "New Bank PLC"
    - "Specific footer text"
    - "Account type: Savings"

  transaction_types:
    transfer:
      - "TRANSFER"
      - "TFR"
    direct_debit:
      - "DIRECT DEBIT"
      - "DD"
    # ...

  validation:
    balance_tolerance: 0.01
    enforce_date_order: true
    require_description: true
```

### 3. Testing
- [ ] Test with single-page statement
- [ ] Test with multi-page statement
- [ ] Test with cross-year statement (Dec/Jan boundary)
- [ ] Test with consolidated multi-month PDF
- [ ] Verify balance reconciliation passes
- [ ] Check confidence scores are reasonable (>80% for good extractions)

---

## Summary Table: Pattern Usage by Parser

| Pattern | Barclays | HSBC | Lloyds | Monzo | NatWest | Santander | Halifax | TSB | Nationwide | Credit Ag | LCL |
|---------|----------|------|--------|-------|---------|-----------|---------|-----|-----------|-----------|-----|
| 1. Cross-year dates | ✓ | ✓ | - | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ? | ? |
| 2. Confidence scoring | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 3. Skip patterns | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ | ✓ |
| 4. Dynamic columns | ✓ | ✓ | - | - | ✓ | ✓ | - | ✓ | ✓ | - | - |
| 5. Balance validation | ✓ | ✓ | - | - | ✓ | - | ✓ | - | - | - | - |
| 6. Right-aligned check | ✓ | - | - | - | - | - | - | ✓ | ✓ | - | - |
| 7. Accessibility filter | - | - | ✓ | - | - | - | - | - | - | - | - |
| 8. Info box filter | - | - | - | - | - | - | - | - | ✓ | - | - |

**Legend**:
- ✓ = Currently using this pattern
- - = Not applicable or not using
- ? = Not yet analyzed

---

## Benefits of Universal Patterns

1. **Reduced Duplication**: ~500-800 lines of code deduplicated across parsers
2. **Easier Maintenance**: Fix bugs once, all parsers benefit
3. **Consistency**: All parsers handle edge cases the same way
4. **Faster Development**: New parsers require less boilerplate
5. **Better Testing**: Shared utilities can have comprehensive unit tests
6. **Knowledge Sharing**: Patterns discovered in one parser benefit all others

---

## Future Enhancements

1. **Multiline Description Extraction**: Already exists in base parser, ensure consistent usage
2. **Foreign Currency Filtering**: `_filter_foreign_currency_amounts()` method available
3. **Amount Position Filtering**: Add `_filter_amounts_by_position()` wrapper
4. **Transaction Type Detection**: Already in base parser via `_detect_transaction_type()`

---

**Document Version**: 1.0
**Last Updated**: February 2025
**Maintained By**: Bank Statement Extractor Team
