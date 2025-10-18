# Dynamic Column Detection - Usage Examples

This document shows how to use the `column_detection` utility functions to simplify parser implementations.

## Problem Statement

Many UK banks use `pdftotext -layout` format where:
- Column positions vary between pages (different headers/margins)
- Amounts are classified by position (e.g., "if position < 100: money_out")
- Without dynamic detection, amounts get misclassified

## Solution: Utility Functions

The `src/utils/column_detection.py` module provides reusable functions for:
1. Detecting column positions from headers
2. Calculating thresholds between columns
3. Pre-scanning documents
4. Classifying amounts by position

---

## Example 1: Santander Parser (Simplified)

### Before (Current Implementation)
```python
# Duplicated logic in the parser
column_positions = {
    'money_in_start': 104,
    'money_out_start': 118,
    'balance_start': 137,
    'threshold': 117
}

# In main loop
if header_pattern.search(line):
    money_in_match = re.search(r'Money\s+in', line, re.IGNORECASE)
    money_out_match = re.search(r'Money\s+out', line, re.IGNORECASE)

    if money_in_match and money_out_match:
        money_in_start = money_in_match.start()
        money_out_start = money_out_match.start()
        threshold = (money_in_start + money_out_start) // 2

        column_positions['threshold'] = threshold
```

### After (Using Utility)
```python
from ..utils import find_and_update_thresholds, pre_scan_for_thresholds

# Define column configuration once
COLUMN_NAMES = ['Money in', 'Money out', 'Balance']
COLUMN_PAIRS = [('Money in', 'Money out')]  # Threshold between these

# Pre-scan before processing
thresholds = pre_scan_for_thresholds(
    lines,
    COLUMN_NAMES,
    COLUMN_PAIRS,
    default_thresholds={'money_in_threshold': 117}
)

# In main loop - single line update
if header_pattern.search(line):
    new_thresholds = find_and_update_thresholds(
        line, COLUMN_NAMES, COLUMN_PAIRS, thresholds
    )
    if new_thresholds:
        thresholds = new_thresholds
```

**Benefits:**
- 15 lines → 3 lines in main loop
- Clear declaration of column structure
- Automatic logging of threshold changes
- Testable in isolation

---

## Example 2: Barclays Parser

### Configuration
```python
from ..utils import pre_scan_for_thresholds, find_and_update_thresholds

# Barclays has 3 amount columns
COLUMN_NAMES = ['Money out', 'Money in', 'Balance']
COLUMN_PAIRS = [
    ('Money out', 'Money in'),   # money_out_threshold
    ('Money in', 'Balance')       # money_in_threshold
]

DEFAULT_THRESHOLDS = {
    'money_out_threshold': 75,
    'money_in_threshold': 95
}
```

### Pre-scan Phase
```python
thresholds = pre_scan_for_thresholds(
    lines,
    COLUMN_NAMES,
    COLUMN_PAIRS,
    DEFAULT_THRESHOLDS
)
```

### Main Loop Update
```python
if header_pattern.search(line):
    new_thresholds = find_and_update_thresholds(
        line, COLUMN_NAMES, COLUMN_PAIRS, thresholds
    )
    if new_thresholds:
        thresholds = new_thresholds
```

### Amount Classification
```python
# Current approach (manual)
if amt_end >= 105:
    balance = amt
elif amt_end >= 85:
    money_in = amt
else:
    money_out = amt

# Alternative with utility (more explicit)
from ..utils import classify_amount_by_position

col = classify_amount_by_position(
    position=amt_end,
    thresholds=thresholds,
    column_order=['money_out', 'money_in', 'balance']
)

if col == 'balance':
    balance = amt
elif col == 'money_in':
    money_in = amt
else:
    money_out = amt
```

---

## Example 3: NatWest Parser (Handles Both Column Orders)

NatWest is unique - it handles both "Paid In, Withdrawn" and "Withdrawn, Paid In" orders.

### Current Implementation
```python
# Manual detection of column order
if withdrawn_start < paid_in_start:
    WITHDRAWN_THRESHOLD = (withdrawn_start + paid_in_start) // 2
    PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2
else:
    PAID_IN_THRESHOLD = (paid_in_start + withdrawn_start) // 2
    WITHDRAWN_THRESHOLD = (withdrawn_start + balance_start) // 2
```

