# Learnings from Monzo FX Transaction Parsing

## Executive Summary

During the implementation of Monzo statement parsing, we discovered several patterns and edge cases that could benefit other bank parsers. This document captures those learnings and recommendations for generalizing them to the base parser.

## Key Issues Discovered

### 1. Date Pattern Matching Priority (HIGH PRIORITY)

**Problem**: When using a "pending state" pattern (waiting for year digit to complete date), overly greedy patterns can misinterpret the start of a NEW date line as completion of the PREVIOUS date.

**Monzo Specific Case**:
- Dates split across lines: `16/08/202` on line 1, `4` on line 2
- Year digit pattern: `^\s*(\d)(.*)$` matches ANY line starting with a digit
- When a new date line appears (`16/08/202        MERCHANT...`) while `pending_year_digit=True`, the `1` in `16/08/202` was matched as a year digit instead of recognizing it as a new date

**Impact**: Transactions were lost or merged incorrectly, causing ~16 missing transactions

**Fix Applied**: Always check for date patterns FIRST, even when in a pending state
```python
# ALWAYS check for date line first (even if pending_year_digit)
# This prevents misinterpreting date lines like "16/08/202..." as year digits
date_match = date_pattern.match(line)

if date_match:
    # ... handle new transaction
    continue

# Check for year's final digit (ONLY if no date match above)
if pending_year_digit:
    # ... complete previous date
```

**Generalization Recommendation**:
- ❌ **DO NOT generalize to base parser** - This is specific to Monzo's split-date layout
- ✅ **ADD as a documented pattern** in base_parser.py docstring
- ✅ **ADD as a warning** in developer guide: "If using multi-line date patterns, always prioritize new date detection over state completion"

### 2. Foreign Currency Amount Filtering (MEDIUM PRIORITY)

**Problem**: When FX metadata appears on the same line as GBP transaction data, naive amount extraction captures BOTH foreign currency amounts AND GBP amounts.

**Monzo Specific Cases**:

**Case A - FX info on date line**:
```
12/08/202        Amount: EUR 1.10. Conversion
```
Amount pattern finds `1.10` (EUR), but this is NOT the GBP transaction amount.

**Case B - FX info with GBP amounts on same line** (with `-layout` flag):
```
Amount: EUR -109.50. Conversion                         -93.58              6.98
```
Amount pattern finds `['-109.50', '-93.58', '6.98']` - need to filter out `-109.50` (EUR).

**Fix Applied**: Filter foreign currency amounts before extracting GBP amounts
```python
# Filter out foreign currency amounts first
line_for_amounts = re.sub(
    r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?',
    'Amount: [FOREIGN]',
    line,
    flags=re.IGNORECASE
)
amounts_in_line = amount_pattern.findall(line_for_amounts)
```

