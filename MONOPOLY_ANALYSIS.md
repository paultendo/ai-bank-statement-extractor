# Monopoly Library Architecture Analysis

## Overview

The Monopoly library (by benjamin-awd) is a mature, production-ready bank statement parser that supports 17+ banks. Having their codebase as reference in `reference/monopoly/` will help us make informed architectural decisions.

## Key Architectural Patterns

### 1. **ETL Pipeline Pattern** (pipeline.py)

```python
class Pipeline:
    def extract() -> BaseStatement:
        # Extract transactions from PDF
        # Perform safety check (balance validation)

    def transform(statement) -> list[Transaction]:
        # Convert dates to ISO 8601
        # Handle cross-year logic

    def load(transactions, output_directory):
        # Write to CSV
```

**Learning**: They use a clear ETL pattern. We should adopt this too!

### 2. **Bank-Specific Configuration Classes** (not YAML)

Unlike our YAML approach, Monopoly uses **Python dataclasses** for bank configs:

```python
class Hsbc(BankBase):
    name = BankNames.HSBC

    credit = StatementConfig(
        statement_type=EntryType.CREDIT,
        statement_date_pattern=re.compile(r"..."),
        header_pattern=re.compile(r"..."),
        transaction_pattern=CreditTransactionPatterns.HSBC,
        transaction_date_format="%d %b",
        multiline_config=MultilineConfig(multiline_descriptions=True),
    )

    identifiers = [email_statement_identifier, web_statement_identifier]
    statement_configs = [credit]
```

**Our Approach vs Theirs**:
- **Monopoly**: Python dataclasses (type-safe, IDE support, but requires code changes)
- **Ours**: YAML configs (easy to edit, no code changes, but less type safety)
- **Verdict**: Our YAML approach is better for non-developers. Stick with it!

### 3. **StatementHandler Pattern** (handler.py)

```python
class StatementHandler:
    def __init__(self, parser: PdfParser):
        self.bank = parser.bank
        self.pages = parser.pages

    def get_header(self, config: StatementConfig) -> str | None:
        # Find header pattern in pages

    @cached_property
    def statement(self):
        # Detect statement type (debit vs credit)
        # Return DebitStatement or CreditStatement
```

**Learning**: They detect statement type (debit/credit) by looking for header patterns. We should add this capability!

### 4. **Multiline Description Handling** (base.py)

They have sophisticated logic for handling descriptions that span multiple lines:

```python
class DescriptionExtractor:
    def get_multiline_description(self, context: MatchContext) -> str:
        # Look at previous lines (within margin)
        # Append subsequent lines until break condition
        # Stop at: blank line, new transaction, or position mismatch
```

**Learning**: This is critical! Many UK banks (including NatWest) have multi-line descriptions. We MUST implement this.

### 5. **Safety Check (Balance Validation)**

```python
def extract(self, safety_check=True) -> BaseStatement:
    if safety_check and statement.config.safety_check:
        statement.perform_safety_check()
```

**Learning**: They validate by default but allow disabling for banks without totals. Good pattern!

### 6. **Cross-Year Date Logic**

```python
# If statement is from Jan/Feb but transaction is Dec, it's from previous year
is_cross_year = statement_date.month in (1, 2) and parsed_date.month > 2
if is_cross_year and needs_year:
    parsed_date = parsed_date.replace(year=parsed_date.year - 1)
```

**Learning**: Essential for statements that cross year boundaries!

## Code Organization Comparison

### Monopoly Structure:
```
monopoly/
├── banks/           # Bank-specific implementations (Python classes)
│   ├── hsbc/
│   ├── citibank/
│   └── base.py
├── statements/      # Statement types (debit/credit)
│   ├── base.py
│   ├── debit_statement.py
│   └── credit_statement.py
├── config.py        # Configuration dataclasses
├── handler.py       # Statement detection & extraction
├── pipeline.py      # ETL orchestration
└── pdf.py           # PDF parsing
```

### Our Structure:
```
src/
├── models/          # Data models (similar to their statements/)
├── extractors/      # PDF, OCR, Vision API
├── parsers/         # Transaction parsing logic
├── validators/      # Balance validation
├── exporters/       # Excel output
└── config/          # YAML-based bank configs
```

**Verdict**: Our structure is more modular. Their approach bundles everything into bank classes, ours separates concerns better.

## Key Differences

| Aspect | Monopoly | Our Implementation |
|--------|----------|-------------------|
| **Config Format** | Python dataclasses | YAML files |
| **Output Format** | CSV only | Excel (with metadata sheets) |
| **Bank Detection** | PDF metadata + text identifiers | Text identifiers only |
| **PDF Library** | pdftotext (command-line) | pdfplumber (Python library) |
| **OCR Support** | Limited (via PDF config) | Dedicated OCR extractor |
| **Vision API** | None | Claude & OpenAI Vision |
| **Use Case** | General bank statements | UK legal evidence (higher accuracy req) |
| **Multiline Handling** | Advanced (with margins) | Need to implement! |
| **Date Parsing** | dateparser library | python-dateutil + custom logic |

## Critical Features We Must Adopt

### 1. **Multiline Description Handling** ⚠️ HIGH PRIORITY

NatWest statements have multi-line descriptions. We MUST implement this:

```python
# Example from NatWest:
"""
19 DEC  OnLine Transaction
        VIA MOBILE
        PYMT FROM MR J SMITH
        REF 12345678              45.00    1,234.56
"""
```

**Action**: Implement `DescriptionExtractor` class in our parser.

### 2. **Cross-Year Date Logic** ⚠️ MEDIUM PRIORITY

```python
# Statement date: 05 Jan 2025
# Transaction: "28 DEC TESCO 45.67"
# Needs to be parsed as: 28 Dec 2024 (not 2025!)
```

**Action**: Add to our `date_parser.py`.

### 3. **Statement Type Detection** ⚠️ MEDIUM PRIORITY

They detect debit vs credit statements. We should too:

```yaml
# In bank config:
statement_types:
  - type: debit
    header_pattern: "Date.*Description.*Paid In.*Withdrawn.*Balance"
  - type: credit
    header_pattern: "Date.*Description.*Amount"
```

**Action**: Add to our bank YAML schema.

### 4. **Transaction Bounds** ⚠️ LOW PRIORITY

They filter out "noise" transactions (like "BALANCE B/F") by checking if amount is too far right:

```python
transaction_bound: int = 32  # Ignore if amount is > 32 spaces from start
```

**Action**: Consider adding to YAML config.

## What NOT to Adopt

### 1. **PDF Metadata Identifiers**
They use PDF metadata to detect banks. Our approach (text-based) is simpler and sufficient.

### 2. **Command-Line pdftotext**
We use pdfplumber (pure Python), which is easier to install and more portable.

### 3. **CSV-Only Output**
Legal industry needs Excel with multiple sheets. Our approach is better for the use case.

## Implementation Recommendations

### Phase 1: Core Parser with Monopoly Patterns

1. **Update our transaction parser** to handle:
   - Multi-line descriptions (using margin-based logic)
   - Cross-year dates
   - Transaction bounds (optional)

2. **Enhance date parser**:
   ```python
   def parse_date_with_year_inference(
       date_str: str,
       statement_date: datetime,
       date_formats: list[str]
   ) -> datetime:
       # Parse date
       # If no year, infer from statement_date
       # Apply cross-year logic
   ```

3. **Add statement type detection**:
   ```python
   def detect_statement_type(text: str, bank_config: BankConfig) -> str:
       # Check header patterns for debit/credit
   ```

### Phase 2: Safety Check Implementation

```python
# In validators/balance_validator.py
def perform_safety_check(statement: Statement, transactions: list[Transaction]) -> bool:
    """
    Validate that transactions reconcile with statement totals.

    Checks:
    - Opening balance + sum(money_in) - sum(money_out) = Closing balance
    - Each transaction balance is correct
    """
```

### Phase 3: Multi-Bank Support

Study their bank implementations:
- HSBC: `reference/monopoly/src/monopoly/banks/hsbc/`
- Citibank: `reference/monopoly/src/monopoly/banks/citibank/`
- Standard Chartered: `reference/monopoly/src/monopoly/banks/standard_chartered/`

Convert their regex patterns to our YAML format.

## Code We Can Reference

### Key Files to Study:

1. **Multi-line description logic**:
   - `reference/monopoly/src/monopoly/statements/base.py` (lines 35-136)

2. **Date parsing with year inference**:
   - `reference/monopoly/src/monopoly/pipeline.py` (lines 73-112)

3. **Transaction extraction**:
   - `reference/monopoly/src/monopoly/statements/debit_statement.py`

4. **Safety check implementation**:
   - `reference/monopoly/src/monopoly/statements/base.py` (search for `perform_safety_check`)

5. **Bank configurations**:
   - `reference/monopoly/src/monopoly/banks/hsbc/hsbc.py`
   - `reference/monopoly/src/monopoly/banks/citibank/`

## Testing Approach

They have comprehensive tests:
```
reference/monopoly/tests/
├── banks/                    # Bank-specific tests
├── integration/              # End-to-end tests
└── unit/                     # Unit tests
```

**Action**: Mirror this structure in our tests.

## Next Steps

### Immediate (This Week):

1. ✅ Clone Monopoly repo to `reference/monopoly/` (DONE)
2. ⏳ Implement multiline description handling
3. ⏳ Add cross-year date logic
4. ⏳ Build transaction parser using these patterns

### Short Term (Next Week):

5. Study their safety check implementation
6. Convert HSBC config to our YAML format
7. Test with real statements

### Long Term:

8. Study all 17 bank implementations
9. Extract common patterns
10. Build generic fallback parser (like their GenericBank)

## Conclusion

**Monopoly validates our architecture!** Key takeaways:

✅ **What we're doing right**:
- Modular structure (extractors, parsers, validators, exporters)
- Configuration-driven approach
- Balance validation ("safety check")
- Cascading extraction strategies

⚠️ **What we need to add**:
- Multi-line description handling (CRITICAL for UK banks)
- Cross-year date logic
- Statement type detection

💡 **What we're doing better**:
- YAML configs (easier for non-developers)
- Excel output (better for legal use case)
- Vision API integration (handles poor quality scans)
- Separate OCR extractor (more flexibility)

---

**Reference Location**: `reference/monopoly/`

**Key Contact**: benjamin-awd (GitHub)

**License**: Do not use their code directly but the developer is fine with us referencing theirs and building our version as it will be better.

**Last Updated**: 2025-10-11
