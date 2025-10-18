Below is a principal‑engineer level implementation response aimed at the developer who will make the changes. I’ve grounded it in the brief, the Monzo PDF, and the Monzo config file; I’ve also provided concrete code patterns, explicit state‑machine rules, and a test plan you can drop straight into your suite.

---

## 1) Executive summary

**What’s broken**
FX transactions that span multiple lines (merchant → FX meta → GBP amount → GBP balance) are being dropped whenever they appear immediately after a completed single‑line transaction. The defensive “don’t contaminate descriptions once we have two amounts” check prevents the first FX line (the merchant name) from attaching to the new transaction. Result: merchant lines such as `Kashia*Nyasa Nairobi KEN` and `APPERATOR Edinburgh GBR` are lost, and the corresponding FX transactions never materialise; reconciliation collapses at ~27.6%.  

**Root cause in one sentence**
We only *finalise* the current transaction on seeing the **next date**; until then we leave `current_amounts` at `2`, so the “block continuation lines once amounts >= 2” rule wrongly bins the first merchant line of the next (FX) transaction. The logic also doesn’t re‑process that merchant line after finalising the previous transaction. 

**Fix (high level)**
Adopt **emit‑on‑completion with reprocessing**: as soon as the current transaction is *complete* (we have two GBP amounts and a finished date), we **emit it immediately**, reset state, and **re‑process the same line** as the *first* line of the next transaction. Replace the current “block‑after‑two‑amounts” guard with this *emit & replay* behaviour. Additionally, if a Monzo “year digit” line (`…202` then `4`) arrives with trailing content, capture and re‑classify that trailing content instead of discarding it. 

---

## 2) Evidence and context you must preserve

* **Monzo layout & split dates**: The statement uses several layouts; notably dates are split across lines like `08/08/202` then `4`. Your YAML patterns and current parser already anticipate this. Ensure we continue to support this exact behaviour. 
* **FX transactions are multi‑line**. Typical structure in the brief:

  ```
  Kashia*Nyasa Nairobi KEN
  Amount: USD -38.04. Conversion
  rate: 1.268.

  -30.00

  10.39
  ```

  (merchant → FX amount/currency → rate → GBP amount → balance). 
  The live PDF exhibits the same pattern (e.g., `LINGOM*RED … Amount: EUR … Conversion rate: … -93.58 …`). 
* **Problematic guard**: In the “continuation line” branch we do:

  ```python
  if len(current_amounts) >= 2 and not pending_year_digit:
      pass
  else:
      current_description_lines.append(stripped)
  ```

  That’s the blocker that drops the very first line of the next FX transaction. 

---

## 3) Root cause analysis (why the state looks wrong)

1. **Finalisation tied to “next date”**
   We only complete a transaction when we hit a **new** date:

```python
if current_date_incomplete and current_amounts and not pending_year_digit:
    transaction = self._build_monzo_transaction(...)
    transactions.append(transaction)
```

This means that after we parse a single‑line non‑FX entry (which already has both GBP amounts on the same line), `len(current_amounts) == 2` remains true **until** we meet the next date header. Any non‑date text in between (e.g., the merchant of the next FX transaction) enters the “continuation line” branch and is dropped by the guard. 

2. **“Temporal inversion” in logs**
   The brief shows logs where a merchant add happens *before* the next date is “seen”. That’s consistent with the above: the date match didn’t fire **yet** (or was bypassed); the guard triggers with `amounts == 2`; the merchant is discarded; only afterwards do we see the date and finalise the previous transaction. Regardless of logging, the control‑flow + guard explains the observed state. 

3. **Secondary minor issue—lost trailing text after the year digit**
   Your `year_digit_pattern` allows optional trailing text `(.*)`, but the code ignores it and `continue`s, losing any same‑line description that might occur after the “4”. That can create sporadic drops for lines where `4` and the next content got merged by `pdftotext`. We should capture and re‑classify that trailing text. 

---

## 4) Design: precise behaviour changes

### 4.1 Emit‑on‑completion (with “replay current line”)

**Definition of “complete”**
A transaction is complete when all of the following hold:

* We have a **fully realised date** (i.e., we’ve seen the year digit; `pending_year_digit == False`).
* We have **two GBP amounts** captured for the row: one amount (money in/out) and one running balance (Monzo presents both). Your `amount_pattern` already handles the numeric forms in the document. 

