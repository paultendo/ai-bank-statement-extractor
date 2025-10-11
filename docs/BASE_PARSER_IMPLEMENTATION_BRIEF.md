# Base Parser Implementation Brief

## Executive Summary

All three UK bank parsers (Halifax, HSBC, NatWest) have achieved 100% validation rates through independent implementations. Analysis reveals **8 major common patterns** that should be extracted into a base parser, while **4 key areas** require bank-specific strategies.

**Goal**: Create a `BaseStatementParser` that reduces code duplication by ~60% while maintaining 100% validation rates and enabling rapid addition of new banks.

---

## Current State Analysis

### Success Metrics
- **Halifax**: 100% validation (12/12 periods), ~400 transactions
- **HSBC**: 100% validation (4/4 periods), ~96 transactions
- **NatWest**: 100% validation (43/43 periods), ~1095 transactions
- **Total**: 100% validation across 59 periods, 1591 transactions

### Code Duplication
Approximately **650 lines of similar code** across the three parsers, including:
- Date tracking logic: ~40 lines × 3 = 120 lines
- Multi-line description collection: ~35 lines × 3 = 105 lines
- Amount extraction: ~25 lines × 3 = 75 lines
- Balance validation: ~45 lines × 3 = 135 lines
- Year inference: ~15 lines × 3 = 45 lines
- Transaction creation: ~30 lines × 3 = 90 lines
- Dynamic column detection: ~35 lines × 2 = 70 lines (HSBC & NatWest)

---

## Architecture Design

### 1. Core Base Parser Class

```python
class BaseStatementParser:
    """
    Base parser implementing common UK bank statement parsing patterns.

    All UK banks share these characteristics:
    - PDF layout-based extraction (pdftotext -layout)
    - Date tracking (one date → multiple transactions)
    - Multi-line descriptions
    - Amount + balance extraction
    - Balance validation (calculated vs actual)
    - Period-aware parsing

    Banks override specific methods for:
    - Transaction classification (type code vs position vs keywords)
    - Period detection (Page markers vs BROUGHT FORWARD vs none)
    - Balance validation strategy (swap vs swap+recalc)
    - Special quirk handling
    """

    def __init__(self, config: BankParserConfig):
        self.config = config
        self.classification_strategy = self._create_classification_strategy()
        self.validation_strategy = self._create_validation_strategy()
        self.special_handlers = self._register_special_handlers()

    # === COMMON METHODS (Implemented in Base) ===

    def parse_text(self, text: str, start_date, end_date) -> List[Transaction]:
        """Main parsing entry point - template method pattern"""

    def _extract_date(self, line: str) -> Optional[datetime]:
        """Extract date from line using bank's date patterns"""

    def _track_date(self, line: str) -> Optional[datetime]:
        """Date tracking: one date applies to multiple transactions"""

    def _collect_multiline_description(self, lines, current_idx) -> str:
        """Look backwards to collect description lines"""

    def _extract_amounts_with_positions(self, line: str) -> List[Tuple[float, int]]:
        """Extract all amounts and their positions"""

    def _detect_and_update_columns(self, line: str) -> bool:
        """Detect table headers and update column thresholds"""

    def _infer_year(self, date_str: str) -> datetime:
        """Add year using statement period"""

    def _validate_balance(self, transaction, prev_transaction) -> Transaction:
        """Balance validation using configured strategy"""

    def _detect_period_boundary(self, line: str) -> bool:
        """Check if line marks period boundary"""

    def _create_transaction(self, **kwargs) -> Transaction:
        """Create Transaction object with confidence scoring"""

    # === ABSTRACT METHODS (Must implement in subclass) ===

    def _classify_amount(self, amount, position, description, type_code) -> str:
        """Classify as money_in or money_out - BANK SPECIFIC"""
        raise NotImplementedError

    def _parse_period_marker(self, line: str) -> Optional[PeriodInfo]:
        """Parse bank-specific period markers - BANK SPECIFIC"""
        raise NotImplementedError
```

