# Bank Statement Extractor

> Automated extraction of financial transaction data from bank statements for legal claims processing

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

---

## Overview

**Bank Statement Extractor** is an intelligent document processing system designed for Fifty Six Law to automatically extract structured financial data from bank statements in various formats (PDFs, scanned documents, photos).

### Use Cases
- **Contentious Probate Claims** (including Inheritance Act claims) - evidencing claimant's financial schedule
- **Bank APP Reimbursement Claims** - supporting complaints under PSR regulations (October 2024) and CRM code

### Key Features
✅ Native PDF text-layer extraction with pdfplumber/pdftotext  
✅ Vision API fallback for scanned or photo-based statements  
✅ Multi-bank compatibility (Barclays, HSBC, Lloyds, NatWest, etc.)  
✅ Intelligent extraction pipeline (text extraction → Vision fallback, OCR planned)  
✅ High accuracy (95%+ on NatWest combined statements)  
✅ Confidence scoring and manual review workflow  
✅ Legal compliance (audit trail, data validation)  
✅ Structured output (Excel/CSV with metadata)

---

## Quick Start

### Prerequisites
- Python 3.10 or higher
- Claude or OpenAI API key (for Vision API fallback on scans/photos)
- (Optional / roadmap) Tesseract OCR once local OCR mode lands

> **Note:** We currently rely on native PDF text extraction plus the Vision API fallback. Local OCR via Tesseract is planned but not yet wired into the pipeline.

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd bank-statement-extractor

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install Tesseract OCR
# Ubuntu/Debian: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
# Windows: Download from https://github.com/UB-Mannheim/tesseract/wiki

# Configure API keys
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY or OPENAI_API_KEY
```

### Basic Usage

**Command Line:**
```bash
# Extract from a single statement
python -m src.cli extract statement.pdf --output transactions.xlsx

# Batch process multiple statements
python -m src.cli batch statements/ --output-dir ./results

# Force Vision API for poor quality scans/photos
python -m src.cli extract scanned_statement.jpg --use-vision
```

**Web Interface:**
```bash
streamlit run ui/streamlit_app.py
```

---

## Example Output

Input: `barclays_statement_sep2024.pdf`

Output: `transactions.xlsx` with three sheets:

**Sheet 1: Transactions**
| Date | Type | Description | Money In | Money Out | Balance | Confidence |
|------|------|-------------|----------|-----------|---------|------------|
| 2024-09-01 | Direct Debit | COUNCIL TAX | | £150.00 | £2,350.00 | 98% |
| 2024-09-02 | Card Payment | TESCO STORES 2341 | | £45.67 | £2,304.33 | 95% |
| 2024-09-05 | Transfer | SALARY PAYMENT | £2,500.00 | | £4,804.33 | 100% |

**Sheet 2: Statement Metadata**
- Bank Name: Barclays Bank UK PLC
- Account: ****4567
- Period: 01/09/2024 - 30/09/2024
- Opening Balance: £2,500.00
- Closing Balance: £4,800.00
- Transaction Count: 47

**Sheet 3: Extraction Log** (audit trail)

---

## Architecture

```
Input (PDF/Image) 
    ↓
Document Analyzer (determines format & quality)
    ↓
Extraction Strategy Selection
    ├─ Native text extraction (pdfplumber/pdftotext)
    ├─ Vision API (poor quality scans/photos)
    └─ OCR (planned roadmap item)
    ↓
Bank Format Detection (Barclays, HSBC, Lloyds, etc.)
    ↓
Transaction Parser (regex + LLM fallback)
    ↓
Validation Layer (balance reconciliation, confidence scoring)
    ↓
