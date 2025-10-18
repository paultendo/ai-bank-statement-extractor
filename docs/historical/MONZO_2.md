Below is a principal‑engineer implementation response that (1) explains the root cause from your traces, (2) gives a concrete, low‑risk fix, (3) shows exactly what to change (with drop‑in code), and (4) lays out verification steps so your developer can ship with confidence.

---

## Executive summary (what to implement)

**Fix class:** *Parsing state / boundary handling.*

**Root cause:** When an FX merchant line (e.g., `Kashia*Nyasa Nairobi KEN`) arrives **after** a fully‑complete transaction (2 amounts present) but **before** the next date header is consumed, the current continuation‑line guard (`if len(current_amounts) >= 2 …: pass`) blocks the merchant from being attached. Your “emit‑and‑replay” attempt then replays the merchant **before** the next date header, causing the next date split (`08/08/202` then `4`) to reset state and drop the merchant you just added. This is why you observed “merchant added” followed immediately by “FX Amount line, current desc has: 0 lines”. The merchant was added, then promptly cleared when the premature date header fired. The behaviour is easy to reproduce around the Kashia / APPERATOR cluster on 08/08/2024 in the supplied statement. 

**Recommended fix (minimal diff, robust):**
Combine **Option 6 (immediate completion after 2 amounts)** with **Option 2 (look‑ahead buffering)** from your brief:

1. **Immediate emit on completion:** As soon as a transaction has its two GBP figures (amount & balance), **emit it immediately**—do not wait for the next date line.
2. **Carry‑over buffer for “early” next‑txn lines:** If, *right after emitting*, you detect a line that *belongs to the next transaction* (e.g., an FX merchant line), **do not replay it immediately**. Instead, stash it in a `carry_over_desc` buffer and attach it **only after** the next date header (`DD/MM/202` + trailing year digit) is assembled. This preserves the natural order in Monzo’s layout B (date split across 2 lines, then description).

This keeps the parser single‑pass, avoids two‑pass complexity, and prevents both contamination and the FX drop.

---

## Why this happens (root cause analysis)

1. **Monzo layout B with a split date header.** Dates appear as `DD/MM/202` followed by the trailing `4` on the next line. Your config expects the 3‑digit prefix (`^\s*\d{1,2}/\d{1,2}/\d{3}`), which correctly matches `08/08/202`, and then a year‑digit line follows. This means a new transaction **always** begins with those two lines before the merchant. 

2. **Blocking continuation after “2 amounts”.** The brief shows a guard that prevents adding any more description once `len(current_amounts) >= 2`. That was introduced to stop contamination, but it also blocks the next merchant if it arrives before the next date has been recognised as *belonging to that merchant’s transaction*. 

3. **Concrete evidence in the PDF and your logs.** In the statement extract, the sequence is:

```
... Transfer from Pot           50.00      60.39
08/08/202
4
Kashia*Nyasa Nairobi KEN
Amount: USD -38.04. Conversion
rate: 1.268.
-30.00 10.39
```

Because the previous transaction (“Transfer from Pot”) is already complete on the first line, the merchant for the **next** transaction must be attached **after** the new date is consumed—never before. Replaying the merchant “early” guarantees it will be wiped when the upcoming date header resets state. 

4. **Your brief’s findings match this.** The “What Doesn’t Work” and “Test Case for Validation” sections describe exactly the Kashia and APPERATOR misses you’re seeing, and the sample expected output for that Aug 8th segment.  

---

## Design: small, safe changes that fix the class of bugs

### A. Emit‑on‑completion (don’t wait for the next date)

* As soon as `current_amounts` reaches 2 GBP figures (amount + balance), **build and store the transaction immediately**.
* Reset `current_description_lines`, `current_amounts`, and any “complete” flags.
* Do **not** consume the *current* input line beyond what you already did; just proceed.

> Why: This removes the “limbo” window where the parser sits with 2 amounts but no official boundary, which is when FX merchant lines get incorrectly blocked. This matches “Option 6” in your brief. 

### B. Carry‑over description buffer (attach after the next date)