### 2. Configuration Schema

```python
@dataclass
class BankParserConfig:
    """Configuration for bank-specific parsing behavior"""

    # Basic Info
    bank_name: str

    # Extraction
    extraction_method: str = "pdftotext_layout"  # All use this currently

    # Date Patterns
    date_formats: List[str]  # e.g., ["%d %b", "%d/%m/%Y"]
    date_pattern: str  # Regex to find date in line

    # Period Detection
    period_boundary_pattern: Optional[str]  # e.g., "Page (\d+) of", "BROUGHT FORWARD"
    period_type: str  # "page_marker", "text_marker", "none"

    # Column Detection
    header_pattern: Optional[str]  # e.g., "Date.*Description.*Paid In.*Withdrawn"
    enable_dynamic_columns: bool = True
    default_column_thresholds: Dict[str, int] = None  # Fallback if no header found

    # Classification
    classification_strategy: str  # "type_code", "column_position", "keyword", "hybrid"
    classification_config: Dict  # Strategy-specific config

    # Balance Validation
    validation_mode: str  # "swap_only", "swap_and_recalculate", "cascading_recalculate"
    trust_pdf_balance: bool = True
    balance_tolerance: float = 0.01  # £0.01 tolerance

    # Special Handlers
    special_handlers: List[str] = []  # e.g., ["brought_forward_quirk"]

    # Transaction Types
    transaction_types: Dict[str, TransactionType]  # Map codes to types
```

### 3. Classification Strategies (Strategy Pattern)

```python
class ClassificationStrategy(ABC):
    """Base class for amount classification strategies"""

    @abstractmethod
    def classify(self, amount: float, position: int,
                 description: str, type_code: Optional[str]) -> str:
        """Return 'money_in' or 'money_out'"""
        pass

class TypeCodeStrategy(ClassificationStrategy):
    """Halifax: Prioritize type codes, fallback to position"""

    def __init__(self, config: Dict):
        self.money_in_codes = config['money_in_codes']  # ['FPI', 'PI']
        self.money_out_codes = config['money_out_codes']  # ['FPO', 'DD', 'CHG']
        self.position_threshold = config.get('position_threshold', 40)

    def classify(self, amount, position, description, type_code):
        if type_code in self.money_in_codes:
            return 'money_in'
        elif type_code in self.money_out_codes:
            return 'money_out'
        else:
            # Fallback: position relative to balance
            return 'money_in' if distance_from_balance > 40 else 'money_out'

class ColumnPositionStrategy(ClassificationStrategy):
    """HSBC: Use dynamic column thresholds"""

    def __init__(self, config: Dict):
        self.paid_out_threshold = config.get('paid_out_threshold', 64)
        self.paid_in_threshold = config.get('paid_in_threshold', 90)

    def classify(self, amount, position, description, type_code):
        if position <= self.paid_out_threshold:
            return 'money_out'
        elif position <= self.paid_in_threshold:
            return 'money_in'
        else:
            # This is the balance column
            return None

class KeywordStrategy(ClassificationStrategy):
    """NatWest: Use keywords in description"""

    def __init__(self, config: Dict):
        self.money_in_keywords = config['money_in_keywords']
        self.money_out_keywords = config['money_out_keywords']

    def classify(self, amount, position, description, type_code):
        desc_lower = description.lower()

        # Check money in keywords
        if any(kw in desc_lower for kw in self.money_in_keywords):
            return 'money_in'

        # Check money out keywords
        if any(kw in desc_lower for kw in self.money_out_keywords):
            return 'money_out'

        # Default to money out
        return 'money_out'
```

### 4. Balance Validation Strategies

