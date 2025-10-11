# CLAUDE.md - Bank Statement Extractor

## Quick Context for AI Coders

This project builds a bank statement extraction system for a UK law firm (Fifty Six Law). It processes PDF and image bank statements, extracting financial transaction data into structured Excel spreadsheets for legal evidence.

**Critical Context**: 
- Used for contentious probate claims and bank APP reimbursement claims
- Accuracy is paramount (legal evidence for court)
- Must handle multiple UK bank formats
- Data privacy is essential (local processing)

---

## Technical Stack

```
Python 3.10+
├── PDF Processing
│   ├── pdfplumber (primary text extraction)
│   ├── PyMuPDF (fallback/metadata)
│   └── camelot-py (table extraction)
├── OCR & Vision
│   ├── pytesseract + Tesseract 5.0
│   ├── opencv-python (image preprocessing)
│   ├── Pillow (image manipulation)
│   └── anthropic / openai (Vision APIs)
├── Data Processing
│   ├── pandas (data manipulation)
│   ├── openpyxl (Excel generation)
│   └── dateutil / arrow (date parsing)
└── UI (choose one)
    ├── streamlit (quick web UI)
    ├── Flask/FastAPI + React (production)
    └── CLI with rich (terminal interface)
```

---

## Project Structure

```
bank-statement-extractor/
├── src/
│   ├── __init__.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   ├── pdf_extractor.py        # PDF text extraction
│   │   ├── ocr_extractor.py        # OCR processing
│   │   ├── vision_extractor.py     # Claude/GPT vision API
│   │   └── base_extractor.py       # Abstract base class
│   ├── parsers/
│   │   ├── __init__.py
│   │   ├── bank_detector.py        # Identify bank from statement
│   │   ├── transaction_parser.py   # Parse transactions
│   │   └── llm_parser.py           # LLM-based fallback parser
│   ├── validators/
│   │   ├── __init__.py
│   │   ├── balance_validator.py    # Reconciliation checks
│   │   ├── data_validator.py       # Field validation
│   │   └── confidence_scorer.py    # Calculate extraction confidence
│   ├── exporters/
│   │   ├── __init__.py
│   │   ├── excel_exporter.py       # Generate Excel output
│   │   └── csv_exporter.py         # Generate CSV output
│   ├── models/
│   │   ├── __init__.py
│   │   ├── transaction.py          # Transaction data model
│   │   ├── statement.py            # Statement metadata model
│   │   └── extraction_result.py    # Complete extraction result
│   ├── config/
│   │   ├── __init__.py
│   │   ├── bank_configs.yaml       # Bank-specific configurations
│   │   └── settings.py             # Global settings
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── image_preprocessing.py  # Deskew, denoise, enhance
│   │   ├── date_parser.py          # Smart date parsing
│   │   ├── currency_parser.py      # Parse £, $, €, etc.
│   │   └── logger.py               # Audit logging
│   └── pipeline.py                 # Main orchestration
├── tests/
│   ├── __init__.py
│   ├── test_extractors/
│   ├── test_parsers/
│   ├── test_validators/
│   ├── test_exporters/
│   ├── fixtures/                   # Sample statements
│   └── conftest.py                 # Pytest configuration
├── ui/
│   ├── cli.py                      # CLI interface
│   ├── streamlit_app.py            # Streamlit web UI
│   └── templates/                  # UI templates
├── data/
│   ├── bank_templates/             # Bank parsing templates
│   └── sample_statements/          # Anonymized test data
├── docs/
│   ├── USER_GUIDE.md
│   ├── DEVELOPER_GUIDE.md
│   └── API_DOCUMENTATION.md
├── .env.example                    # Environment variables template
├── .gitignore
├── requirements.txt
├── setup.py
├── BRIEF.md                        # Full project brief
├── CLAUDE.md                       # This file
└── README.md
```

---

## Implementation Approach

### Phase 1: Core Extraction Pipeline (Start Here)

1. **Document Analysis**
   ```python
   def analyze_document(file_path):
       """
       Determine document type and extraction strategy
       Returns: {"type": "pdf_native"|"pdf_scanned"|"image", 
                "pages": int, 
                "quality": float}
       """
   ```

2. **Multi-Strategy Extraction**
   ```python
   class ExtractionPipeline:
       def __init__(self):
           self.strategies = [
               PDFTextExtractor(),
               OCRExtractor(),
               VisionAPIExtractor()
           ]
       
       def extract(self, document):
           for strategy in self.strategies:
               result = strategy.extract(document)
               if result.confidence > 0.8:
                   return result
           return result  # Return best attempt
   ```

3. **Bank Format Detection**
   ```python
   # bank_configs.yaml structure:
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
     column_mapping:
       paid_in: money_in
       paid_out: money_out
   ```