**Rule**
Whenever the parser is about to process a non‑amount line, and the **current** transaction is complete:

* **Immediately emit** the current transaction.
* **Reset** all transaction‑scoped state (description accumulator, amounts list, FX flags).
* **Reprocess the same line** (do not increment `i`) as the beginning of the **next** transaction.

This replaces the current “block if amounts >= 2” guard. The key difference: we *never* discard the merchant line; we use it to start the next record.

**Why this is safe**

* For regular one‑line transactions, two amounts are found on the same line; the very next non‑amount line is typically the next date or a blank; immediate emission is correct either way.
* For FX, by the time the GBP amount and balance arrive (the last two amounts), the description lines (merchant + FX meta) must be allowed to attach. With emit‑on‑completion, the *previous* transaction is out of the way as soon as it’s complete, so the first FX merchant line is never suppressed.

### 4.2 Handle “year digit + trailing content” correctly

When the `year_digit_pattern` matches and `group(2)` is non‑empty (e.g., `"4  Transfer from Pot 100.00 100.42"`), immediately:

* Finalise the date.
* **Replay** the trailing content substring through the same classification pipeline (as if it were a new line).
  This closes a real gap where content after the final year digit is silently dropped today. 

### 4.3 Keep FX meta lines simple and explicit

You already treat lines containing `'Amount:'` with `'EUR'` or `'USD'`, and lines containing `'rate:'`, as FX meta that should attach to the description. Keep that in place so we continue to form descriptions like:
`"LINGOM*RED London GBR Amount: EUR -109.50. Conversion rate: 1.170122."` (as per the PDF). 

### 4.4 No change to bank templates

The Monzo YAML correctly encodes the split‑date and header patterns and already documents that a “custom parser” is required for transactions; we don’t need to widen its regex scope. Leave `transaction_patterns` empty for Monzo and keep the custom code path. 

---

## 5) Implementation sketch (drop‑in changes)

> **Scope:** `src/parsers/monzo_parser.py` main loop between lines ~143–263 as per the brief. 

### 5.1 Helpers you’ll add

```python
def _txn_is_complete(current_date_incomplete, pending_year_digit, current_amounts):
    return bool(current_date_incomplete) and not pending_year_digit and len(current_amounts) >= 2

def _emit_current(transactions):
    tx = self._build_monzo_transaction(...)   # existing builder
    transactions.append(tx)

def _reset_txn_state():
    return [], [], False, None  # description_lines, amounts, pending_year_digit, current_date_incomplete
```

### 5.2 “Replay current line” mechanism

Introduce two local variables in the loop:

```python
replay_line = None   # type: Optional[str]
...
while i < range_end:
    raw_line = lines[i] if replay_line is None else replay_line
    if replay_line is None:
        i += 1
    else:
        replay_line = None

    line = raw_line  # keep original
```

This pattern lets you **not lose** the current line when you decide to emit the previous transaction and start a new one.

### 5.3 Replace the guard with “emit & replay”

In the **continuation line handler** (the `else:` branch where today we apply the problematic check):

```python
stripped = line.strip()
if stripped and not re.search(r'^\(GBP\)', stripped):

    if _txn_is_complete(current_date_incomplete, pending_year_digit, current_amounts):
        # ✅ We finished the previous transaction; start a new one with this line.
        _emit_current(transactions)
        # Reset state for next transaction
        current_description_lines = []
        current_amounts = []
        # NOTE: do NOT touch current_date_incomplete or pending_year_digit here.
        # The next transaction's date should already be in progress (or will come next).
        # Replay this same content through the pipeline:
        replay_line = stripped
        continue  # next loop iteration will reprocess the line

    # Normal path — accept the continuation line
    current_description_lines.append(stripped)
```

**Delete** the old `if len(current_amounts) >= 2 and not pending_year_digit: pass` guard entirely. 

### 5.4 Emit immediately when two amounts arrive *and* next token looks like a new record

In the **amounts branch**, after you `extend(current_amounts)` and optionally derive `desc_part`, add a **fast‑path**:

```python
if _txn_is_complete(current_date_incomplete, pending_year_digit, current_amounts):
    # Peek the next physical line if we didn't come from replay and it's not EOF.
    nxt = None if i >= range_end else lines[i]
    # Heuristic: If next line is a date or merchant-looking content (non-empty, not a footer),
    # emit now so we don't carry a complete txn forward.
    if nxt is None or date_pattern.match(nxt) or nxt.strip():
        _emit_current(transactions)
        current_description_lines = []
        current_amounts = []
        # Do not replay here; we haven't consumed 'nxt' yet; the loop continues naturally.
```

This reduces the window during which a “complete” previous transaction can interfere with upcoming content.

### 5.5 Year‑digit with trailing content

In the **year digit** branch:

```python
year_digit_match = year_digit_pattern.match(line)
if year_digit_match:
    current_date_incomplete += year_digit_match.group(1)
    pending_year_digit = False

    trailing = year_digit_match.group(2)
    if trailing:
        # reclassify the trailing text
        replay_line = trailing
        continue
    else:
        continue
```

This implements the safe handling of merged lines. 

---

## 6) Edge cases you must handle (and how)

1. **FX on same day, multiple back‑to‑back FX lines**
   Covered: emit‑on‑completion means each set of two amounts + balance finalises, and the next merchant line seeds the next transaction immediately (no description loss). Evidence of multi‑FX clusters in August in the PDF (e.g., repeated `LINGOM*RED …`). 

2. **“This relates to a previous transaction”** adjustment lines
   These appear with a single amount and explanatory text (e.g., UBER/Ebay examples in the PDF). Continue to treat the text as description and the amount as money in/out; they often complete the “pair” with the running balance on the next line. Your two‑amount completion rule still applies. 

3. **Date lines split across pages**
   Your validator already copes with period breaks; our change does not alter that. Ensure the footer skip regex is not so broad that it swallows date prefixes. (Observed footers are Monzo’s legal lines and “Pot statement” pages.) 

4. **Trailing text after year digit**
   Now captured and re‑classified per §5.5, so we won’t lose legitimate content when `pdftotext` folds lines. 

5. **Currencies other than EUR/USD**
   Your FX meta heuristic currently triggers on `EUR`/`USD`. If you encounter `IRL` it’s a country code in descriptions (Apple IRL), not a currency indicator; keep it out of the FX meta branch. (PDF shows `APPLE.COM/BILL … IRL` transactions repeatedly). 

---

## 7) Test plan (unit + integration)

### 7.1 Focused unit test for the failure case (from the brief)

* **Input (lines as parsed by `pdftotext`)** – exactly as specified in the brief’s test case.
* **Expected** – 3 transactions:

  1. `Transfer from Pot` 50.00 → balance 60.39
  2. `Kashia*Nyasa Nairobi KEN Amount: USD -38.04. Conversion rate: 1.268.` money‑out 30.00 → balance 10.39
  3. `Transfer from Pot` 35.00 → balance 40.39
     This must pass after the change. 

### 7.2 Golden tests against real PDF fragments

* **FX cluster** around 16–17 Aug (contains `LINGOM*RED … Amount: EUR … rate: 1.170122. … -93.58`): assert description concatenation and amounts. 
* **Small FX** around 12 Aug (`TIKTOK DUBLIN IRL Amount: EUR -1.10 … rate: 1.170213.`): ensure both the tiny amount and the balance are captured, with the “This relates …” adjustment lines nearby not corrupting order. 
* **Adjustment examples** (Ebay/UBER “This relates to a previous transaction”) to confirm they form valid rows and don’t collide with neighbours. 

### 7.3 Property tests

* Generate synthetic sequences with permutations of:

  * single‑line entries,
  * split‑date entries (date prefix + year digit),
  * FX meta lines (Amount:/rate:),
  * blank lines and footers.
    Check that **no continuation line is ever dropped** when `_txn_is_complete()` is true; instead, a transaction is emitted and the line is re‑classified.

### 7.4 Reconciliation gate

Run the **balance validator** over the full statement and require validation to improve materially from 27.6% (first failure at 2024‑08‑08) toward 100%. This is your regression guard for the entire change. 

---

## 8) Observability & safety rails