```python
class BalanceValidationStrategy(ABC):
    """Base class for balance validation strategies"""

    @abstractmethod
    def validate(self, transaction: Transaction,
                 prev_transaction: Transaction) -> Transaction:
        """Validate and potentially correct transaction"""
        pass

class SwapOnlyStrategy(BalanceValidationStrategy):
    """Halifax/HSBC: Swap direction if mismatch, trust PDF balance"""

    def validate(self, transaction, prev_transaction):
        if not prev_transaction:
            return transaction

        balance_change = transaction.balance - prev_transaction.balance
        calculated_change = transaction.money_in - transaction.money_out

        if abs(calculated_change - balance_change) > 0.01:
            # Swap direction
            transaction.money_in, transaction.money_out = \
                transaction.money_out, transaction.money_in

        return transaction

class SwapAndRecalculateStrategy(BalanceValidationStrategy):
    """NatWest: Swap direction, and recalculate balance if still wrong"""

    def validate(self, transaction, prev_transaction):
        if not prev_transaction:
            return transaction

        balance_change = transaction.balance - prev_transaction.balance
        calculated_change = transaction.money_in - transaction.money_out

        if abs(calculated_change - balance_change) > 0.01:
            # Swap direction
            transaction.money_in, transaction.money_out = \
                transaction.money_out, transaction.money_in

            # Recalculate expected change after swap
            calculated_change_after = transaction.money_in - transaction.money_out

            # If STILL wrong, PDF balance is wrong
            if abs(calculated_change_after - balance_change) > 0.01:
                transaction.balance = prev_transaction.balance + \
                    transaction.money_in - transaction.money_out

        return transaction

class CascadingRecalculateStrategy(BalanceValidationStrategy):
    """NatWest: For periods with PDF errors, calculate all balances"""

    def __init__(self):
        self.recalculate_mode = False

    def enable_recalculation(self):
        """Enable recalculation for rest of period"""
        self.recalculate_mode = True

    def disable_recalculation(self):
        """Reset at period boundary"""
        self.recalculate_mode = False

    def validate(self, transaction, prev_transaction):
        if self.recalculate_mode and prev_transaction:
            # Recalculate balance, ignore PDF value
            transaction.balance = prev_transaction.balance + \
                transaction.money_in - transaction.money_out

        return transaction
```

### 5. Special Handlers (Registry Pattern)

```python
class SpecialHandler(ABC):
    """Base class for bank-specific quirk handlers"""

    @abstractmethod
    def can_handle(self, transaction, prev_transaction, context) -> bool:
        """Check if this handler should be applied"""
        pass

    @abstractmethod
    def handle(self, transaction, prev_transaction, context) -> Transaction:
        """Apply special handling"""
        pass

class BroughtForwardQuirkHandler(SpecialHandler):
    """
    NatWest: First transaction after BROUGHT FORWARD shows BF balance
    instead of balance after transaction.
    """

    def can_handle(self, transaction, prev_transaction, context):
        if not prev_transaction:
            return False

        # Check if prev is BROUGHT FORWARD with zero amounts
        is_bf = ('BROUGHT FORWARD' in prev_transaction.description.upper() and
                 prev_transaction.money_in == 0 and
                 prev_transaction.money_out == 0)

        # Check if current balance equals BF balance (unchanged)
        balance_unchanged = abs(transaction.balance - prev_transaction.balance) < 0.01

        # Check if current has transaction amount
        has_amount = transaction.money_in > 0 or transaction.money_out > 0

        return is_bf and balance_unchanged and has_amount

    def handle(self, transaction, prev_transaction, context):
        # Calculate correct balance
        corrected_balance = prev_transaction.balance + \
            transaction.money_in - transaction.money_out

        transaction.balance = corrected_balance

        # Enable cascading recalculation for this period
        if hasattr(context, 'validation_strategy'):
            context.validation_strategy.enable_recalculation()

        return transaction

# Handler Registry
class HandlerRegistry:
    """Manages special handlers"""

    def __init__(self):
        self.handlers = {
            'brought_forward_quirk': BroughtForwardQuirkHandler(),
            # Future handlers...
        }

    def apply_handlers(self, transaction, prev_transaction,
                       handler_names, context):
        """Apply registered handlers"""
        for name in handler_names:
            handler = self.handlers.get(name)
            if handler and handler.can_handle(transaction, prev_transaction, context):
                transaction = handler.handle(transaction, prev_transaction, context)

        return transaction
```