4. **Transaction Parsing**
   - Try regex patterns from bank config
   - If confidence < 80%, use LLM parser
   - Always validate with balance reconciliation

5. **Excel Output**
   ```python
   # Three sheets:
   # 1. Transactions (main data)
   # 2. Metadata (statement info)
   # 3. Extraction Log (audit trail)
   ```

---

## Key Implementation Notes

### 1. Extraction Strategy Selection

**Decision Tree:**
```
Is it a PDF?
├─ Yes: Can you extract text directly?
│   ├─ Yes: Use pdfplumber (fastest, cheapest)
│   └─ No: Is it a scanned PDF?
│       ├─ Yes: Good quality?
│       │   ├─ Yes: Use Tesseract OCR
│       │   └─ No: Use Vision API
│       └─ No: Use Vision API
└─ No: Is it an image?
    └─ Yes: Good quality?
        ├─ Yes: Use Tesseract OCR
        └─ No: Use Vision API
```

### 2. LLM Integration Pattern

**Use LLM for:**
- Bank format detection when patterns fail
- Parsing unstructured/complex layouts
- Extracting data from poor quality scans

**Cost optimization:**
```python
# Use vision API only when necessary
if confidence_score < 0.8 or extraction_failed:
    result = vision_api_extract(document)
else:
    result = template_based_extract(document)
```

**Prompt template for Claude Vision:**
```python
EXTRACTION_PROMPT = """
Analyze this bank statement image and extract all transactions.

Return a JSON array with this structure:
[
  {
    "date": "YYYY-MM-DD",
    "type": "Direct Debit|Card Payment|Transfer|etc",
    "description": "Transaction description",
    "money_in": 0.00,
    "money_out": 0.00,
    "balance": 0.00
  }
]

Also extract:
- Bank name
- Account number (last 4 digits only)
- Statement period (start and end dates)
- Opening and closing balance

Be precise with amounts. Include all transactions visible.
"""
```

### 3. Image Preprocessing Pipeline

```python
def preprocess_image(image_path):
    """
    Improves OCR accuracy
    """
    img = cv2.imread(image_path)
    
    # 1. Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # 2. Deskew (fix rotation)
    gray = deskew(gray)
    
    # 3. Denoise
    denoised = cv2.fastNlMeansDenoising(gray)
    
    # 4. Increase contrast
    enhanced = cv2.equalizeHist(denoised)
    
    # 5. Binarization (black and white)
    _, binary = cv2.threshold(enhanced, 0, 255, 
                              cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    return binary
```

### 4. Validation Logic

**Balance Reconciliation:**
```python
def validate_balance(transactions, opening_balance):
    """
    Critical: Ensures extracted data is mathematically correct
    """
    calculated = opening_balance
    
    for i, txn in enumerate(transactions):
        calculated += txn.money_in - txn.money_out
        
        # Allow 1p tolerance for rounding
        if abs(calculated - txn.balance) > 0.01:
            return False, f"Mismatch at transaction {i+1}"
    
    return True, "Balance reconciled"
```

**Confidence Scoring:**
```python
def calculate_confidence(transaction):
    """
    Score 0-100 based on multiple factors
    """
    score = 100
    
    # Deduct points for issues
    if not transaction.date:
        score -= 30
    if not transaction.description:
        score -= 20
    if not transaction.balance:
        score -= 25
    if transaction.money_in == 0 and transaction.money_out == 0:
        score -= 25
    
    # OCR quality indicators
    if extracted_via_ocr:
        if has_garbled_text(transaction.description):
            score -= 15
    
    return max(0, min(100, score))
```

### 5. Date Parsing Robustness

```python
def parse_date(date_string, bank_format=None):
    """
    Handle multiple date formats
    """
    formats = [
        "%d/%m/%Y",      # UK: 01/12/2024
        "%d-%m-%Y",      # UK: 01-12-2024
        "%d %b %Y",      # UK: 01 Dec 2024
        "%d %B %Y",      # UK: 01 December 2024
        "%Y-%m-%d",      # ISO: 2024-12-01
    ]
    
    for fmt in formats:
        try:
            return datetime.strptime(date_string, fmt)
        except ValueError:
            continue
    
    # Fallback: Use dateutil parser (very flexible)
    return dateutil.parser.parse(date_string, dayfirst=True)
```

### 6. Currency Parsing

```python
def parse_currency(amount_string):
    """
    Handle various currency formats
    """
    # Remove currency symbols and whitespace
    cleaned = re.sub(r'[£$€\s]', '', amount_string)
    
    # Remove thousand separators
    cleaned = cleaned.replace(',', '')
    
    # Handle negative amounts
    if cleaned.startswith('(') or cleaned.endswith('CR'):
        is_negative = True
        cleaned = cleaned.replace('(', '').replace(')', '').replace('CR', '')
    else:
        is_negative = False
    
    # Parse to float
    amount = float(cleaned)
    
    return -amount if is_negative else amount
```