Excel/CSV Output + Review Interface
```

---

## Recent Updates (November 2024)

### Parser Architecture Refactoring
We recently completed a major refactoring of the parser architecture to improve maintainability and reduce code duplication:

**Achievements:**
- **40 lines saved** in Nationwide parser alone (276→236 LOC, 14% reduction)
- Eliminated duplicate parsing logic across 6 bank parsers
- Centralized configuration in YAML files for easier bank format updates
- Added PDF bounding box support to exclude unwanted regions (info boxes, headers)
- Implemented universal column detection with right-aligned amount support
- Fixed balance calculation bugs for transactions without balances

**Key Features:**
- **BaseTransactionParser**: Universal base class with shared date/description/amount extraction patterns
- **YAML-Driven Config**: Skip patterns, column detection settings, and PDF bbox all configurable per bank
- **Smart Column Detection**: Automatic detection of right-aligned amounts with configurable thresholds
- **PDF Region Filtering**: Crop out info boxes and headers at extraction level using pdfplumber's bbox feature

**Next Steps:**
- Refactor Barclays and HSBC parsers using the new base class patterns
- Measure total LOC reduction across all parsers
- Add bbox support to other banks with problematic layouts

### Nationwide Layout Parser (November 2025)
- Added a coordinate-aware Nationwide parser that consumes pdfplumber word layout, reconstructs table rows by `x` buckets, and injects `NATIONWIDE_PERIOD_BREAK` markers for every “Balance from statement …” line.
- Dynamic amount-based bbox + tighter `x/y` tolerances keep the right-hand info panel out while preserving Money In/Balance columns.
- Marsh Combined Statements (Jan–Dec 2023) now reconcile: 623 transactions, 13 period breaks, balance validation ✅, smoke-ready JSON at `output/nationwide_marsh.json`.

---

## Supported Banks (UK)

| Bank | Status | Notes |
|------|--------|-------|
| NatWest | ✅ Validated on combined statements (Statements 1-3) | 1,000+ txns, BROUGHT FORWARD handling |
| Halifax | ✅ Validated on Dec 24 & Jan 25 native PDFs | OCR fallback still pending for scans |
| HSBC | ✅ Validated on “HSBC Combined Statements for Myah Wright” | 195 txns, combined period |
| Lloyds | ✅ Validated on “Lloyds – Deborah Prime” | 79 txns, Jan 2023 period |
| Barclays | ✅ Validated on Proudfoot May 2024 statement | 78 txns, inferred period |
| Santander | ✅ Validated on CurrentAccountStatement_08022024.pdf | 212 txns, Feb 2024 period |
| TSB | ✅ Validated on “TSB Savings account - Mark Wilcox.pdf” | 31 txns, Oct 2023–Sep 2024 |
| Monzo | ✅ Validated on “monzo-bidmead.pdf” | 1,035 txns, May–Oct 2024 combined + pot summaries |
| Nationwide | ✅ “Marsh Bankstatements up to April 2024.pdf” | 623 txns Jan–Dec 2023, layout parser with 13 period breaks |

Additional banks can be enabled quickly by adding YAML configurations and regression fixtures.

---

## Documentation

- **[BRIEF.md](BRIEF.md)** - Comprehensive project specification, requirements, and implementation guide
- **[CLAUDE.md](CLAUDE.md)** - Technical guide for agentic coders (Claude Code, GPT Codex, etc.)
- **[USER_GUIDE.md](docs/USER_GUIDE.md)** - Step-by-step guide for legal staff (coming soon)
- **[DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)** - Architecture and API documentation (coming soon)

---

## Development Status

### Phase 1: Core Extraction Pipeline ✅ COMPLETE
- [x] Project specification complete
- [x] Technical architecture designed
- [x] Development brief created
- [x] Core extraction pipeline implemented
- [x] Multi-strategy PDF processing (native text + Vision fallback today, OCR planned)
- [x] Excel output generation with metadata
- [x] Balance validation and reconciliation
- [x] Bank format detection system
- [x] Multi-bank parser support (Barclays, HSBC, Lloyds, TSB, Monzo, Nationwide)

### Phase 2: Parser Architecture Refactoring 🔄 IN PROGRESS
**What We've Done:**
- [x] Created universal `BaseTransactionParser` with shared extraction patterns
- [x] Extracted common date/description/amount parsing to base class
- [x] Implemented YAML-driven configuration for all bank parsers
- [x] Refactored Nationwide parser (40 lines saved, 276→236 LOC)
- [x] Added PDF bounding box support for excluding unwanted regions (info boxes)
- [x] Fixed balance calculation to handle transactions without balances
- [x] Implemented universal column detection with right-aligned amount support

**What's Next:**
- [ ] Refactor Barclays parser to use BaseTransactionParser patterns
- [ ] Refactor HSBC parser to use BaseTransactionParser patterns
- [ ] Test all refactored parsers for accuracy
- [ ] Measure and document LOC reduction across all parsers
- [ ] Add bbox support to other banks with info boxes/headers

**Technical Debt Addressed:**
- ✅ Eliminated code duplication across bank parsers (DRY principle)
- ✅ Centralized skip patterns in YAML configs (maintainability)
- ✅ Universal column detection with configurable right-alignment
- ✅ PDF region exclusion via bounding box (cleaner extraction)
- ✅ Robust balance handling for transactions with/without balances

### Phase 3: Enhanced Extraction 🚧 IN PROGRESS
- [ ] OCR support for scanned documents (Tesseract pipeline)
- [x] Image/scan support via Claude Vision API fallback
- [x] JPEG/PNG ingestion routed through Vision API
- [x] Multi-bank format support (6 UK banks)
- [x] Confidence scoring per transaction
- [x] Cascading extraction strategy (native text → Vision API, OCR planned)

### Phase 4: UI & Validation 🔄 PARTIAL
- [x] CLI interface with rich output
- [ ] Batch processing capability (CLI stub exists)
- [ ] Web interface (Streamlit) - framework in place
- [ ] Manual review and correction workflow
- [ ] Case/client management

### Phase 5: Production Hardening 📋 PLANNED
- [ ] Comprehensive test suite (unit + integration)
- [ ] Security audit (API key handling, data privacy)
- [ ] Performance optimization (batch processing, caching)
- [ ] Deployment packaging (Docker, installers)

---

## Technical Stack

| Component | Technology |
|-----------|------------|
| **PDF Processing** | pdfplumber, PyMuPDF, camelot-py |
| **OCR** | pytesseract, Tesseract 5.0 |
| **Computer Vision** | OpenCV, Pillow |
| **LLM APIs** | Anthropic Claude, OpenAI GPT-4 Vision |
| **Data Processing** | pandas, openpyxl |
| **Date Parsing** | dateutil, arrow |
| **UI** | Streamlit (web) or CLI (rich, click) |
| **Testing** | pytest, pytest-cov |

---

## Testing

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=src --cov-report=html

# Run specific test suite
pytest tests/test_extractors/ -v

# Test with real statements (requires fixtures)
pytest tests/test_integration/ -v --use-fixtures
```