---

## Implementation Plan

### Phase 1: Create Base Parser Infrastructure (Week 1)

**Goals:**
- Create `BaseStatementParser` class
- Implement 8 common methods
- Create configuration schema
- Write comprehensive tests

**Tasks:**
1. Create `src/parsers/base_statement_parser.py`
2. Implement common methods:
   - `_extract_date()`
   - `_track_date()`
   - `_collect_multiline_description()`
   - `_extract_amounts_with_positions()`
   - `_detect_and_update_columns()`
   - `_infer_year()`
   - `_create_transaction()`
   - `_detect_period_boundary()`
3. Create `src/parsers/parser_config.py` with configuration classes
4. Create `tests/test_parsers/test_base_parser.py`

**Success Criteria:**
- All common methods tested independently
- 100% test coverage for base methods
- Documentation complete

### Phase 2: Implement Strategy Classes (Week 2)

**Goals:**
- Create pluggable classification strategies
- Create pluggable validation strategies
- Create handler registry

**Tasks:**
1. Create `src/parsers/strategies/classification_strategies.py`:
   - `TypeCodeStrategy`
   - `ColumnPositionStrategy`
   - `KeywordStrategy`
2. Create `src/parsers/strategies/validation_strategies.py`:
   - `SwapOnlyStrategy`
   - `SwapAndRecalculateStrategy`
   - `CascadingRecalculateStrategy`
3. Create `src/parsers/strategies/special_handlers.py`:
   - `HandlerRegistry`
   - `BroughtForwardQuirkHandler`
4. Write comprehensive tests for each strategy

**Success Criteria:**
- Each strategy tested independently
- Strategies can be swapped without affecting base parser
- Handler registry functional

### Phase 3: Create Bank Configurations (Week 2-3)

**Goals:**
- Define configuration for each bank
- Validate configurations work with strategies

**Tasks:**
1. Create `data/bank_templates/halifax.yaml`:
```yaml
bank_name: Halifax
classification_strategy: type_code
classification_config:
  money_in_codes: [FPI, PI, BGC, DEP]
  money_out_codes: [FPO, DD, CHG, FEE, SO, CPT]
  position_threshold: 40
validation_mode: swap_only
period_boundary_pattern: "Page (\\d+) of (\\d+)"
period_type: page_marker
date_formats: ["%d %b %Y", "%d %b"]
date_pattern: "^(\\d{1,2}\\s+[A-Z]{3}(?:\\s+\\d{4})?)"
```

2. Create `data/bank_templates/hsbc.yaml`:
```yaml
bank_name: HSBC
classification_strategy: column_position
classification_config:
  paid_out_threshold: 64
  paid_in_threshold: 90
validation_mode: swap_only
period_boundary_pattern: "BALANCE\\s+(BROUGHT|CARRIED)\\s+FORWARD"
period_type: text_marker
enable_dynamic_columns: true
header_pattern: "Paid\\s+out.*Paid\\s+in.*Balance"
date_formats: ["%d %b %y", "%d %b %Y"]
```

3. Create `data/bank_templates/natwest.yaml`:
```yaml
bank_name: NatWest
classification_strategy: keyword
classification_config:
  money_in_keywords: [automated credit, cash & dep, deposit]
  money_out_keywords: [online transaction, direct debit, card transaction]
validation_mode: swap_and_recalculate
trust_pdf_balance: false
period_boundary_pattern: "BROUGHT FORWARD"
period_type: text_marker
enable_dynamic_columns: true
header_pattern: "Date\\s+Description.*Paid In.*Withdrawn.*Balance"
special_handlers: [brought_forward_quirk]
date_formats: ["%d %b", "%d %b %Y"]
```

