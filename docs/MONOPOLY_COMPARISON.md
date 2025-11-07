# Monopoly Comparison & Learning Analysis

## Executive Summary

[Monopoly](https://github.com/benjamin-awd/monopoly) is a mature, well-architected bank statement parser with **815 commits**, **64 stars**, and **32 forks**. This document analyzes their approach to help us improve our own implementation.

**Key Stats:**
- **Supported Banks**: 17 (international focus: Canada, Singapore, US)
- **Code Size**: 4,071 lines source + 2,179 lines tests
- **Architecture**: Configuration-driven with smart fallbacks
- **Output**: CSV files
- **License**: AGPL 3.0

---

## Architecture Comparison

### Monopoly's Approach

**Configuration Over Inheritance:**
```python
# Each bank is a simple class with config dataclasses
class Dbs(BankBase):
    name = BankNames.DBS

    credit = StatementConfig(
        statement_type=EntryType.CREDIT,
        transaction_pattern=CreditTransactionPatterns.DBS,
        header_pattern=r"^Transaction Date.*Description.*Amount",
        statement_date_pattern=r"Statement Date:\s+(\d{2}\s\w{3}\s\d{4})",
        multiline_config=MultilineConfig(...),
        transaction_bound=170  # Ignore amounts past column 170
    )

    debit = StatementConfig(...)  # Different format

    statement_configs = [credit, debit]  # Try in order
```

**Benefits:**
- Banks are ~30-50 lines each
- Easy to add new banks without modifying base classes
- Multiple formats per bank supported naturally
- Configuration is declarative and testable

### Our Current Approach

**Class-Based Parsers:**
```python
class BarclaysParser(BaseTransactionParser):
    def parse_transactions(self, text, start_date, end_date):
        # 200+ lines of parsing logic
        # Regex patterns defined inline
        # Column detection mixed with parsing
```

**Benefits:**
- Maximum flexibility for complex cases
- Bank-specific optimizations easy to add
- Already works well for UK banks

**Drawbacks:**
- Parsers are longer and harder to maintain
- Patterns not easily reusable
- Adding banks requires more code

---

## Key Learnings & What We Should Adopt

### 1. ✅ **Configuration-Based Pattern Management**

**Their Approach:**
```python
@dataclass(kw_only=True)
class StatementConfig:
    statement_type: EntryType  # CREDIT or DEBIT
    transaction_pattern: Pattern[str]
    header_pattern: Pattern[str]
    statement_date_pattern: Pattern[str]
    transaction_bound: int | None = None  # Column limit
    multiline_config: MultilineConfig = ...
    safety_check: bool = True  # Balance validation
```

**What We Could Do:**
- Enhance our YAML bank templates with more structured configs
- Add `transaction_bound` to prevent false matches in margins
- Standardize multiline handling configuration

**Action Item:** Consider creating a `BankConfig` dataclass that validates our YAML configs.

---

### 2. ✅ **Polymorphic Bank Detection**

**Their System:**
```python
class TextIdentifier(Identifier):
    """Match text in PDF content"""
    text: str

class MetadataIdentifier(Identifier):
    """Match PDF metadata"""
    creator: str
    producer: str

# Example usage:
identifiers = [
    [TextIdentifier("DBS"), MetadataIdentifier(creator="Quadient")],
    [TextIdentifier("POSB")]  # Alternative identifier group
]
```

**What We Could Do:**
- Extend bank detection beyond simple text matching
- Add PDF metadata checking (creator, producer)
- Support multiple identifier strategies per bank

**Action Item:** Create `src/utils/bank_detector.py` with identifier classes.

---

### 3. ✅ **Generic Fallback Parser** (BRILLIANT!)

**Their Innovation:**
When a PDF doesn't match any known bank, Monopoly doesn't fail—it auto-detects patterns:

```python
class DatePatternAnalyzer:
    def analyze(self, pdf_text):
        # Scans for common date patterns
        # Finds transaction columns
        # Builds regex dynamically
        return GenericStatementConfig(
            transaction_pattern=self.create_transaction_pattern(),
            date_format=self.detected_format
        )
```

**How It Works:**
1. Scans all lines for date patterns (DD/MM/YYYY, MM/DD, etc.)
2. Determines how many date columns exist
3. Builds a transaction regex from detected patterns
4. Falls back gracefully instead of failing

**What We Could Do:**
- Add generic parser as fallback before Vision API
- Cheaper than LLM, more reliable than failing
- Sequence: Known Parser → Generic Parser → Vision API

**Action Item:** Implement `src/parsers/generic_parser.py` using pattern analysis.

---

### 4. ✅ **Transaction Bound (Prevents False Positives)**

```python
# DBS Config
transaction_bound=170  # Ignore amounts past column 170

# In parser:
if amount_position > config.transaction_bound:
    continue  # Skip, it's metadata/artifact
```

**Why This Matters:**
- PDFs often have page numbers, headers, footers with amounts
- Column bounds prevent parsing these as transactions
- Significantly reduces false positives

**What We Should Do:**
- Add `max_column_position` to our YAML configs
- Apply bounds in our column detection utilities

**Action Item:** Add `transaction_bound` to bank templates and enforce in parsers.

---

### 5. ✅ **Multiline Configuration**

```python
multiline_config=MultilineConfig(
    multiline_descriptions=True,
    description_margin=10,      # Lines within 10 chars of start
    include_prev_margin=3,      # Include previous line if within 3 chars
)
```

**What This Enables:**
- Declarative multiline handling (no custom logic per bank)
- Configurable indentation rules
- Handles complex layouts systematically

**What We Could Do:**
- Add multiline config to our bank YAML templates
- Standardize continuation line detection

**Action Item:** Add `multiline_config` section to bank templates.

---

### 6. ✅ **Cross-Year Date Handling**

**Their Smart Logic:**
```python
def convert_date(tx, statement_date):
    # Statement from Jan 2024, transaction shows "Dec"
    # Assume Dec is from 2023 (previous year)

    is_cross_year = (
        statement_date.month in (1, 2) and
        parsed_date.month > 2
    )

    if is_cross_year:
        parsed_date = parsed_date.replace(year=parsed_date.year - 1)
```

**What We Should Do:**
- Add cross-year logic to `src/utils/date_parser.py`
- Handle statements spanning year boundaries correctly

**Action Item:** Implement cross-year date inference in utilities.

---

### 7. ✅ **Parameterized Integration Tests**

**Their Test Pattern:**
```python
@pytest.mark.parametrize(
    "bank, expected_debit_sum, expected_credit_sum, statement_date",
    [
        (Dbs, 2222.68, 1302.88, datetime(2023, 10, 31)),
        (Maybank, 5275.61, 4093.7, datetime(2023, 8, 31)),
        (Ocbc, 6630.79, 5049.55, datetime(2023, 10, 31)),
    ]
)
def test_bank_debit_statements(bank, expected_debit_sum, ...):
    # Test extraction
    # Test balance reconciliation
    # Test transformation
```

**Test Fixtures:**
```
tests/banks/dbs/
├── credit/
│   ├── input.pdf
│   ├── raw.csv          # Expected extracted transactions
│   └── transformed.csv  # Expected post-pipeline output
└── debit/
    └── (same)
```

**What We Should Do:**
- Create test fixtures for each bank with expected outputs
- Use parameterized tests to reduce duplication
- Test both extraction AND balance reconciliation

**Action Item:** Create `tests/fixtures/` with sample statements + expected CSVs.

---

### 8. ✅ **ETL Pipeline Pattern**

**Their Clean Separation:**
```python
class Pipeline:
    def extract(self) -> Statement:
        """Extract raw transactions from PDF"""

    def transform(self, statement) -> list[dict]:
        """Convert to standard format (ISO dates, etc)"""

    def load(self, transactions, output_dir):
        """Write to CSV"""
```

**What We Have:**
- We already have `ExtractionPipeline` but it's more monolithic
- Could benefit from clearer ETL separation

**Action Item:** Consider refactoring pipeline into explicit extract/transform/load stages.

---

## Features Monopoly Has That We Don't

### 1. Generic Parser
- **Status**: They have it, we don't
- **Value**: High - graceful degradation
- **Effort**: Medium - requires pattern analysis logic
- **Priority**: ⭐⭐⭐

### 2. Transaction Bounds
- **Status**: They have it, we don't
- **Value**: Medium - reduces false positives
- **Effort**: Low - just add config + check
- **Priority**: ⭐⭐

### 3. Polymorphic Identifiers
- **Status**: They have it, we don't
- **Value**: Medium - better bank detection
- **Effort**: Medium - new abstraction needed
- **Priority**: ⭐⭐

### 4. Cross-Year Logic
- **Status**: They have it, we don't
- **Value**: Medium - handles edge cases
- **Effort**: Low - utility function
- **Priority**: ⭐⭐

### 5. CSV Fixtures for Tests
- **Status**: They have it, we don't
- **Value**: High - better test coverage
- **Effort**: Medium - create fixtures
- **Priority**: ⭐⭐⭐

---

## Features We Have That Monopoly Doesn't

### 1. ✅ **Excel Multi-Sheet Output**
- **Their Approach**: CSV only
- **Our Advantage**: Excel with Transactions + Metadata + Extraction Log sheets
- **Value for Legal Cases**: High - better for evidence presentation
- **Keep**: YES

### 2. ✅ **Vision API Fallback**
- **Their Approach**: Generic pattern matching only
- **Our Advantage**: Claude Vision API for poor quality scans
- **Value**: High - handles edge cases they can't
- **Keep**: YES

### 3. ✅ **Confidence Scoring**
- **Their Approach**: Binary safety check only
- **Our Advantage**: Per-transaction confidence percentages
- **Value**: High - transparency for legal use
- **Keep**: YES

### 4. ✅ **Advanced Analytics**
- **Their Approach**: No analytics (just extraction)
- **Our Advantage**: Fraud detection, gambling analysis, lifestyle spending
- **Value**: Very High - unique to our legal use case
- **Keep**: YES (major differentiator)

### 5. ✅ **Streamlit UI**
- **Their Approach**: CLI only (+ demo site)
- **Our Advantage**: Batch upload, side-by-side view, analytics dashboard
- **Value**: High - better UX for non-technical users
- **Keep**: YES

### 6. ✅ **UK Bank Focus**
- **Their Approach**: International (Canada, Singapore, US)
- **Our Advantage**: Deep UK bank support (Barclays, HSBC, NatWest, Monzo, etc.)
- **Value**: High for UK legal market
- **Keep**: YES

---

## Recommended Action Plan

### Phase 1: Quick Wins (Week 1)
1. ✅ Add `transaction_bound` to bank YAML templates
2. ✅ Implement cross-year date logic in `date_parser.py`
3. ✅ Create CSV test fixtures for existing banks
4. ✅ Add multiline config to YAML templates

### Phase 2: Medium Effort (Week 2-3)
5. ⚠️ Implement generic fallback parser with pattern analysis
6. ⚠️ Add polymorphic bank identifier system
7. ⚠️ Refactor pipeline to explicit ETL stages
8. ⚠️ Create parameterized integration tests

### Phase 3: Optional Enhancements (Future)
9. 🔮 Consider hybrid approach: config for simple banks, custom parsers for complex
10. 🔮 Add PDF metadata checking to bank detection
11. 🔮 Implement safety check as explicit balance validator
12. 🔮 Create bank addition template (like their `example_bank.py`)

---

## File Reference Guide

Key files to study in Monopoly codebase:

| File | What to Learn | Lines | Priority |
|------|---------------|-------|----------|
| `src/monopoly/config.py` | StatementConfig design | 108 | ⭐⭐⭐ |
| `src/monopoly/banks/base.py` | Base architecture | 38 | ⭐⭐⭐ |
| `src/monopoly/generic/patterns.py` | Pattern analysis | 100+ | ⭐⭐⭐ |
| `src/monopoly/pipeline.py` | ETL orchestration | 157 | ⭐⭐ |
| `src/monopoly/banks/detector.py` | Bank detection | 42 | ⭐⭐ |
| `src/monopoly/identifiers.py` | Identifier system | 66 | ⭐⭐ |
| `tests/integration/test_banks_debit.py` | Test patterns | 59 | ⭐⭐ |

---

## Comparison Table

| Aspect | Monopoly | Our Project | Winner |
|--------|----------|-------------|--------|
| **Architecture** | Configuration-driven | Class-based parsers | Monopoly (simpler) |
| **Banks Supported** | 17 (international) | 8+ (UK-focused) | Tie (different markets) |
| **Fallback Strategy** | Generic pattern analysis | Vision API | Our Project (more powerful) |
| **Output Format** | CSV only | Excel (multi-sheet) | Our Project |
| **Analytics** | None | Advanced legal analytics | Our Project |
| **UI** | CLI only | Streamlit + batch mode | Our Project |
| **Testing** | Parameterized with fixtures | Growing | Monopoly (more mature) |
| **Code Complexity** | Lower (config-driven) | Higher (custom logic) | Monopoly |
| **Flexibility** | Medium | High | Our Project |
| **Maintenance** | Easier (declarative) | Harder (imperative) | Monopoly |
| **Bank Addition** | Very easy (~30 lines) | Medium (~200 lines) | Monopoly |
| **Edge Case Handling** | Generic parser | Vision API | Our Project |

---

## Key Takeaways

### What Monopoly Does Better
1. **Simplicity**: Configuration-driven approach is easier to maintain
2. **Testability**: Parameterized tests with CSV fixtures
3. **Graceful Degradation**: Generic parser for unknown banks
4. **Bank Addition**: Very low barrier to add new banks

### What We Do Better
1. **Power**: Vision API handles cases they can't
2. **Output**: Excel format better for legal evidence
3. **Analytics**: Unique value-add for legal cases
4. **UX**: Streamlit UI more accessible
5. **Confidence**: Scoring system for transparency

### Hybrid Approach Recommendation

**For Simple Banks** (standard table layouts):
- Use configuration-driven approach like Monopoly
- Store patterns in enhanced YAML templates
- Reduce custom parser code

**For Complex Banks** (irregular layouts, special cases):
- Keep custom parser classes
- Use Vision API fallback
- Maintain flexibility

**For Unknown Banks**:
1. Try generic pattern analysis (Monopoly's approach)
2. Fall back to Vision API (our approach)
3. Log for future bank addition

This gives us **best of both worlds**: Monopoly's elegance for simple cases + our power for complex cases.

---

**Document Version**: 1.0
**Last Updated**: October 2024
**Next Review**: After implementing Phase 1 quick wins