* Introduce `carry_over_desc: list[str] | None`. When you see a line that should start the next transaction (e.g., an FX merchant) **right after** emitting the previous one, **do not replay it immediately**. Instead:

  * `carry_over_desc = [merchant_line]`
  * Skip appending it to the *current* transaction; instead, wait.
* When you later see the next date header (`DD/MM/202` then the trailing digit `4`):

  * Start a fresh transaction state for that date.
  * If `carry_over_desc` is populated, extend `current_description_lines` with it **now**, then clear `carry_over_desc`.
* Treat “FX info” lines (`Amount: [USD|EUR] ...`, `rate: ...`) similarly: if they occur while `carry_over_desc` is waiting and you haven’t attached it yet, attach `carry_over_desc` first, then append the FX lines.

> Why: This preserves the true order of “date → merchant → FX info → GBP amount/balance” that the PDF enforces, and eliminates the need to “replay” lines at all. This is “Option 2” in your brief (look‑ahead buffering), implemented as a single‑line carry‑over rather than a complex queue. 

---

## Exact code changes (drop‑in patterns)

> **Note:** I don’t have direct access to your `monzo_parser.py`, but the snippets below map 1:1 to the brief’s “Main Parsing Loop” and the config. Your developer can paste these changes into the corresponding sections.

### 1) Configuration (no change needed, but relies on this)

You’re already keying off the three‑digit date prefix (`^\s*\d{1,2}/\d{1,2}/\d{3}`) and a separate “year digit” line—keep that. 

### 2) New state fields

Add near the other state variables:

```python
carry_over_desc: list[str] | None = None         # merchant (and possibly other starter lines) that belong to the NEXT txn
fx_block_active: bool = False                    # set True after seeing an FX merchant until we’ve processed its FX info + amounts
```

### 3) Helper predicates

Add these helpers above the loop:

```python
FX_MERCHANT_HINT = re.compile(r'\b[A-Z][A-Za-z0-9* .,-]+(?:\b[A-Z]{3})\b')  # heuristic; presence of a trailing country code like GBR, KEN, DNK helps
FX_AMOUNT_LINE   = re.compile(r'\bAmount:\s*(USD|EUR|[A-Z]{3})\b', re.IGNORECASE)
FX_RATE_LINE     = re.compile(r'\brate:\s*[0-9.]+', re.IGNORECASE)

def is_date_prefix(line: str) -> bool:
    return bool(date_pattern.match(line))  # from your brief/config

def is_year_digit(line: str) -> bool:
    return bool(year_digit_pattern.match(line))  # from your brief

def is_fx_amount_info(line: str) -> bool:
    return bool(FX_AMOUNT_LINE.search(line))

def is_fx_rate_info(line: str) -> bool:
    return bool(FX_RATE_LINE.search(line))

def gbp_amounts_in_line(line: str) -> list[str]:
    # avoid picking FX foreign amount values from “Amount: USD …”
    if is_fx_amount_info(line):
        return []
    return amount_pattern.findall(line)  # your existing -?\d+.\d{2}
```

(Regex names reference snippets in your brief. )

### 4) Emit‑on‑completion

Immediately after you extend `current_amounts` with `gbp_amounts_in_line(line)`, do:

```python
if len(current_amounts) >= 2 and not pending_year_digit:
    # complete the transaction right now
    transaction = self._build_monzo_transaction(
        date=current_date_incomplete,  # already completed with the year digit
        description=" ".join(current_description_lines).strip(),
        amounts=current_amounts,
    )
    transactions.append(transaction)

    # reset state AFTER emit
    current_description_lines = []
    current_amounts = []
    fx_block_active = False

    # IMPORTANT: do not attach the current line to a new txn here;
    # just continue. Any next-transaction content (e.g., merchant)
    # will be detected below and placed into carry_over_desc.
    # continue parsing the same loop iteration (no extra i += 1 here beyond the normal loop).
```

This removes the reliance on the *next* date as a completion trigger and eliminates the window in which your guard blocks the merchant. (In the brief, this is “Option 6”.) 

