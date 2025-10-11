# Quick Reference Guide

## Project Overview

Bank statement extractor for UK law firm (Fifty Six Law) - extracts transaction data from PDF/image statements into Excel for legal evidence (contentious probate, APP claims).

## 📁 Project Structure

```
ai-bank-statement-extractor/
├── src/                              # Source code
│   ├── models/                       # Data structures
│   │   ├── transaction.py           # Transaction model with confidence
│   │   ├── statement.py             # Statement metadata
│   │   └── extraction_result.py     # Complete extraction result
│   ├── extractors/                   # Document extraction
│   │   ├── base_extractor.py        # Abstract base class
│   │   ├── pdf_extractor.py         # Native PDF text (pdfplumber) ✅
│   │   ├── ocr_extractor.py         # Tesseract OCR (TODO)
│   │   └── vision_extractor.py      # Claude/GPT Vision API (TODO)
│   ├── parsers/                      # Transaction parsing
│   │   ├── transaction_parser.py    # Regex-based parsing (TODO)
│   │   ├── llm_parser.py            # LLM fallback (TODO)
│   │   └── bank_detector.py         # Detect bank from text (TODO)
│   ├── validators/                   # Data validation
│   │   ├── balance_validator.py     # Reconciliation (TODO)
│   │   └── confidence_scorer.py     # Score extraction quality (TODO)
│   ├── exporters/                    # Output generation
│   │   ├── excel_exporter.py        # Excel with 3 sheets (TODO)
│   │   └── csv_exporter.py          # CSV output (TODO)
│   ├── config/                       # Configuration
│   │   ├── settings.py              # Global settings ✅
│   │   └── bank_config_loader.py    # Load YAML configs ✅
│   ├── utils/                        # Utilities
│   │   ├── logger.py                # Audit logging ✅
│   │   ├── currency_parser.py       # Parse £, $, € ✅ (TESTED)
│   │   ├── date_parser.py           # Smart date parsing ✅
│   │   └── image_preprocessing.py   # Deskew, denoise (TODO)
│   ├── pipeline.py                   # Main ETL orchestration (TODO)
│   └── cli.py                        # Command-line interface ✅
├── data/
│   └── bank_templates/
│       └── natwest.yaml             # NatWest config ✅
├── tests/                            # Test suite
│   ├── conftest.py                  # Pytest fixtures ✅
│   └── test_utils/
│       └── test_currency_parser.py  # Currency tests ✅
├── reference/
│   └── monopoly/                     # Reference implementation 🔍
├── ui/
│   └── streamlit_app.py             # Web UI (TODO)
└── docs/                             # Documentation
```

## 🚀 Quick Start

```bash
# 1. Setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 2. Test system
python -m src.cli test

# 3. List banks
python -m src.cli banks

# 4. Run tests
pytest tests/test_utils/test_currency_parser.py -v
```

## 📚 Key Documentation

| File | Purpose |
|------|---------|
| [README.md](README.md) | Project overview |
| [CLAUDE.md](CLAUDE.md) | Detailed implementation guide for AI coders |
| [QUICK_START.md](QUICK_START.md) | Quick reference for users |
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | What's done, what's next |
| [MONOPOLY_ANALYSIS.md](MONOPOLY_ANALYSIS.md) | Learnings from reference implementation |
| [INSTALLATION.md](INSTALLATION.md) | Setup instructions |
| [UI_SPECIFICATION.md](UI_SPECIFICATION.md) | UI requirements |

## 🔑 Key Concepts

### 1. Extraction Strategy Cascade

```
1. PDF Text (pdfplumber) - Fast, cheap, accurate for native PDFs
   ↓ If fails or confidence < 80%
2. OCR (Tesseract) - Medium speed/cost, good for scanned docs
   ↓ If fails or confidence < 80%
3. Vision API (Claude/GPT) - Slow, expensive, handles anything
```

### 2. Bank Configuration (YAML)

```yaml
# data/bank_templates/natwest.yaml
natwest:
  identifiers:
    - "NatWest"
    - "National Westminster Bank"

  header_patterns:
    account_number: "Account No\\s+(\\d+)"
    sort_code: "Sort Code\\s+(\\d{2}-\\d{2}-\\d{2})"

  date_formats:
    - "%d %b %Y"      # 18 DEC 2024

  transaction_patterns:
    standard: |
      ^(?P<date>\d{1,2}\s+[A-Z]{3}(?:\s+\d{4})?)\s+
      (?P<description>.+?)\s+
      (?P<paid_in>[\d,]+\.\d{2})?\s*
      (?P<withdrawn>[\d,]+\.\d{2})?\s*
      (?P<balance>[\d,]+\.\d{2})$

  field_mapping:
    paid_in: "money_in"
    withdrawn: "money_out"
```

### 3. Data Models

```python
# Transaction
Transaction(
    date=datetime(2024, 12, 1),
    description="TESCO STORES 2341",
    money_in=0.0,
    money_out=45.67,
    balance=1254.33,
    transaction_type=TransactionType.CARD_PAYMENT,
    confidence=95.0  # 0-100 score
)

# Statement
Statement(
    bank_name="NatWest",
    account_number="1234",
    statement_start_date=datetime(2024, 12, 1),
    statement_end_date=datetime(2024, 12, 31),
    opening_balance=1300.00,
    closing_balance=3754.33,
    currency="GBP"
)

# ExtractionResult
ExtractionResult(
    statement=statement,
    transactions=[...],
    success=True,
    balance_reconciled=True,
    confidence_score=96.7,
    extraction_method="pdf_text",
    processing_time=1.5
)
```

