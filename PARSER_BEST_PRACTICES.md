# Bank Statement Parser Best Practices

## Learned from Real-World Implementation

This document captures critical patterns and pitfalls discovered during implementation of multiple bank parsers.

---

## 1. Dynamic Column Position Detection ⚠️ CRITICAL

### The Problem

**Never assume column positions are consistent across all pages of a PDF statement.**

Many banks (including Santander) use different layouts on different pages:
- Page 1: Wide margins, detailed header → columns at positions 104, 118, 137
- Pages 2+: Narrow margins, compact header → columns at positions 79, 94, 117

### The Symptoms

- ✅ Transaction-to-transaction balance reconciliation passes
- ❌ Statement totals are completely wrong (often 2x or 0.5x actual)
- ❌ Many "Money In" transactions classified as "Money Out" or vice versa
- ❌ Error appears mid-statement when reaching page 2

### The Solution

**Re-detect column positions on EVERY page header**, not just once at the start:

```python
# BAD: Detect once at start
header_pattern = re.compile(r'Money\s+in.*Money\s+out.*Balance')
for i, line in enumerate(lines):
    if i == 0 and header_pattern.search(line):
        money_in_start = line.find('Money in')
        money_out_start = line.find('Money out')
        threshold = (money_in_start + money_out_start) // 2
        # This threshold is used for ALL transactions - WRONG!

# GOOD: Update on every header
column_positions = {'threshold': 117}  # Default for page 1

for i, line in enumerate(lines):
    if header_pattern.search(line):  # Header found - update positions
        money_in_match = re.search(r'Money\s+in', line)
        money_out_match = re.search(r'Money\s+out', line)

        if money_in_match and money_out_match:
            money_in_start = money_in_match.start()
            money_out_start = money_out_match.start()
            threshold = (money_in_start + money_out_start) // 2

            # Update for THIS page's transactions
            column_positions['threshold'] = threshold
            logger.debug(f"Page {page_num}: Updated threshold to {threshold}")
```

### When to Apply

Use dynamic column detection when:
- ✅ Using `pdftotext -layout` flag (preserves visual spacing)
- ✅ Parser uses position-based classification (e.g., `if pos < threshold`)
- ✅ Statement has multiple pages
- ✅ Bank uses different headers/margins on different pages

### Affected Parsers

- **Santander**: ✅ Fixed - dynamic column detection implemented
- **HSBC**: ✅ Safe - already implements dynamic column detection (pre-scan + header updates)
- **NatWest**: ✅ Safe - already implements dynamic column detection (handles both column orders)
- **Barclays**: ✅ Fixed - dynamic column detection implemented (pre-scan + header updates)
- **Halifax**: ✅ Safe - doesn't use position-based classification
- **Monzo**: ✅ Safe - uses pattern matching, not positions

---

## 2. Boundary Conditions in Threshold Comparisons

### The Problem

Off-by-one errors when amounts fall exactly on column boundaries.

### Example from Santander

```
Page 2 threshold: 89 (midpoint between "Money in" at 82 and "Money out" at 96)
Transaction: "PRIMARK credit" with amount at position 89

if txn_pos < 89:      # WRONG: 89 is not < 89, classified as OUT
if txn_pos <= 89:     # CORRECT: 89 <= 89, classified as IN
```

### The Rule

Always use **inclusive comparisons** (`<=` or `>=`) when amounts could fall exactly on boundaries:

```python
# Calculate threshold as midpoint
threshold = (money_in_start + money_out_start) // 2

# Use <= to include boundary cases in "money in" column
if txn_amt_pos <= threshold:
    return txn_amt, None, balance  # Money in
else:
    return None, txn_amt, balance  # Money out
```

---

## 3. State Management After Transaction Emission

### The Problem

Failing to reset parser state after emitting a complete transaction leads to double-counting.

### Example from Santander (Before Fix)

```python
if balance is not None:
    # Emit transaction
    transactions.append(transaction)
    # BUG: Didn't reset current_description!
    # Next non-date line thinks it's a continuation

else:
    current_description = [description]  # Only set if incomplete
```

This caused the next line to be processed as a "continuation" even though the previous transaction was already complete.

### The Solution

**Always reset state after emitting**:

```python
if balance is not None:
    # Emit complete transaction
    transactions.append(transaction)

    # CRITICAL: Reset state
    current_description = []
    current_date = None  # If needed

else:
    # Incomplete - buffer for continuation
    current_description = [description]
```

---

## 4. Skip Statement Summary Lines

### The Problem

Statement summary lines (totals, opening/closing balances) can be parsed as transactions if not explicitly filtered.

### Example from Santander

```
Your account summary for 9th Jan 2024 to 7th Feb 2024
Balance brought forward from 8th Jan Statement          £22.67
Total money in:                                      £5,341.71
Total money out:                                    -£5,323.10
Your balance at close of business 7th Feb 2024          £41.28
```

These lines have amounts and can match transaction patterns!

### The Solution

Explicitly skip summary markers:

```python
# Skip statement summary lines
if any(marker in line for marker in [
    'Balance brought forward',
    'Total money in:',
    'Total money out:',
    'Your balance at close of business',
    'Balance carried forward to next statement',
    'Opening balance',
    'Closing balance'
]):
    continue
```

### Bank-Specific Markers to Skip

- **Santander**: "Total money in/out", "Your balance at close of business"
- **HSBC**: "Opening Balance", "Closing Balance", "Payments In/Out"
- **Barclays**: "Total paid in", "Total paid out", "Balance brought forward"
- **NatWest**: "Total Credits", "Total Debits"
- **Monzo**: Generally doesn't have summary lines in transaction section

---

## 5. Foreign Currency Amount Filtering

### The Pattern

When FX metadata appears inline with GBP amounts:

```
Amount: EUR 109.50. Conversion                    -93.58        6.98
```

Standard amount regex `[\d,]+\.\d{2}` will find THREE amounts: `109.50`, `93.58`, `6.98`.
We want only the GBP amounts: `93.58` (transaction) and `6.98` (balance).

### The Solution

Filter foreign currency amounts BEFORE extracting:

```python
# From base_parser.py (added during Monzo FX work)
def _filter_foreign_currency_amounts(self, line: str, amount_pattern: re.Pattern) -> List[str]:
    """Extract only GBP amounts, filtering out EUR/USD."""
    if not re.search(r'Amount:\s*(USD|EUR)\s*-?[\d,]+', line, re.IGNORECASE):
        return amount_pattern.findall(line)  # No FX, extract all

    # Filter out foreign currency
    filtered_line = re.sub(
        r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?',
        'Amount: [FOREIGN]',
        line,
        flags=re.IGNORECASE
    )

    return amount_pattern.findall(filtered_line)
```

This is now available as a **base parser utility method** for all parsers to use.

---

## 6. Testing with Statement Totals

### The Metrics

**Two levels of validation required:**

1. **Transaction-to-transaction reconciliation** (micro)
   - Each transaction's balance = previous balance + money_in - money_out
   - Catches parsing errors, wrong amounts, missing transactions

2. **Statement totals reconciliation** (macro)
   - Sum of all money_in = statement's "Total money in"
   - Sum of all money_out = statement's "Total money out"
   - Catches systemic issues (double-counting, wrong column classification)

### The Gotcha

❌ **DON'T** sum the Excel file with pandas - it includes the TOTALS row!

```python
# WRONG: Includes totals row, appears 2x actual
df = pd.read_excel('statement.xlsx')
total_in = df['Money In'].sum()  # Oops!

# CORRECT: Read from parser result directly
result = parser.parse_text(text, start, end)
total_in = sum(txn.money_in for txn in result.transactions)
```

Or exclude the totals row:

```python
df = pd.read_excel('statement.xlsx')
totals_row_idx = df[df['Date'] == 'TOTALS'].index[0]
transactions_only = df.iloc[:totals_row_idx]
total_in = transactions_only['Money In'].sum()
```

### Success Criteria

✅ Transaction-to-transaction: 100% reconciliation
✅ Statement totals: Within £0.50 tolerance
✅ Confidence: 95%+ average

---

## 7. Multi-Line Transaction Handling

### The Pattern

Many banks split long descriptions across lines:

```
9th Jan    BILL PAYMENT VIA FASTER PAYMENT TO SIV LLOYDS REFERENCE HOUSEHOLD BILLS ,    41.00    4.37
           MANDATE NO 229
```

### Key Principles

