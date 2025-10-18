# Monzo Parser FX Transaction Issue - Research Brief

## Problem Statement

The Monzo bank statement parser is failing to capture foreign currency (FX) transactions, resulting in only 27.6% reconciliation (285/1032 transactions validated). Specifically, merchant names like "Kashia*Nyasa Nairobi KEN" and "APPERATOR Edinburgh GBR" are being blocked and the entire FX transactions are missing from the output.

---

## Background Context

### Monzo Statement Structure (from pdftotext)

**Regular transactions** appear as single lines with all data:
```
                  Transfer from Pot                                       17.50             17.93
```
Format: `[spaces] Description [spaces] Amount [spaces] Balance`

**FX transactions** appear across multiple lines:
```
Kashia*Nyasa Nairobi KEN
Amount: USD -38.04. Conversion
rate: 1.268.

-30.00

10.39
```
Format:
- Line 1: Merchant name
- Line 2: FX info (foreign currency amount)
- Line 3: Conversion rate
- Line 4: (blank)
- Line 5: GBP amount
- Line 6: (blank)
- Line 7: GBP balance

**Typical sequence in pdftotext output:**
```
Transfer from Pot                                       50.00             60.39

08/08/202
4

Kashia*Nyasa Nairobi KEN
Amount: USD -38.04. Conversion
rate: 1.268.

-30.00

10.39

08/08/202
4

Transfer from Pot

35.00

40.39
```

---

## Current Parser Logic

### State Machine Variables
- `current_description_lines`: List accumulating description fragments
- `current_amounts`: List of extracted amounts (target: 2 per transaction)
- `pending_year_digit`: Boolean tracking split-date completion
- `current_date_incomplete`: Date string (DD/MM/YYYY)

### Transaction Completion Trigger
Transactions are completed when we encounter a NEW date line, with this condition:
```python
if current_date_incomplete and current_amounts and not pending_year_digit:
    # Complete previous transaction
    # Reset state
```

### The Problematic Check (Line 243)
To prevent merchant names from the NEXT transaction contaminating the CURRENT transaction's description, this check was added:

```python
# In the continuation line handler:
if len(current_amounts) >= 2 and not pending_year_digit:
    # Transaction is complete, don't add more description
    pass  # Block adding this line
else:
    current_description_lines.append(stripped)  # Add to description
```

---

## The Bug

### What Happens (Trace)

**Iteration 1-3**: Parse "Transfer from Pot 50.00 60.39"
- Extract from single line: description="Transfer from Pot", amounts=[50.00, 60.39]
- State after: `current_description_lines=["Transfer from Pot"]`, `current_amounts=[50.00, 60.39]`, `pending_year_digit=False`

**Iteration 4**: See date "08/08/202" (for Kashia transaction)
- Complete "Transfer from Pot" transaction ✓
- Reset: `current_description_lines=[]`, `current_amounts=[]`, `pending_year_digit=True`

**Iteration 5**: See year digit "4"
- Set `pending_year_digit=False`
- State: `current_description_lines=[]`, `current_amounts=[]`, `pending_year_digit=False`

**Iteration 6**: See blank line
- Skip

**Iteration 7**: See "Kashia*Nyasa Nairobi KEN"
- This is NOT a date, NOT amounts, so falls into continuation line handler
- **BUG**: Check evaluates: `len(current_amounts)=0` (should be 0!), but logs showed `amounts=2`
- The check blocks adding "Kashia*Nyasa" to description
- Merchant name is lost!

### Why amounts=2 When It Should Be 0?

Based on extensive debugging logs, when the parser tries to add "Kashia*Nyasa", the state shows `amounts=2` even though the reset happened. This suggests either:

1. **Hypothesis A**: The amounts from the previous "Transfer from Pot" line (which had TWO amounts on the same line: 50.00 and 60.39) are being added in a LATER iteration, not when the line is first parsed

2. **Hypothesis B**: There's a timing issue where the continuation line check runs BEFORE the transaction completion/reset logic

3. **Hypothesis C**: The "Transfer from Pot 50.00 60.39" line is being processed in chunks across multiple iterations, and amounts persist between chunks

---

## Key Observations from Debugging

### Debug Log Evidence
```
Adding merchant: Kashia*Nyasa Nairobi KEN, amounts=2, pending_year=False
Seeing date, current: desc='Transfer from Pot', amounts=['50.00', '60.39'], pending_year=False
  → Completing transaction: Transfer from Pot
```

The merchant addition happens BEFORE the date is seen, which contradicts the pdftotext line order where the date comes BEFORE the merchant.

### Expected vs Actual pdftotext Line Order
**Expected (and actual pdftotext output):**
```
Line N:   Transfer from Pot                                       50.00             60.39
Line N+1: (blank)
Line N+2: 08/08/202
Line N+3: 4
Line N+4: (blank)
Line N+5: Kashia*Nyasa Nairobi KEN
```