**Success Criteria:**
- All three banks have complete configurations
- Configurations load correctly
- Strategies initialize from configurations

### Phase 4: Refactor Halifax to Use Base Parser (Week 3)

**Goals:**
- First bank migration
- Validate approach
- Maintain 100% validation

**Tasks:**
1. Create `HalifaxParser(BaseStatementParser)`
2. Implement bank-specific methods:
   - `_classify_amount()` - delegates to TypeCodeStrategy
   - `_parse_period_marker()` - parses "Page X of Y"
3. Remove duplicate code from original implementation
4. Run full test suite on Halifax
5. Verify 100% validation maintained (12/12 periods)

**Success Criteria:**
- Halifax parser < 200 lines (down from ~400)
- All 12 periods validate at 100%
- All existing tests pass
- Code coverage maintained

### Phase 5: Refactor HSBC to Use Base Parser (Week 3-4)

**Goals:**
- Second bank migration
- Validate dynamic column detection in base
- Maintain 100% validation

**Tasks:**
1. Create `HSBCParser(BaseStatementParser)`
2. Implement bank-specific methods:
   - `_classify_amount()` - delegates to ColumnPositionStrategy
   - `_parse_period_marker()` - single period handling
3. Remove duplicate code
4. Run full test suite
5. Verify 100% validation maintained (4/4 periods)

**Success Criteria:**
- HSBC parser < 150 lines (down from ~350)
- All 4 periods validate at 100%
- Dynamic columns work from base parser

### Phase 6: Refactor NatWest to Use Base Parser (Week 4)

**Goals:**
- Third bank migration
- Validate special handlers
- Maintain 100% validation

**Tasks:**
1. Create `NatWestParser(BaseStatementParser)`
2. Implement bank-specific methods:
   - `_classify_amount()` - delegates to KeywordStrategy
   - `_parse_period_marker()` - BROUGHT FORWARD handling
3. Register `brought_forward_quirk` handler
4. Remove duplicate code
5. Run full test suite
6. Verify 100% validation maintained (43/43 periods)

**Success Criteria:**
- NatWest parser < 200 lines (down from ~450)
- All 43 periods validate at 100%
- Special handler system works
- Cascading recalculation works

### Phase 7: Integration and Testing (Week 5)

**Goals:**
- Full integration testing
- Performance validation
- Documentation

**Tasks:**
1. Run all three banks through full test suite
2. Performance benchmarking (should be similar or faster)
3. Update documentation:
   - Developer guide for adding new banks
   - Architecture documentation
   - Strategy selection guide
4. Code review and cleanup

**Success Criteria:**
- All 59 periods validate at 100% across all three banks
- Performance within 10% of original
- Documentation complete
- No regressions

---

## Migration Benefits

### Code Reduction
- **Before**: ~1200 lines across three parsers
- **After**: ~400 lines base + (150+150+200) bank-specific = ~900 lines
- **Reduction**: 25% smaller codebase, 60% less duplication

### Maintainability
- Common logic in one place
- Bug fixes benefit all banks
- Clear separation of concerns

### Extensibility
- New banks can be added in < 100 lines
- Strategy pattern allows easy customization
- Configuration-driven reduces code changes

### Testing
- Base parser tested once, used by all
- Bank-specific tests focus on unique behavior
- Higher confidence in shared code

---

## Adding a New Bank (Post-Refactoring)

**Steps to add a new bank:**

1. **Create YAML configuration** (`data/bank_templates/newbank.yaml`)
   - Choose classification strategy
   - Define date patterns
   - Set validation mode
   - List any special handlers needed

2. **Create parser class** (if needed - only if custom logic required)
   ```python
   class NewBankParser(BaseStatementParser):
       def _classify_amount(self, ...):
           # Only if existing strategies don't fit
           pass
   ```