1. **First line has amounts** (transaction amount + balance)
2. **Continuation lines have NO amounts** (just description text)
3. **No date on continuation lines** (spaces or indentation)
4. **Continuation lines immediately follow** the first line

### Implementation Pattern

```python
if date_match:
    # New transaction starts
    money_in, money_out, balance = extract_amounts(line)

    if balance is not None:
        # Complete on one line - emit immediately
        emit_transaction()
        current_description = []  # Reset!
    else:
        # Incomplete - wait for continuation
        current_description = [description]

else:
    # No date - check if continuation
    if current_description:  # We're in a multi-line transaction
        money_in, money_out, balance = extract_amounts(line)

        if balance is not None:
            # Continuation has amounts - complete it
            current_description.append(line.strip())
            emit_transaction()
            current_description = []
        else:
            # Just text - buffer it
            current_description.append(line.strip())
```

---

## 8. Page Break Handling

### The Pattern

Transactions can span page breaks:

```
Page 1:
16/08/2024    TRANSACTION NAME    -93.58    6.98
--- FOOTER ---
--- NEW PAGE HEADER ---
Page 2:
              rate: 1.170122.
```

### Solution

**Don't special-case page breaks** - treat them like any other multi-line transaction:

1. Emit transaction when amounts are complete (on page 1)
2. Skip footer/header lines
3. Continuation line (if any) has no amounts → gets filtered as non-transaction line

### Critical: Footer Detection

Be cautious with footer patterns - don't skip lines that might be transaction continuations:

```python
# Be specific with footer patterns
footer_pattern = re.compile(
    r'(Page \d+ of \d+|Account number:|Statement number:|'
    r'santander\.co\.uk|HSBC UK|Continued on reverse)',
    re.IGNORECASE
)

if footer_pattern.search(line):
    # But don't skip if it looks like transaction data
    if not re.search(r'Amount:|rate:|\d{2}/\d{2}/\d{4}', line):
        continue
```

---

## 9. Ordinal Date Formats

### The Pattern

Some banks (Santander) use ordinal suffixes:
- `1st Jan`, `2nd Feb`, `3rd Mar`, `4th Apr`, `21st Jan`, `22nd Feb`, `23rd Mar`

### The Problem

Standard `strptime` doesn't handle ordinals:

```python
datetime.strptime("9th Jan", "%d %b")  # ValueError!
```

### The Solution

Use the `infer_year_from_period()` utility which handles ordinals:

```python
# From utils/date_parser.py
current_date = infer_year_from_period(
    "9th Jan",  # Handles ordinals internally
    statement_start_date,
    statement_end_date
)
```

Or strip ordinals before parsing:

```python
date_str = re.sub(r'(\d+)(st|nd|rd|th)', r'\1', date_str)
# "9th Jan" → "9 Jan"
```

---

## Checklist for New Bank Parsers

When implementing a new bank parser, verify:

- [ ] **Dynamic column detection** - Do column positions change between pages?
- [ ] **Boundary conditions** - Use `<=` not `<` for threshold comparisons
- [ ] **State reset** - Clear all state variables after emitting transactions
- [ ] **Summary line filtering** - Skip "Total", "Balance brought forward", etc.
- [ ] **Foreign currency** - Use `_filter_foreign_currency_amounts()` if FX present
- [ ] **Multi-line transactions** - Test with transactions that span 2+ lines
- [ ] **Page breaks** - Test with transactions that span page boundaries
- [ ] **Statement totals** - Verify extracted sum matches statement's totals
- [ ] **Edge cases** - Test with £0.00 transactions, overdrafts, refunds

---

## Quick Reference: Parser Debugging

When extracted totals don't match statement:

1. **Check if double-counting**: Are totals exactly 2x?
   → State not reset after emitting transactions

2. **Check if wrong classification**: Money In high, Money Out low (or vice versa)?
   → Column threshold not updating per page, or boundary condition bug

3. **Check if missing transactions**: Totals much lower than expected?
   → Too aggressive footer filtering, or date pattern too narrow

4. **Check if including summary**: Totals slightly too high?
   → Not skipping statement summary lines

5. **Verify you're not summing the Excel totals row**: Is pandas sum 2x?
   → Exclude rows where Date == 'TOTALS'

---

**Last Updated**: October 2024 (Santander implementation)
**Next Review**: When implementing next bank parser