---

## Common Pitfalls & Solutions

### Pitfall 1: Assuming Consistent Bank Formats
**Problem**: Each bank uses different layouts, column orders, date formats  
**Solution**: Maintain bank config YAML files with regex patterns and mappings

### Pitfall 2: Hardcoding Text Positions
**Problem**: PDF text positions vary between statement versions  
**Solution**: Use semantic markers (keywords like "Date", "Description", "Balance")

### Pitfall 3: Ignoring Multi-Page Statements
**Problem**: Transactions span multiple pages, missing data  
**Solution**: Concatenate all page text, then parse; track page numbers

### Pitfall 4: Poor OCR Without Preprocessing
**Problem**: Low accuracy on scanned statements  
**Solution**: Always preprocess images (deskew, denoise, enhance contrast)

### Pitfall 5: Not Handling Edge Cases
**Problem**: Crashes on statements with no transactions, overdrafts, etc.  
**Solution**: Defensive programming with null checks and edge case tests

### Pitfall 6: Expensive API Overuse
**Problem**: Using Vision API for every statement drives up costs  
**Solution**: Cascade approach - try cheap methods first, API as fallback

### Pitfall 7: No Manual Review Mechanism
**Problem**: 100% automation impossible; errors go to production  
**Solution**: Implement confidence scoring and flag low-confidence extractions

---

## Testing Strategy

### Unit Tests (pytest)
```python
# tests/test_parsers/test_transaction_parser.py
def test_parse_barclays_transaction():
    raw = "01/10/2024  TESCO STORES 2341      45.67    1254.33"
    result = parse_transaction(raw, bank_config='barclays')
    
    assert result.date == date(2024, 10, 1)
    assert result.description == "TESCO STORES 2341"
    assert result.money_out == 45.67
    assert result.balance == 1254.33
```

### Integration Tests
```python
# tests/test_integration/test_end_to_end.py
def test_process_barclays_statement():
    result = process_statement('fixtures/barclays_sample.pdf')
    
    assert result.transaction_count == 47
    assert result.balance_reconciled == True
    assert result.opening_balance == 2500.00
    assert result.closing_balance == 4800.00
```

### Bank-Specific Test Suite
```
tests/fixtures/
├── barclays/
│   ├── native_pdf.pdf
│   ├── scanned_pdf.pdf
│   └── photo.jpg
├── hsbc/
│   └── ...
└── lloyds/
    └── ...
```

---

## Environment Variables

Create `.env` file:
```bash
# API Keys
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...

# Processing Settings
MAX_FILE_SIZE_MB=50
OCR_LANGUAGE=eng
TESSERACT_PATH=/usr/bin/tesseract

# Output Settings
OUTPUT_DIRECTORY=./output
EXCEL_FORMAT=xlsx
CONFIDENCE_THRESHOLD=70

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/extractor.log
```

---

## Development Workflow

### 1. Start with MVP (Week 1)
```bash
# Goal: Process one native PDF Barclays statement
python -m src.cli extract fixtures/barclays_sample.pdf --output test_output.xlsx
```

**Tasks:**
- [ ] PDF text extraction with pdfplumber
- [ ] Basic transaction regex parsing
- [ ] Excel output with core fields
- [ ] Balance validation

### 2. Add OCR Support (Week 2)
```bash
# Goal: Process scanned statements
python -m src.cli extract fixtures/barclays_scanned.pdf --output test_output.xlsx
```

**Tasks:**
- [ ] Tesseract OCR integration
- [ ] Image preprocessing pipeline
- [ ] Quality assessment logic
- [ ] Confidence scoring

### 3. Add Vision API (Week 2-3)
```bash
# Goal: Handle poor quality statements
python -m src.cli extract fixtures/poor_quality.jpg --use-vision-api
```

**Tasks:**
- [ ] Claude Vision API integration
- [ ] OpenAI Vision API integration
- [ ] Cost optimization (cascading strategy)
- [ ] Prompt engineering for accuracy

### 4. Multi-Bank Support (Week 3-4)
```bash
# Goal: Process HSBC, Lloyds, NatWest
python -m src.cli extract fixtures/hsbc_sample.pdf --output test_output.xlsx
```

**Tasks:**
- [ ] Bank detection logic
- [ ] YAML config for each bank
- [ ] Template-based parsing
- [ ] LLM fallback parser

### 5. UI Development (Week 4-5)
```bash
# Goal: Web interface for non-technical users
streamlit run ui/streamlit_app.py
```

**Tasks:**
- [ ] File upload interface
- [ ] Processing status display
- [ ] Side-by-side viewer (PDF + extracted data)
- [ ] Manual correction capability
- [ ] Export functionality

---

## Performance Targets