**But parser log shows:**
```
"Adding merchant: Kashia*Nyasa" BEFORE "Seeing date"
```

This temporal inversion is impossible unless the log statements are misleading about the actual execution order.

---

## Relevant Code Sections

### Main Parsing Loop (monzo_parser.py lines 143-263)
```python
i = header_idx + 1
while i < range_end:
    line = lines[i]

    # Skip footers
    if footer_compiled.search(line):
        i += 1
        continue

    # Check for date line
    date_match = date_pattern.match(line)

    if date_match:
        # Complete previous transaction if ready
        if current_date_incomplete and current_amounts and not pending_year_digit:
            transaction = self._build_monzo_transaction(...)
            transactions.append(transaction)

        # Reset state
        current_date_incomplete = date_match.group(1)
        current_description_lines = []
        current_amounts = []
        pending_year_digit = True
        i += 1
        continue

    # Check for year digit
    if pending_year_digit:
        year_digit_match = year_digit_pattern.match(line)
        if year_digit_match:
            current_date_incomplete += year_digit_match.group(1)
            pending_year_digit = False
            i += 1
            continue

    # Check for FX markers
    if 'Amount:' in line and ('EUR' in line or 'USD' in line):
        current_description_lines.append(line.strip())
        i += 1
        continue

    if 'rate:' in line.lower():
        current_description_lines.append(line.strip())
        i += 1
        continue

    # Extract amounts
    amounts_in_line = amount_pattern.findall(line)

    if amounts_in_line:
        current_amounts.extend(amounts_in_line)
        # Extract description from same line (after removing amounts)
        desc_part = line
        for amt in amounts_in_line:
            desc_part = desc_part.replace(amt, ' ', 1)
        desc_part = desc_part.strip()
        if desc_part:
            current_description_lines.append(desc_part)
    else:
        # Continuation line
        stripped = line.strip()
        if stripped and not re.search(r'^\(GBP\)', stripped):
            # THE PROBLEMATIC CHECK:
            if len(current_amounts) >= 2 and not pending_year_digit:
                pass  # Block adding to prevent contamination
            else:
                current_description_lines.append(stripped)

    i += 1
```

### Amount Pattern
```python
amount_pattern = re.compile(r'-?[\d,]+\.\d{2}')
```
Matches currency amounts like: 50.00, -30.02, 1,234.56

### Date Pattern
```python
date_pattern = re.compile(r'^\s*(\d{1,2}/\d{1,2}/\d{3})')
```
Matches: "08/08/202" (year missing last digit)

### Year Digit Pattern
```python
year_digit_pattern = re.compile(r'^\s*(\d)(?:\s+(.*))?')
```
Matches: "4" optionally followed by text

---

## Files Involved

1. **`/Users/pw/Code/ai-bank-statement-extractor/src/parsers/monzo_parser.py`** - Main parser (lines 90-295)
2. **`/Users/pw/Code/ai-bank-statement-extractor/data/bank_templates/monzo.yaml`** - Config
3. **`/Users/pw/Code/ai-bank-statement-extractor/src/validators/balance_validator.py`** - Validation (handles period breaks)

---

## What Works Currently

1. ✅ Regular transactions (e.g., "Transfer from Pot") parse correctly when amounts are on the same line
2. ✅ Split-date handling (DD/MM/YYY + final digit on next line)
3. ✅ Per-period reconciliation with period break markers
4. ✅ Chronological sorting with within-day order preservation
5. ✅ Preventing contamination: "Transfer from Pot" no longer gets "vibraskitip.com" appended
6. ✅ FX info lines ("Amount: EUR...", "rate: 1.268.") ARE being added to descriptions when FX transactions are successfully captured
7. ✅ Some FX transactions DO work (8 found: TALLMADGE, ARE, CAP LAO)

---

## What Doesn't Work

1. ❌ FX transactions where merchant name appears AFTER a completed previous transaction
2. ❌ Specifically: Kashia*Nyasa (2 instances) and APPERATOR (1 instance) are missing entirely
3. ❌ These missing transactions cause cascade failures in balance reconciliation

---

## Research Questions

### Primary Question
**How should the parser handle merchant names that appear between a complete transaction (with 2 amounts) and the next date line?**

### Specific Sub-Questions

1. **State Management**: Why would `current_amounts` still be 2 when processing "Kashia*Nyasa" if the reset happened at the previous date line? Is there a state persistence bug?

2. **Alternative Architecture**: Should FX transactions be detected proactively (by looking ahead for "Amount: EUR" patterns) rather than reactively building up state line-by-line?

3. **Two-Pass Solution**: Would a two-pass approach work?
   - Pass 1: Identify transaction boundaries and types (regular vs FX)
   - Pass 2: Extract data based on type

4. **Buffering Strategy**: Should the parser buffer incomplete FX transactions separately until all required components are found?

