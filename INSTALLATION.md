# Installation Guide

## Prerequisites

- Python 3.10 or higher
- pip (Python package manager)
- Tesseract OCR (optional, for scanned documents)

## Step 1: Clone or Download the Repository

```bash
cd /path/to/ai-bank-statement-extractor
```

## Step 2: Create Virtual Environment

```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
# On macOS/Linux:
source venv/bin/activate

# On Windows:
venv\Scripts\activate
```

## Step 3: Install Dependencies

```bash
# Install core dependencies
pip install -r requirements.txt

# Or install in development mode
pip install -e ".[dev]"
```

## Step 4: Install Tesseract OCR (Optional)

### macOS
```bash
brew install tesseract
```

### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install tesseract-ocr
```

### Windows
Download and install from: https://github.com/UB-Mannheim/tesseract/wiki

## Step 5: Configure Environment Variables

```bash
# Copy example environment file
cp .env.example .env

# Edit .env and add your API keys
nano .env  # or use your preferred editor
```

Add your API keys:
```
ANTHROPIC_API_KEY=sk-ant-your-key-here
OPENAI_API_KEY=sk-your-key-here
```

## Step 6: Verify Installation

```bash
# Run system test
python -m src.cli test

# List supported banks
python -m src.cli banks
```

## Step 7: Test with Sample Statement

```bash
# Extract a statement (once pipeline is implemented)
python -m src.cli extract path/to/statement.pdf
```

## Troubleshooting

### Import Errors
If you see import errors, make sure:
1. Virtual environment is activated
2. Dependencies are installed: `pip install -r requirements.txt`
3. You're in the project root directory

### Tesseract Not Found
If Tesseract is not found:
1. Verify installation: `tesseract --version`
2. Update TESSERACT_PATH in .env file
3. OCR is optional - native PDF extraction will still work

### API Key Errors
Make sure your .env file exists and contains valid API keys.

## Next Steps

1. Review [QUICK_START.md](QUICK_START.md) for usage examples
2. Check [README.md](README.md) for project overview
3. See [CLAUDE.md](CLAUDE.md) for implementation details

## Development Setup

For development work:

```bash
# Install with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with coverage
pytest --cov=src --cov-report=html

# Format code
black src/ tests/

# Lint code
flake8 src/ tests/

# Type checking
mypy src/
```