3. **Add to bank detector** (`src/parsers/bank_detector.py`)
   ```python
   'newbank': ['NewBank PLC', 'newbank.co.uk']
   ```

4. **Test with sample statements**
   - Place PDFs in `tests/fixtures/newbank/`
   - Run extraction
   - Verify validation rate

5. **Iterate on configuration**
   - Adjust thresholds
   - Add type codes
   - Fine-tune patterns

**Estimated effort**: 2-4 hours for a bank with standard format, 1-2 days for complex formats.

---

## Risk Mitigation

### Risk 1: Breaking Existing Functionality
**Mitigation:**
- Comprehensive test suite before refactoring
- Migrate one bank at a time
- Compare outputs before/after migration
- Keep original implementations until validated

### Risk 2: Performance Degradation
**Mitigation:**
- Benchmark before/after
- Profile strategy pattern overhead
- Optimize hot paths if needed
- Target: < 10% performance change

### Risk 3: Lost Edge Case Handling
**Mitigation:**
- Document all edge cases from existing code
- Explicit tests for each edge case
- Code review with original implementer
- Run on full statement corpus

### Risk 4: Over-Engineering
**Mitigation:**
- Only extract proven patterns (all 3 banks use)
- Don't create abstractions for single use cases
- YAGNI principle - build what's needed now
- Regular reviews to remove unused complexity

---

## Success Metrics

### Must Have (MVP)
- ✅ 100% validation maintained for all three banks
- ✅ 25% code reduction
- ✅ No performance regression > 10%
- ✅ All existing tests pass

### Should Have (Full Success)
- ✅ 60% reduction in duplicated code
- ✅ New bank can be added in < 100 lines
- ✅ Documentation complete for new bank additions
- ✅ Strategy pattern enables easy customization

### Nice to Have (Excellence)
- ⭐ Performance improvement from optimized shared code
- ⭐ Fourth bank added to validate extensibility
- ⭐ Automated configuration validation
- ⭐ Visual diff tool for before/after validation

---

## Appendix: Key Code Examples

### Example: Adding a New Bank

```python
# 1. Create configuration (data/bank_templates/lloyds.yaml)
bank_name: Lloyds
classification_strategy: type_code
classification_config:
  money_in_codes: [PAY, TFR, CR]
  money_out_codes: [DD, SO, BGC, CHQ]
validation_mode: swap_only
period_boundary_pattern: "Page (\\d+)"
date_formats: ["%d %b %Y"]

# 2. Create parser (src/parsers/lloyds_parser.py) - Optional if standard
class LloydsParser(BaseStatementParser):
    """Lloyds Bank parser - uses base implementation with config"""
    pass  # No custom code needed if config is sufficient!

# 3. Add to detector (src/parsers/bank_detector.py)
BANK_IDENTIFIERS = {
    'lloyds': ['Lloyds Bank', 'lloydsbank.com'],
    # ...
}

# 4. Test it
python -m src.cli extract lloyds_statement.pdf --output test.xlsx
```

### Example: Custom Classification Strategy

```python
# If existing strategies don't fit, create new one
class HybridPositionKeywordStrategy(ClassificationStrategy):
    """
    Use position as primary, keywords as tiebreaker.
    For banks with inconsistent column alignment.
    """

    def classify(self, amount, position, description, type_code):
        # Primary: position
        if position < 50:
            likely = 'money_out'
        elif position < 80:
            likely = 'money_in'
        else:
            return None  # Balance column

        # Verify with keywords
        if 'payment to' in description.lower():
            return 'money_out'
        elif 'payment from' in description.lower():
            return 'money_in'

        return likely
```

---

**Document Version**: 1.0
**Created**: 2025-10-11
**Status**: Ready for Implementation
**Estimated Effort**: 5 weeks (1 developer)
**Expected Impact**: 25% code reduction, 60% less duplication, easier new bank additions