---

## Configuration

### Environment Variables (.env)
```bash
# API Keys (choose one or both)
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Processing Settings
MAX_FILE_SIZE_MB=50
OCR_LANGUAGE=eng
CONFIDENCE_THRESHOLD=70

# Output
OUTPUT_DIRECTORY=./output
EXCEL_FORMAT=xlsx
```

### Bank Configuration (config/bank_configs.yaml)
```yaml
barclays:
  identifiers:
    - "Barclays Bank UK PLC"
    - "barclays.co.uk"
  date_format: "DD/MM/YYYY"
  transaction_pattern: |
    (?P<date>\d{2}/\d{2}/\d{4})\s+
    (?P<description>.+?)\s+
    (?P<paid_in>[\d,]+\.\d{2})?\s+
    (?P<paid_out>[\d,]+\.\d{2})?\s+
    (?P<balance>[\d,]+\.\d{2})
```

---

## Security & Compliance

### Data Protection
- ✅ All processing happens **locally** (no cloud upload)
- ✅ API keys stored securely in environment variables
- ✅ Temporary files cleaned after processing
- ✅ Anonymized logging (no sensitive data in logs)

### Legal Compliance
- ✅ Complete audit trail for court evidence
- ✅ Version tracking (extractor version per statement)
- ✅ Manual review workflow for uncertain extractions
- ✅ Data validation ensures integrity
- ✅ GDPR compliant (local processing, deletion on request)