### 5) Replace the “block after 2 amounts” guard with carry‑over

Find the continuation block shown in your brief:

```python
# THE PROBLEMATIC CHECK:
if len(current_amounts) >= 2 and not pending_year_digit:
    pass  # Block adding to prevent contamination
else:
    current_description_lines.append(stripped)
```

Replace with:

```python
if len(current_amounts) >= 2 and not pending_year_digit:
    # We consider the previous transaction complete; do NOT discard this line.
    # Instead, prime it for the *next* transaction as carry-over (e.g., FX merchant).
    # Only keep meaningful non-empty lines.
    if stripped:
        carry_over_desc = [stripped]
        fx_block_active = bool(FX_MERCHANT_HINT.search(stripped))  # heuristic; turn on FX substate if it looks like an FX merchant
    # Do NOT append to current_description_lines here; the txn was just completed above.
else:
    if stripped:
        current_description_lines.append(stripped)
```

This keeps your de‑contamination intention but no longer drops the merchant.

### 6) Attach carry‑over at the right time (after the date header)

In the **date** / **year‑digit** branches, right after you’ve finished building the full date:

```python
# date prefix branch
if date_match:
    # (if you still have a transaction half-baked here, you can emit it or drop it based on your rules)
    current_date_incomplete = date_match.group(1)
    current_description_lines = []
    current_amounts = []
    pending_year_digit = True
    fx_block_active = False
    i += 1
    continue

# year digit branch
if pending_year_digit:
    year_digit_match = year_digit_pattern.match(line)
    if year_digit_match:
        current_date_incomplete += year_digit_match.group(1)
        pending_year_digit = False

        # >>> NEW: attach buffered merchant/first lines now <<<
        if carry_over_desc:
            current_description_lines.extend(carry_over_desc)
            carry_over_desc = None

        i += 1
        continue
```

This guarantees lines like `Kashia*Nyasa Nairobi KEN` are attached **after** `08/08/2024` is formed—exactly how they appear in the PDF. 

### 7) FX info lines

In your existing FX branches:

```python
if is_fx_amount_info(line):
    # ensure merchant line is attached first if we were carrying it
    if carry_over_desc:
        current_description_lines.extend(carry_over_desc)
        carry_over_desc = None
    current_description_lines.append(line.strip())
    fx_block_active = True
    i += 1
    continue

if is_fx_rate_info(line):
    if carry_over_desc:
        current_description_lines.extend(carry_over_desc)
        carry_over_desc = None
    current_description_lines.append(line.strip())
    fx_block_active = True
    i += 1
    continue
```

This makes the FX description robust whether the PDF emits GBP amounts on the same line as the rate (as seen in one rendering) or on separate lines (as seen in another). The dataset shows both flavours; e.g., the Kashia / APPERATOR region has `-30.00` and balance on the same line in one page image, and split lines elsewhere.  

---

## Why this is safe

* You already rely on a **custom** Monzo parser because the transaction patterns are not declarative in YAML; the config itself flags that a custom parser is required and that the date column is only a **3‑digit** prefix. The changes above align with that reality rather than fighting it. 
* The new behaviour does **not** relax header/footer skipping nor amount parsing and keeps the contamination protection—just moves it into a targeted carry‑over path instead of a blanket “drop”.
* It handles both FX layouts (GBP lines on the same line as rate vs separate lines) present in your PDF sample.  

---

## Test plan (must pass before merge)

Use the exact failing segment from your brief as a fixture and assert the three expected transactions. 

1. **Unit test: FX segment on 2024‑08‑08 (Kashia + APPERATOR)**

   * **Input (lines):** Use the `Transfer from Pot … 60.39` → `08/08/202` → `4` → `Kashia*Nyasa …` → `Amount:` → `rate:` → `-30.00` → `10.39` snippet.
   * **Assert:** 3 transactions:

     * “Transfer from Pot” in: `50.00`, balance `60.39`
     * “Kashia*Nyasa … Amount: USD -38.04. Conversion rate: 1.268.” out: `30.00`, balance `10.39`
     * “Transfer from Pot” in: `35.00`, balance `40.39`
       (Exactly as per brief.) 