* **Structured debug logs (temporary)**
  Log when `_txn_is_complete()` flips to true and when an emit happens due to a non‑amount continuation line. Include a hash of `current_description_lines` and the two amounts so we can see “who” was emitted and “who” started.

* **Metric**
  Count how many lines are “replayed”. After stabilisation this should be rare except around FX and split‑year lines.

* **Feature flag (optional)**
  Gate the new behaviour (emit‑on‑completion + replay) behind a `MONZO_EMIT_ON_COMPLETION` flag for quick revert during rollout.

---

## 9) Complexity and risk

* **Time complexity** remains O(n) over lines; the replay mechanism never loops infinitely because each replay either emits a transaction or consumes the line.
* **Risk of over‑emitting** is mitigated by the strong completion predicate (date fully formed + two GBP amounts), which mirrors the table layout in the PDF. 

---

## 10) Worked example (how the loop behaves after the change)

Using the brief’s failing snippet:

1. Parse `Transfer from Pot 50.00 60.39` → `current_amounts = ['50.00', '60.39']`, date already set from prior context.
2. Next non‑amount arrives (blank or date prefix) → `_txn_is_complete()` is **true** → **emit** the Pot transfer immediately.
3. Date prefix `08/08/202` sets `current_date_incomplete='08/08/202'`, `pending_year_digit=True`.
4. Year digit `4` → `pending_year_digit=False`. Any trailing text is **replayed**.
5. Merchant `Kashia*Nyasa Nairobi KEN` now accrues to the **new** transaction (there is no longer a complete prior txn blocking it).
6. FX meta lines (`Amount: USD …`, `rate: 1.268.`) attach.
7. `-30.00` and `10.39` arrive → `_txn_is_complete()` flips true → **emit** `Kashia*Nyasa …` as a full row.

This yields exactly the expected three rows in the brief. 

---

## 11) Files that change (and ones that don’t)

* **Change:** `src/parsers/monzo_parser.py` — main loop (replace guard; add emit‑on‑completion + replay; handle year‑digit trailing). 
* **No change:** `data/bank_templates/monzo.yaml` (keep identifiers, header, date formats as‑is). 
* **No change needed:** `validators/balance_validator.py` (but use it to validate the fix over the full file). The validator already handles period breaks. 

---

## 12) Acceptance criteria

* FX merchants like **Kashia*Nyasa** and **APPERATOR** now appear with complete descriptions (`… Amount: <CUR> <amt>. Conversion rate: <rate>.`) and correct GBP amount & balance. 
* The specific failing block in the brief parses to **3** transactions exactly as specified. 
* Overall validated transactions rise significantly above **27.6%** toward parity with the parsed count; **first validation failure at 2024‑08‑08 disappears.** 

---

## 13) Notes on real‑world quirks we observed in the PDF

* FX sequences in mid‑August demonstrate the desired final shape (“merchant + Amount: … + rate: …” on one or two lines; then GBP figures). Use those as positive controls during manual QA. 
* Small FX + adjustment lines (e.g., TikTok, “This relates…”) must not be conflated with neighbouring entries; our emit‑on‑completion plus replay preserves boundaries. 

---

## 14) Why we didn’t choose alternatives in the brief

* **Look‑ahead buffering** (Option 2) adds complexity and risks brittle peek logic when footers/page breaks intervene. Emit‑on‑completion plus replay is simpler and strictly local in state. 
* **Two‑pass** boundary detection (Option 3) is heavy for a single bank template and unnecessary: the table layout gives us a strong single‑pass completion predicate (date complete + two GBP amounts). 
* **Dropping the guard without emit/replay** (Option 4) re‑introduces the original contamination bug. The proposed change *removes* the guard *and* eliminates the reason it existed. 

---

### Ready‑to‑ship checklist

* [ ] Replace “block after two amounts” with **emit & replay**. 
* [ ] Implement **year‑digit trailing text replay**. 
* [ ] Add focused unit test from the brief’s failing snippet. 
* [ ] Add golden tests for FX clusters (16–17 Aug, 12 Aug).  
* [ ] Run validator and record new reconciliation percentage; ensure first failure (08‑Aug) is gone. 

---

If you implement the above exactly, the merchant lines for FX transactions will no longer be dropped, and reconciliation should jump markedly without regressing contamination control for ordinary, single‑line rows.