**Generalization Recommendation**:
- ✅ **CAN be generalized** as a utility method in base parser
- ✅ **Useful for**: Barclays, HSBC, NatWest (all have FX transactions)
- ⚠️ **Caveat**: Only apply when FX metadata is detected (don't filter all EUR/USD mentions)

**Proposed Base Parser Addition**:
```python
def _filter_foreign_currency_amounts(self, line: str, amount_pattern: re.Pattern) -> List[str]:
    """
    Extract GBP amounts from a line containing foreign currency metadata.

    When FX transaction info appears on the same line as GBP amounts,
    this method filters out the foreign currency amounts to prevent them
    from being parsed as GBP transaction amounts.

    Common patterns:
    - "Amount: EUR 109.50. Conversion    -93.58    6.98"
      → Extracts: ['-93.58', '6.98'] (filters out EUR 109.50)
    - "12/08/202  Amount: USD 38.06. Conversion"
      → Extracts: [] (filters out USD 38.06)

    Args:
        line: Text line containing FX metadata and amounts
        amount_pattern: Compiled regex pattern for matching amounts

    Returns:
        List of GBP amount strings (foreign currency amounts filtered out)

    Example:
        >>> line = "Amount: EUR -109.50. Conversion  -93.58  6.98"
        >>> self._filter_foreign_currency_amounts(line, amount_pattern)
        ['-93.58', '6.98']
    """
    # Only apply filtering if FX markers are present
    if not re.search(r'Amount:\s*(USD|EUR)\s*-?[\d,]+', line, re.IGNORECASE):
        # No FX metadata - extract amounts normally
        return amount_pattern.findall(line)

    # Replace foreign currency amounts with placeholder
    filtered_line = re.sub(
        r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?',
        'Amount: [FOREIGN]',
        line,
        flags=re.IGNORECASE
    )

    return amount_pattern.findall(filtered_line)
```

### 3. Page Break Transaction Splitting (LOW PRIORITY)

**Problem**: Transactions that span page breaks can be missed if the continuation line appears after footer/header.

**Monzo Specific Case**:
```
Page 1:
16/08/2024    LINGOM*RED London GBR    -93.58    6.98
--- PAGE BREAK / FOOTER / HEADER ---
Page 2:
              rate: 1.170122.
```

**Original Issue**: The second LINGOM*RED transaction was missed because:
1. The transaction data was complete on page 1
2. The "rate:" continuation appeared after the page break
3. Footer detection was too aggressive and skipped the transaction

**Root Cause**: Not the page break itself, but the date pattern priority issue (#1 above)

**Generalization Recommendation**:
- ❌ **DO NOT generalize** - This was a symptom of issue #1, not a separate problem
- ✅ **Already handled** by existing footer detection in base parser
- ℹ️ **Note**: The footer pattern is already cautious about skipping lines with FX data

### 4. Layout A vs Layout B Transaction Patterns (HIGH PRIORITY - Documentation)

**Problem**: PDF extraction with `-layout` flag can produce two different transaction layouts even within the same statement:

**Layout A** (all on one line):
```
16/08/202        MERCHANT NAME                                  -93.58              6.98
4                [year digit on next line]
```

**Layout B** (split across lines):
```
16/08/202
                 MERCHANT NAME
                                                                 -93.58              6.98
4
```

**Implication**: Parsers need to handle amount extraction in BOTH contexts:
- On date line remainder (Layout A)
- On subsequent lines (Layout B)

**Generalization Recommendation**:
- ✅ **ADD to base parser documentation** as a common pattern
- ✅ **ADD helper method** to detect and extract from both layouts
- ℹ️ **Note**: Each bank parser can choose which layouts they support

**Proposed Base Parser Addition**:
```python
def _extract_amounts_from_remainder(
    self,
    remainder: str,
    amount_pattern: re.Pattern,
    filter_foreign_currency: bool = False
) -> tuple[List[str], str]:
    """
    Extract amounts from date line remainder (Layout A pattern).

    When using pdftotext -layout, some transactions have all data on one line:
    "16/08/202        MERCHANT NAME        -93.58        6.98"

    This method extracts amounts from the remainder after the date prefix,
    and returns both the amounts and a cleaned description.

    Args:
        remainder: Text after date prefix
        amount_pattern: Compiled regex for matching amounts
        filter_foreign_currency: If True, filter out EUR/USD amounts

    Returns:
        Tuple of (amounts_list, cleaned_description)

    Example:
        >>> remainder = "TESCO STORES    -45.67    1254.33"
        >>> amounts, desc = self._extract_amounts_from_remainder(remainder, pattern)
        >>> print(amounts)  # ['-45.67', '1254.33']
        >>> print(desc)     # "TESCO STORES"
    """
    # Filter foreign currency if requested
    if filter_foreign_currency:
        amounts = self._filter_foreign_currency_amounts(remainder, amount_pattern)
    else:
        amounts = amount_pattern.findall(remainder)

    # Remove amounts from description
    desc_part = remainder
    for amt in amounts:
        desc_part = desc_part.replace(amt, ' ', 1)

    return amounts, desc_part.strip()
```

## Comparison with Other Banks

### NatWest FX Handling
- **Strategy**: When 3+ amounts found, take last 2 (assumes: last=balance, second-to-last=GBP transaction)
- **Pattern**: `"USD 20.00 VRATE 1.2730 N-S TRN FEE 0.43    16.14    42,193.81"`
- **Limitation**: Doesn't explicitly filter - relies on positional logic
- **Monzo difference**: Monzo has foreign amount on SAME line as "Amount: EUR" text, so needs explicit filtering

### Barclays, Halifax, HSBC
- **Current state**: No explicit FX handling
- **Risk**: May have similar issues if FX transactions present
- **Recommendation**: Test with FX transaction samples

## Recommended Actions

### Immediate (Do Now)
1. ✅ **Add `_filter_foreign_currency_amounts()` to base parser** - Useful for multiple banks
2. ✅ **Add `_extract_amounts_from_remainder()` to base parser** - Common Layout A pattern
3. ✅ **Document the pattern matching priority issue** in base_parser.py docstring

### Short Term (Before Next Bank)
4. ⚠️ **Test existing parsers with FX transactions** to see if they have similar issues
5. ⚠️ **Add unit tests** for foreign currency filtering edge cases
6. ⚠️ **Update developer guide** with Layout A vs Layout B patterns

### Long Term (Future Enhancement)
7. 💡 **Consider adding FX metadata to Transaction model** (foreign_currency, foreign_amount, exchange_rate)
8. 💡 **Add FX transaction detection to bank detector** (helps with parser selection)
9. 💡 **Create FX-specific validator** (check exchange rate reasonableness, fee calculations)

## Impact Assessment: Regression Risk

### Low Risk Changes (Safe to Generalize)
- ✅ `_filter_foreign_currency_amounts()` - Only activates when FX markers present
- ✅ `_extract_amounts_from_remainder()` - Additive helper method, doesn't change existing logic
- ✅ Documentation additions - No code changes

### Medium Risk Changes (Test Thoroughly)
- ⚠️ Applying foreign currency filtering to existing parsers
  - **Risk**: May break parsers that handle EUR/GBP descriptions differently
  - **Mitigation**: Only apply when FX metadata patterns detected

### High Risk Changes (DO NOT Generalize)
- ❌ Date pattern priority changes - Specific to Monzo's split-date format
- ❌ Year digit pattern changes - Other banks don't use this pattern
- ❌ Carry-over buffer mechanism - Specific to Monzo's reverse chronological layout

## Code Changes to Base Parser

### 1. Add Foreign Currency Filtering Method

```python
# Add to BaseTransactionParser class around line 327

def _filter_foreign_currency_amounts(
    self,
    line: str,
    amount_pattern: re.Pattern
) -> List[str]:
    """
    Extract GBP amounts from a line containing foreign currency metadata.

    When FX transaction info appears on the same line as GBP amounts,
    this method filters out the foreign currency amounts to prevent them
    from being parsed as GBP transaction amounts.

    This is commonly needed when using pdftotext -layout flag, which
    preserves the visual layout and can place FX metadata and GBP amounts
    on the same line.

    Common patterns that trigger filtering:
    - "Amount: EUR 109.50. Conversion    -93.58    6.98"
      → Extracts: ['-93.58', '6.98']
    - "Amount: USD 38.06. Conversion"
      → Extracts: []
    - "TESCO STORES    -45.67    1254.33"
      → Extracts: ['-45.67', '1254.33'] (no FX, returns all amounts)

    Args:
        line: Text line that may contain FX metadata and amounts
        amount_pattern: Compiled regex pattern for matching amounts (e.g., r'-?[\d,]+\.\d{2}')

    Returns:
        List of GBP amount strings with foreign currency amounts filtered out

    Example:
        >>> amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')
        >>> line = "Amount: EUR -109.50. Conversion  -93.58  6.98"
        >>> self._filter_foreign_currency_amounts(line, amount_pattern)
        ['-93.58', '6.98']

    Note:
        Only applies filtering when "Amount: EUR/USD" pattern is detected.
        For lines without FX metadata, returns all matched amounts unchanged.

    See Also:
        - Monzo parser: Uses this extensively for FX transactions
        - NatWest parser: Uses positional logic (last 2 amounts) instead
    """
    # Only apply filtering if FX markers are present
    # Look for pattern: "Amount:" followed by currency code and amount
    if not re.search(r'Amount:\s*(USD|EUR)\s*-?[\d,]+', line, re.IGNORECASE):
        # No FX metadata detected - extract amounts normally
        return amount_pattern.findall(line)

    # Replace foreign currency amounts with placeholder to exclude them
    # Pattern matches: "Amount: EUR 109.50" or "Amount: USD -38.06"
    filtered_line = re.sub(
        r'Amount:\s*(USD|EUR|GBP)\s*-?[\d,]+\.?\d*\.?',
        'Amount: [FOREIGN]',
        line,
        flags=re.IGNORECASE
    )

    return amount_pattern.findall(filtered_line)
```

### 2. Add Layout A Amount Extraction Method

```python
# Add to BaseTransactionParser class around line 375

def _extract_amounts_from_remainder(
    self,
    remainder: str,
    amount_pattern: re.Pattern,
    filter_foreign_currency: bool = False
) -> tuple:
    """
    Extract amounts from date line remainder (Layout A pattern).

    When using pdftotext -layout, some banks format transactions with
    all data on one line after the date prefix:

    "16/08/202        MERCHANT NAME        -93.58        6.98"

    This is referred to as "Layout A" (vs "Layout B" where description
    and amounts are on separate lines). This method extracts amounts
    from the remainder and returns a cleaned description.

    Args:
        remainder: Text after date prefix on the same line
        amount_pattern: Compiled regex for matching amounts
        filter_foreign_currency: If True, apply FX amount filtering

    Returns:
        Tuple of (amounts_list, cleaned_description)
        - amounts_list: List of amount strings found
        - cleaned_description: Remainder with amounts removed

    Example - Normal transaction:
        >>> remainder = "TESCO STORES 2341      -45.67      1254.33"
        >>> amounts, desc = self._extract_amounts_from_remainder(remainder, pattern)
        >>> print(amounts)  # ['-45.67', '1254.33']
        >>> print(desc)     # "TESCO STORES 2341"

    Example - FX transaction with filtering:
        >>> remainder = "Amount: EUR 109.50. Conversion  -93.58  6.98"
        >>> amounts, desc = self._extract_amounts_from_remainder(remainder, pattern, True)
        >>> print(amounts)  # ['-93.58', '6.98']  (EUR filtered out)
        >>> print(desc)     # "Amount: EUR 109.50. Conversion"

    See Also:
        - Monzo parser: Uses this extensively for Layout A transactions
        - _filter_foreign_currency_amounts(): Called when filter_foreign_currency=True
    """
    # Extract amounts, applying foreign currency filter if requested
    if filter_foreign_currency:
        amounts = self._filter_foreign_currency_amounts(remainder, amount_pattern)
    else:
        amounts = amount_pattern.findall(remainder)

    # Remove amounts from description text
    # Replace each amount with space to preserve word separation
    desc_part = remainder
    for amt in amounts:
        desc_part = desc_part.replace(amt, ' ', 1)  # Replace only first occurrence

    return amounts, desc_part.strip()
```

### 3. Update Base Parser Documentation

```python
# Add to BaseTransactionParser class docstring (around line 140)

"""
Abstract base class for bank-specific transaction parsers.

This class defines the interface that all bank parsers must implement
and provides shared utility methods for common parsing operations.

Subclasses must implement:
- parse_transactions(): Main parsing logic for their bank's format

Subclasses can optionally override:
- _find_table_header(): Custom header detection
- _extract_column_positions(): Custom column extraction
- _classify_amount(): Custom amount classification

Common Parsing Patterns:
-----------------------

1. Layout A vs Layout B Transactions:
   When using pdftotext -layout, transactions may appear in two formats:

   Layout A (all on one line):
     "16/08/2024    MERCHANT NAME    -93.58    6.98"
     Use _extract_amounts_from_remainder() to parse.

   Layout B (split across lines):
     "16/08/2024"
     "MERCHANT NAME"
     "                            -93.58    6.98"
     Parse date, description, and amounts separately.

2. Foreign Currency Transactions:
   FX metadata may appear inline with GBP amounts:
     "Amount: EUR 109.50. Conversion    -93.58    6.98"
   Use _filter_foreign_currency_amounts() to extract only GBP amounts.

3. Pattern Matching Priority:
   When using state machines with "pending" flags, always check for
   NEW transaction patterns before checking for state completion.
   This prevents misinterpreting the start of a new transaction
   as the completion of the previous one.

   Example:
     # GOOD: Check for new date first
     if date_match:
         # Start new transaction
     elif pending_year_digit:
         # Complete previous transaction

     # BAD: State check first
     if pending_year_digit:
         # May misinterpret new date as year digit!

4. Multi-line Descriptions:
   Use MultilineDescriptionExtractor for descriptions spanning
   multiple lines. It handles position-based continuation detection
   and footer/header avoidance.
"""
```

## Testing Recommendations

### Unit Tests to Add

```python
# tests/test_parsers/test_base_parser.py

def test_filter_foreign_currency_amounts_with_fx_metadata():
    """Test filtering when EUR/USD amounts present."""
    parser = create_test_parser()
    amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')

    line = "Amount: EUR -109.50. Conversion                         -93.58              6.98"
    amounts = parser._filter_foreign_currency_amounts(line, amount_pattern)

    assert amounts == ['-93.58', '6.98']
    assert '-109.50' not in amounts

def test_filter_foreign_currency_amounts_without_fx_metadata():
    """Test normal amount extraction when no FX metadata."""
    parser = create_test_parser()
    amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')

    line = "TESCO STORES                                           -45.67           1254.33"
    amounts = parser._filter_foreign_currency_amounts(line, amount_pattern)

    assert amounts == ['-45.67', '1254.33']

def test_extract_amounts_from_remainder_layout_a():
    """Test Layout A extraction."""
    parser = create_test_parser()
    amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')

    remainder = "TESCO STORES 2341                                  -45.67           1254.33"
    amounts, desc = parser._extract_amounts_from_remainder(remainder, amount_pattern)

    assert amounts == ['-45.67', '1254.33']
    assert 'TESCO STORES 2341' in desc
    assert '-45.67' not in desc
    assert '1254.33' not in desc

def test_extract_amounts_from_remainder_with_fx_filter():
    """Test Layout A with foreign currency filtering."""
    parser = create_test_parser()
    amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')

    remainder = "Amount: EUR 109.50. Conversion                         -93.58              6.98"
    amounts, desc = parser._extract_amounts_from_remainder(
        remainder, amount_pattern, filter_foreign_currency=True
    )

    assert amounts == ['-93.58', '6.98']
    assert '-109.50' not in amounts
    assert 'Amount: EUR 109.50. Conversion' in desc
```

### Integration Tests to Add

```python
# tests/test_integration/test_fx_transactions.py

def test_monzo_fx_transactions():
    """Verify Monzo FX transactions are captured correctly."""
    result = process_statement('tests/fixtures/monzo_with_fx.pdf')

    # Should capture Kashia×2, APPERATOR×1, LINGOM×4
    fx_transactions = [t for t in result.transactions if 'Amount: EUR' in t.description or 'Amount: USD' in t.description]

    assert len([t for t in fx_transactions if 'Kashia' in t.description]) == 2
    assert len([t for t in fx_transactions if 'APPERATOR' in t.description]) == 1
    assert len([t for t in fx_transactions if 'LINGOM' in t.description]) == 4

def test_natwest_fx_transactions():
    """Verify NatWest FX transactions work with existing logic."""
    # Ensure our changes don't break NatWest's positional FX logic
    result = process_statement('tests/fixtures/natwest_with_fx.pdf')

    # NatWest uses last 2 amounts for transaction+balance when 3+ amounts
    # Verify this still works
    assert result.balance_reconciled == True
```

## Conclusion

The Monzo FX parsing work revealed several generalizable patterns, with **foreign currency filtering** and **Layout A extraction** being the most valuable for the base parser.

**Key Takeaways**:
1. ✅ Add FX filtering methods to base parser - Safe and useful for other banks
2. ✅ Add Layout A extraction helper - Common pattern across banks
3. ✅ Document pattern matching priorities - Prevents future bugs
4. ❌ Do NOT generalize split-date/year-digit logic - Too Monzo-specific
5. ⚠️ Test existing parsers with FX transactions - May reveal similar issues

**Next Steps**:
1. Add the two helper methods to base_parser.py
2. Add comprehensive unit tests
3. Test Barclays, Halifax, HSBC with FX transaction samples
4. Document Layout A vs Layout B patterns in developer guide