5. **Look-Ahead Logic**: When a continuation line is blocked (amounts=2), should the parser look ahead to see if the next line is a date? If yes, buffer the current line for the next transaction?

6. **Transaction Completion Timing**: Should transactions with 2 amounts be completed IMMEDIATELY (mid-loop) rather than waiting for the next date line?

---

## Success Criteria

1. All FX transactions (including Kashia and APPERATOR) appear in output
2. FX transactions have complete descriptions: "Merchant Name Amount: EUR -X.XX. Conversion rate: Y.YYYYYY."
3. FX transactions have correct GBP amounts and balances
4. No contamination: Regular transactions don't get FX merchant names appended
5. Balance reconciliation improves from 27.6% toward 100%

---

## Test Case for Validation

After implementing fix, this specific section should parse correctly:

**Input (pdftotext lines):**
```
Transfer from Pot                                       50.00             60.39

08/08/202
4

Kashia*Nyasa Nairobi KEN
Amount: USD -38.04. Conversion
rate: 1.268.

-30.00

10.39

08/08/202
4

Transfer from Pot

35.00

40.39
```

**Expected Output (3 transactions):**
1. Description: "Transfer from Pot", Money In: 50.00, Balance: 60.39
2. Description: "Kashia*Nyasa Nairobi KEN Amount: USD -38.04. Conversion rate: 1.268.", Money Out: 30.00, Balance: 10.39
3. Description: "Transfer from Pot", Money In: 35.00, Balance: 40.39

---

## Current Validation Stats

- **Total transactions in statement**: 1,032
- **Transactions parsed**: 1,016
- **Transactions validated**: 285 (27.6%)
- **First validation failure**: Transaction 285 (date: 2024-08-08)
- **Missing FX transactions**: At least 3 (Kashia×2, APPERATOR×1)

---

## Additional Context

### Why Regular Transactions Work
Lines like "Transfer from Pot      50.00      60.39" have ALL data on one line. When parsed:
- Both amounts extracted immediately
- Description extracted from same line
- Transaction is self-contained
- Next line is usually a date, triggering completion

### Why FX Transactions Fail
FX transactions span 5+ lines. The merchant name line arrives when:
- Previous transaction is complete (amounts=2)
- But new transaction hasn't started yet (no date seen)
- Parser is in "limbo" state
- Check blocks adding merchant name
- Transaction never gets created

---

## Potential Solutions to Evaluate

### Option 1: Delayed Completion
Don't complete transactions at date lines. Instead, complete them when we see a merchant name OR amount line for the NEXT transaction.

**Pros:** Natural transaction boundaries
**Cons:** Complex state management, risk of losing last transaction

### Option 2: Look-Ahead Buffering
When blocking a continuation line, buffer it. If next line is a date, associate buffered line with upcoming transaction.

**Pros:** Minimal changes to current logic
**Cons:** Requires peeking ahead, may miss edge cases

### Option 3: Transaction Type Detection
Detect FX transactions early (when seeing "Amount: EUR" lines) and use different parsing logic.

**Pros:** Clear separation of concerns
**Cons:** More complex, need to handle mixed regular/FX sequences

### Option 4: Remove the Blocking Check
Remove the `if len(current_amounts) >= 2` check entirely and find another way to prevent contamination.

**Pros:** Simple, unblocks FX merchant names
**Cons:** Re-introduces contamination bug (regular transactions getting wrong merchant names)

### Option 5: State Flag for "Transaction Complete"
Add explicit `transaction_complete` flag set when amounts=2 AND description is non-empty. Use this instead of amounts check.

**Pros:** More explicit state management
**Cons:** Another variable to track, may not solve root cause

### Option 6: Immediate Completion After 2 Amounts
When `current_amounts` reaches 2, immediately complete the transaction and reset state (don't wait for next date).

**Pros:** Transactions complete as soon as they're ready
**Cons:** Need to buffer the completed transaction until we can append it to the list, complex control flow

---

## Request

Please analyze this issue and provide:

1. **Root Cause Analysis**: Why is `amounts=2` when processing "Kashia*Nyasa" despite the reset?
2. **Recommended Solution**: Which approach (or combination) would be most robust?
3. **Implementation Sketch**: Pseudo-code or high-level steps for the fix
4. **Edge Cases**: What other scenarios might break with the proposed fix?
5. **Testing Strategy**: How to verify the fix works for all transaction types?

The ideal solution should handle:
- Regular single-line transactions ✓
- Multi-line FX transactions with merchant names
- Mixed sequences of regular and FX transactions
- Transactions with/without descriptions
- Page breaks within FX transactions (handled separately)

---

## Appendix: Working FX Transaction Example

For comparison, here are FX transactions that DO work (8 found):
- TALLMADGE USA Amount: USD -10.98
- ARE Amount: EUR -116.62
- CAP LAO Amount: USD -119.93

These likely work because they appear in different contexts where the previous transaction state doesn't interfere. Analyzing what's different about their positioning in the file could provide clues.