| Metric | Target | How to Measure |
|--------|--------|----------------|
| Accuracy | 95%+ | Manual verification on test set |
| Speed | <2 min per statement | Time 50-statement batch |
| API Cost | <$0.50 per statement | Track API usage |
| Memory | <2GB for large batches | Profile with memory_profiler |
| Error Rate | <5% requiring manual intervention | Track confidence scores |

---

## Security Checklist

- [ ] API keys in environment variables (not in code)
- [ ] No client data logged (only anonymized metadata)
- [ ] Temp files cleaned after processing
- [ ] File permissions restricted (700 for case folders)
- [ ] No cloud upload (all processing local)
- [ ] Dependencies scanned for vulnerabilities (pip-audit)

---

## Debugging Tips

### Issue: OCR Not Working
```bash
# Check Tesseract installation
tesseract --version

# Test OCR on sample image
tesseract fixtures/test.png output -l eng

# Check image quality
python -c "from PIL import Image; img=Image.open('test.png'); print(img.size, img.mode)"
```

### Issue: PDF Extraction Empty
```python
import pdfplumber
pdf = pdfplumber.open('statement.pdf')
print(pdf.pages[0].extract_text())  # Should show text
```

### Issue: Balance Not Reconciling
```python
# Add verbose logging
logger.debug(f"Transaction {i}: Calculated={calc}, Stated={txn.balance}, Diff={diff}")
```

### Issue: API Rate Limits
```python
# Add exponential backoff
import time
from anthropic import RateLimitError

try:
    response = client.messages.create(...)
except RateLimitError:
    time.sleep(60)  # Wait 1 minute
    response = client.messages.create(...)
```

---

## Dependencies Installation

```bash
# Core dependencies
pip install pdfplumber PyMuPDF camelot-py[cv]
pip install pytesseract opencv-python Pillow
pip install pandas openpyxl
pip install anthropic openai
pip install python-dateutil arrow
pip install python-dotenv pyyaml

# UI dependencies (choose one)
pip install streamlit  # Web UI
pip install flask flask-cors  # REST API
pip install rich click  # CLI

# Development dependencies
pip install pytest pytest-cov
pip install black flake8 mypy
pip install ipython ipdb

# Install Tesseract OCR (system dependency)
# Ubuntu/Debian:
sudo apt-get install tesseract-ocr

# macOS:
brew install tesseract

# Windows:
# Download installer from https://github.com/UB-Mannheim/tesseract/wiki
```

---

## Quick Start Commands

```bash
# 1. Set up environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# 2. Configure API keys
cp .env.example .env
# Edit .env with your API keys

# 3. Run tests
pytest tests/ -v

# 4. Process a statement
python -m src.cli extract path/to/statement.pdf

# 5. Launch web UI
streamlit run ui/streamlit_app.py
```

---

## Code Style Guidelines

```python
# Use type hints
def extract_transactions(file_path: str, bank: str) -> List[Transaction]:
    pass

# Use dataclasses for models
from dataclasses import dataclass

@dataclass
class Transaction:
    date: datetime
    description: str
    money_in: float
    money_out: float
    balance: float
    confidence: float

# Use enums for constants
from enum import Enum

class TransactionType(Enum):
    DIRECT_DEBIT = "Direct Debit"
    CARD_PAYMENT = "Card Payment"
    TRANSFER = "Transfer"

# Document complex functions
def parse_complex_layout(text: str) -> List[Transaction]:
    """
    Parse bank statement with complex layout.
    
    Args:
        text: Raw text extracted from PDF
        
    Returns:
        List of parsed transactions
        
    Raises:
        ParsingError: If text cannot be parsed
        
    Example:
        >>> parse_complex_layout("01/10/2024  TESCO  45.67  1000.00")
        [Transaction(date=..., description='TESCO', ...)]
    """
    pass
```

---

## Success Criteria (MVP Ready)

- [ ] Process native PDF Barclays statement with 95%+ accuracy
- [ ] Generate Excel with all required fields
- [ ] Balance reconciliation passes
- [ ] Process in <1 minute
- [ ] Comprehensive test coverage (80%+)
- [ ] CLI functional for basic operations
- [ ] Documentation complete (README, user guide)

---

## Next Steps After MVP

1. Add HSBC, Lloyds, NatWest support
2. Implement OCR for scanned statements
3. Add Vision API integration
4. Build web UI
5. Deploy to law firm workstations
6. Gather user feedback
7. Iterate and improve accuracy

---

**For Questions or Issues:**
- Check BRIEF.md for comprehensive project details
- Review bank_configs.yaml for format specifications
- Test with fixtures/ sample statements
- Enable debug logging for troubleshooting

---

**Document Version**: 1.0  
**Last Updated**: October 2024  
**Optimized For**: Claude Code, GPT-5-Codex, Devin, other agentic coders