### With Utility (Same Result)
```python
from ..utils import detect_column_positions, calculate_thresholds

# Detect actual column positions
positions = detect_column_positions(
    line,
    ['Paid In', 'Withdrawn', 'Balance']
)

if not positions:
    continue

# Determine order dynamically
if positions['Withdrawn'] < positions['Paid In']:
    # Order: Withdrawn, Paid In, Balance
    pairs = [('Withdrawn', 'Paid In'), ('Paid In', 'Balance')]
else:
    # Order: Paid In, Withdrawn, Balance
    pairs = [('Paid In', 'Withdrawn'), ('Withdrawn', 'Balance')]

thresholds = calculate_thresholds(positions, pairs)
```

**Advantage**: Logic is explicit and testable.

---

## Example 4: HSBC Parser (Already Well-Implemented)

HSBC already has clean dynamic detection. The utility would simplify it slightly:

### Current (Good Code)
```python
paid_out_match = re.search(r'Paid\s+out', line)
paid_in_match = re.search(r'Paid\s+in', line)
balance_match = re.search(r'Balance', line)

if paid_out_match and paid_in_match and balance_match:
    paid_out_start = paid_out_match.start()
    paid_in_start = paid_in_match.start()
    balance_start = balance_match.start()

    PAID_OUT_THRESHOLD = (paid_out_start + paid_in_start) // 2
    PAID_IN_THRESHOLD = (paid_in_start + balance_start) // 2
```

### With Utility (More Concise)
```python
new_thresholds = find_and_update_thresholds(
    line,
    ['Paid out', 'Paid in', 'Balance'],
    [('Paid out', 'Paid in'), ('Paid in', 'Balance')],
    current_thresholds
)
if new_thresholds:
    PAID_OUT_THRESHOLD = new_thresholds['paid_out_threshold']
    PAID_IN_THRESHOLD = new_thresholds['paid_in_threshold']
```

---

## Best Practices

### When to Use the Utility

✅ **Use when:**
- Parser uses position-based amount classification
- Statement has multiple pages
- Bank format is consistent (same column names across pages)

❌ **Don't use when:**
- Parser uses regex patterns, not positions (Halifax, Monzo)
- Only processing single-page statements
- Column detection logic is highly custom (NatWest's order detection)

### Recommended Approach

1. **Define column config at top of `parse_transactions()`:**
   ```python
   COLUMN_NAMES = ['Money out', 'Money in', 'Balance']
   COLUMN_PAIRS = [('Money out', 'Money in'), ('Money in', 'Balance')]
   DEFAULT_THRESHOLDS = {'money_out_threshold': 75, 'money_in_threshold': 95}
   ```

2. **Pre-scan before main loop:**
   ```python
   thresholds = pre_scan_for_thresholds(lines, COLUMN_NAMES, COLUMN_PAIRS, DEFAULT_THRESHOLDS)
   ```

3. **Update in main loop when header found:**
   ```python
   if header_pattern.search(line):
       new_thresholds = find_and_update_thresholds(line, COLUMN_NAMES, COLUMN_PAIRS, thresholds)
       if new_thresholds:
           thresholds = new_thresholds
   ```

### Migration Strategy

**Don't refactor existing working parsers** unless:
- They have bugs related to column detection
- You're making other significant changes
- Code readability would significantly improve

**Do use the utility for:**
- All new parsers
- Parsers undergoing major refactoring
- Fixing column detection bugs

---

## Testing

The utility functions are designed to be easily testable:

```python
def test_detect_column_positions():
    line = "Date    Money out    Money in    Balance"
    positions = detect_column_positions(line, ['Money out', 'Money in', 'Balance'])

    assert positions == {'Money out': 8, 'Money in': 21, 'Balance': 33}

def test_calculate_thresholds():
    positions = {'Money out': 65, 'Money in': 85, 'Balance': 105}
    pairs = [('Money out', 'Money in'), ('Money in', 'Balance')]
    thresholds = calculate_thresholds(positions, pairs)

    assert thresholds == {'money_out_threshold': 75, 'money_in_threshold': 95}

def test_boundary_case():
    # Amount exactly on threshold should go to left column
    col = classify_amount_by_position(
        75,  # Exactly on threshold
        {'money_out_threshold': 75, 'money_in_threshold': 95},
        ['money_out', 'money_in', 'balance']
    )
    assert col == 'money_out'  # Boundary-inclusive
```

---

## Summary

The `column_detection` utility provides:
- **Reusable** functions for common pattern
- **Tested** and documented behavior
- **Flexible** - doesn't enforce base class structure
- **Optional** - use only when beneficial

Each parser can still implement custom logic while leveraging these utilities for the repetitive parts.