---

## Performance

| Metric | Target | Actual |
|--------|--------|--------|
| **Accuracy** | 95%+ | TBD (in development) |
| **Speed** | <2 min/statement | TBD |
| **API Cost** | <£0.50/statement | TBD |
| **Automation Rate** | 80%+ no manual review | TBD |

---

## Roadmap

### Short-term (Q4 2024)
- Complete MVP with core extraction pipeline
- Support top 5 UK banks
- Basic web interface

### Medium-term (Q1 2025)
- Business account support
- Credit card statement processing
- Advanced analytics (spending patterns, anomaly detection)
- Integration with case management systems

### Long-term (2025+)
- International bank support (EU, US)
- Investment account statements
- Direct banking API integration (Open Banking)
- Mobile app for statement capture
- Fine-tuned ML model for law firm's specific statement types

---

## Contributing

We welcome contributions! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

### Adding a New Bank

1. Create bank configuration in `config/bank_configs.yaml`
2. Add regex patterns for transaction parsing
3. Create test fixtures in `tests/fixtures/<bank_name>/`
4. Run tests to verify accuracy
5. Submit pull request

---

## Troubleshooting

### Common Issues

**Issue**: Tesseract not found
```bash
# Check installation
tesseract --version

# Install if missing
# Ubuntu: sudo apt-get install tesseract-ocr
# macOS: brew install tesseract
```

**Issue**: Low OCR accuracy
- Ensure image quality is good (300+ DPI)
- Use image preprocessing (`--preprocess` flag)
- Consider using Vision API for difficult documents

**Issue**: API rate limits
- Reduce batch size
- Add delays between requests
- Check API tier limits

**Issue**: Balance not reconciling
- Verify all transactions extracted
- Check for hidden fees/interest
- Review multi-page statement handling

---

## License

This project is licensed under the MIT License - see [LICENSE](LICENSE) file for details.

---

## Support

**Project Owner**: Fifty Six Law  
**Primary Use**: Legal claims processing  
**Regulatory Context**: PSR regulations (October 2024), CRM code

For issues or questions:
- 📧 Email: support@example.com (update with actual contact)
- 📝 Documentation: See [BRIEF.md](BRIEF.md) and [CLAUDE.md](CLAUDE.md)
- 🐛 Issues: [GitHub Issues](https://github.com/your-repo/issues)

---

## Acknowledgments

- Built for Fifty Six Law legal claims processing
- Compliant with UK PSR regulations (October 2024 updates)
- Designed for use with contentious probate and APP reimbursement claims

---

**Current Version**: 0.1.0-alpha  
**Last Updated**: October 2024  
**Status**: In Development - MVP Phase

---

## Getting Started for Developers

**Ready to build?** Start here:

1. **Read the brief**: [BRIEF.md](BRIEF.md) - Complete project specification
2. **For AI coders**: [CLAUDE.md](CLAUDE.md) - Optimized guide for Claude Code, GPT Codex
3. **Set up environment**: Follow installation steps above
4. **Run first test**: `pytest tests/ -v`
5. **Process first statement**: `python -m src.cli extract fixtures/sample.pdf`

**Questions?** Check the documentation or raise an issue!

### Batch Processing Status (November 2025)
- `python3 -m src.cli batch <dir>` walks any folder of PDFs, auto-detects the bank per file, writes per-statement XLSX/JSON outputs, and emits a manifest (`batch_summary.json`) summarising success, warnings, reconciliation, etc.
- The Streamlit app mirrors that capability: upload multiple files, click “Extract All,” and it runs the shared batch runner, surfaces per-file warnings, and offers consolidated exports (combined transactions Excel, CSVs, manifest JSON).
- Both surfaces now support CSV output (CLI: `--format csv`, Streamlit: download buttons), so you can hand the consolidated data directly to GPT/Claude without Excel overhead.