### 4. Balance Validation (Critical!)

```python
# Opening balance + money_in - money_out = Closing balance
calculated = opening_balance
for txn in transactions:
    calculated += txn.money_in - txn.money_out
    assert abs(calculated - txn.balance) <= 0.01  # 1p tolerance
```

## 🎯 MVP Roadmap

### ✅ Phase 0: Foundation (DONE)
- [x] Project structure
- [x] Data models
- [x] PDF extractor
- [x] Config system
- [x] Utilities (currency, date, logging)
- [x] CLI framework
- [x] Test infrastructure

### ⏳ Phase 1: Core Parser (IN PROGRESS)
- [ ] Transaction parser with regex
- [ ] Multi-line description handling
- [ ] Balance validator
- [ ] Excel exporter
- [ ] Pipeline integration

### 📋 Phase 2: Enhanced Extraction
- [ ] OCR extractor
- [ ] Image preprocessing
- [ ] Vision API extractor

### 📋 Phase 3: Multi-Bank
- [ ] HSBC config
- [ ] Lloyds config
- [ ] Barclays config
- [ ] Generic fallback parser

### 📋 Phase 4: UI
- [ ] Streamlit web interface
- [ ] File upload
- [ ] Manual correction
- [ ] Batch processing

## 🔍 Reference Implementation

We have Monopoly library cloned in `reference/monopoly/` for reference:
- 17+ banks supported
- Production-ready patterns
- Multi-line description handling
- Cross-year date logic
- Balance validation ("safety check")

**Key files to study:**
- `reference/monopoly/src/monopoly/pipeline.py` - ETL pattern
- `reference/monopoly/src/monopoly/statements/base.py` - Multi-line descriptions
- `reference/monopoly/src/monopoly/banks/hsbc/hsbc.py` - Bank config example

See [MONOPOLY_ANALYSIS.md](MONOPOLY_ANALYSIS.md) for detailed analysis.

## 🧪 Testing

```bash
# Run all tests
pytest

# Run with coverage
pytest --cov=src --cov-report=html

# Run specific test
pytest tests/test_utils/test_currency_parser.py -v

# Run integration tests
pytest tests/integration/ -v

# Run tests for specific bank
pytest -k "natwest" -v
```

## 🐛 Common Issues

### Import errors
```bash
# Make sure you're in project root and venv is activated
cd /Users/pw/Code/ai-bank-statement-extractor
source venv/bin/activate
```

### Tesseract not found
```bash
# macOS
brew install tesseract

# Update .env
TESSERACT_PATH=/opt/homebrew/bin/tesseract
```

### API keys not working
```bash
# Make sure .env exists
cp .env.example .env
# Edit .env and add your keys
```

## 📖 Usage Examples (When Implemented)

```bash
# Extract single statement
python -m src.cli extract statements/natwest_dec2024.pdf

# Specify output format
python -m src.cli extract statement.pdf -o output.xlsx --format xlsx

# Force vision API use
python -m src.cli extract low_quality.jpg --use-vision

# Batch process directory
python -m src.cli batch statements/ -o output_dir/

# List supported banks
python -m src.cli banks

# Run system test
python -m src.cli test
```

## 🎨 Code Style

```python
# Use type hints
def extract_transactions(file_path: str, bank: str) -> list[Transaction]:
    pass

# Use dataclasses
@dataclass
class Transaction:
    date: datetime
    description: str
    confidence: float = 100.0

# Document complex functions
def parse_multiline_description(text: str) -> str:
    """
    Parse transaction description spanning multiple lines.

    Args:
        text: Raw text from statement

    Returns:
        Combined description string

    Example:
        >>> parse_multiline_description("Line 1\n  Line 2")
        "Line 1 Line 2"
    """
    pass
```

## 💡 Pro Tips

1. **Always validate balance** - Legal evidence must be 100% accurate
2. **Log everything** - Audit trail is critical for compliance
3. **Handle edge cases** - Overdrafts, multi-page statements, year boundaries
4. **Test with real data** - Use anonymized real statements, not synthetic
5. **Reference Monopoly** - When stuck, check `reference/monopoly/` for patterns
6. **Multiline descriptions** - NatWest and most UK banks have these!
7. **Confidence scoring** - Flag low-confidence extractions for manual review

## 🔗 External Links

- **Monopoly Library**: https://github.com/benjamin-awd/monopoly
- **StatementSensei**: https://github.com/benjamin-awd/StatementSensei
- **pdfplumber docs**: https://github.com/jsvine/pdfplumber
- **Tesseract**: https://github.com/tesseract-ocr/tesseract
- **Claude API**: https://docs.anthropic.com/

## 🆘 Need Help?

1. Check [PROJECT_STATUS.md](PROJECT_STATUS.md) for current progress
2. Read [MONOPOLY_ANALYSIS.md](MONOPOLY_ANALYSIS.md) for patterns
3. Review code in `reference/monopoly/` for examples
4. Check test files for usage examples
5. Enable debug logging: `LOG_LEVEL=DEBUG` in .env

---

**Last Updated**: 2025-10-11
**Current Status**: Foundation complete, ready for core parser implementation
**Next Step**: Implement transaction parser with multi-line description support