2. **Integration test: full statement**

   * Run parser end‑to‑end on `monzo-bidmead.pdf`.
   * **Search** the output for “Kashia” and “APPERATOR”; expect ≥3 rows (Kashia×2, APPERATOR×1) with correct amounts/balances. The PDF pages 46–47 show these transactions clearly, including currency lines and conversion rate. 

3. **Regression tests (non‑FX)**

   * Confirm that regular single‑line transactions like “Transfer from Pot” still parse with description, amount and balance on the same line. (Many examples across the statement.) 

4. **Edge cases**

   * **Split amounts:** When GBP amount and balance are on separate lines (some PDF renderings), ensure the second number still pairs as balance.
   * **Page breaks:** Ensure footer/header filters still skip Monzo’s page furniture (company reg lines, FSCS, etc.). (Numerous footers across PDF pages.) 
   * **Other FX examples that already worked** (TALLMADGE / ARE / CAP LAO per the brief) continue to pass. 

5. **Validator pass**

   * Re‑run your balance validator. Expect reconciliation to rise from ~27.6% (285/1032) towards full alignment once the 3 missing FX transactions are present. (Stats and first failure position are recorded in the brief.) 

---

## Developer notes & pitfalls

* **Do not replay the merchant immediately after an emit.** That inserts it *before* the date header and guarantees it will be wiped when the date prefix arrives. Buffer it and attach after the `YYYY` is formed.
* **Do not treat `Amount: USD|EUR …` as GBP amounts.** Your `amount_pattern` is broad. Always short‑circuit when `is_fx_amount_info(line)` is true so you don’t pollute `current_amounts`. (The brief shows the pattern you’re using.) 
* **Only reset description on true transaction boundaries.** With immediate emit, you’ll reset straight after adding the 2nd number; that’s fine. The carry‑over ensures the very next merchant won’t be dropped.
* **Date handling remains split.** Keep the three‑digit date prefix and the single trailing digit logic—this matches the PDF and your YAML. 

---

## What to tell from logging (post‑fix)

Add structured logs around these events:

* `emit(txn)` → include final date, description first 60 chars, and both amounts.
* `carry_over_desc set` → include the line; this should be immediately followed by a date in the subsequent iterations.
* `attach carry_over_desc after year digit` → ensure you see this exactly once per occurrence.

On the failing region you should now see:

1. Emit `Transfer from Pot` (50.00 / 60.39).
2. `carry_over_desc` set to `"Kashia*Nyasa Nairobi KEN"`.
3. See `08/08/202` then `4`.
4. Attach carry‑over to new txn, then append `Amount: USD …` and `rate: …`.
5. Add `-30.00` and `10.39` and emit FX transaction.

---

## Why this satisfies the brief

* **Fixes Kashia & APPERATOR**—the explicit failing cases—by guaranteeing the merchant is associated with the correct date block and FX lines. (The region is visible on pp. 46–47 in your PDF, including the exact currency and rate lines.) 
* **Prevents contamination** without dropping lines by using a carry‑over buffer instead of a hard block.
* **Minimal code churn** centred on the continuation guard and completion timing, keeping your custom Monzo parser aligned with the YAML config’s assumptions about date layout. 
* **Matches your success criteria** in the brief (all FX appear, complete descriptions, correct GBP values, improved reconciliation). 

---

### Appendix – references used

* Monzo YAML notes the split date (`^\s*\d{1,2}/\d{1,2}/\d{3}`) and that a custom parser is required. 
* The brief provides the problematic guard and loop structure, plus options 2 & 6 which we’ve combined.   
* Statement evidence of the Kashia / APPERATOR FX sequences on 08/08/2024. 

---

If your developer implements the four code changes above (emit‑on‑completion; replace the guard with carry‑over; attach carry‑over after the year digit; treat FX info lines as description, not GBP), the three missing FX transactions should populate and the reconciliation count should climb accordingly.
