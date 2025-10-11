"""Global settings and configuration."""
import os
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Project root directory
PROJECT_ROOT = Path(__file__).parent.parent.parent

# Directories
DATA_DIR = PROJECT_ROOT / "data"
BANK_TEMPLATES_DIR = DATA_DIR / "bank_templates"
SAMPLE_STATEMENTS_DIR = DATA_DIR / "sample_statements"
OUTPUT_DIR = PROJECT_ROOT / "output"
LOGS_DIR = PROJECT_ROOT / "logs"

# Ensure directories exist
OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)

# API Keys
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Processing settings
MAX_FILE_SIZE_MB = int(os.getenv("MAX_FILE_SIZE_MB", "50"))
OCR_LANGUAGE = os.getenv("OCR_LANGUAGE", "eng")
TESSERACT_PATH = os.getenv("TESSERACT_PATH", "/usr/bin/tesseract")

# Output settings
EXCEL_FORMAT = os.getenv("EXCEL_FORMAT", "xlsx")
CONFIDENCE_THRESHOLD = float(os.getenv("CONFIDENCE_THRESHOLD", "70"))

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE = LOGS_DIR / "extractor.log"

# Extraction strategies priority
EXTRACTION_STRATEGIES = [
    "pdf_text",      # Try native PDF text extraction first (fastest, cheapest)
    "ocr",           # Then try OCR for scanned documents
    "vision_api"     # Finally use Vision API as fallback (slowest, most expensive)
]

# Vision API settings
VISION_API_PROVIDER = os.getenv("VISION_API_PROVIDER", "anthropic")  # or "openai"
VISION_API_MODEL = os.getenv("VISION_API_MODEL", "claude-3-5-sonnet-20241022")

# Currency settings
DEFAULT_CURRENCY = "GBP"
CURRENCY_SYMBOLS = {
    "GBP": "£",
    "USD": "$",
    "EUR": "€"
}
