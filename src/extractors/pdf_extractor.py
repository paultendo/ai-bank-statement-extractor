"""PDF text extraction using pdfplumber."""
import logging
from pathlib import Path
from typing import Optional

try:
    import pdfplumber
except ImportError:
    pdfplumber = None

from .base_extractor import BaseExtractor, ExtractionError

logger = logging.getLogger(__name__)


class PDFExtractor(BaseExtractor):
    """
    Extract text from native PDF files using pdfplumber.

    This is the fastest and most accurate method for PDFs
    that contain selectable text (non-scanned PDFs).
    """

    def __init__(self):
        """Initialize PDF extractor."""
        super().__init__()
        if pdfplumber is None:
            raise ImportError(
                "pdfplumber is required for PDF extraction. "
                "Install it with: pip install pdfplumber"
            )

    def can_handle(self, file_path: Path) -> bool:
        """
        Check if file is a PDF.

        Args:
            file_path: Path to the document file

        Returns:
            True if file is a PDF
        """
        return file_path.suffix.lower() == '.pdf'

    def extract(self, file_path: Path) -> tuple[str, float]:
        """
        Extract text from PDF using pdfplumber.

        Args:
            file_path: Path to PDF file

        Returns:
            Tuple of (extracted_text, confidence_score)

        Raises:
            ExtractionError: If extraction fails
        """
        self.validate_file(file_path)

        if not self.can_handle(file_path):
            raise ExtractionError(f"File is not a PDF: {file_path}")

        try:
            logger.info(f"Extracting text from PDF: {file_path}")

            all_text = []
            total_pages = 0
            pages_with_text = 0

            with pdfplumber.open(file_path) as pdf:
                total_pages = len(pdf.pages)
                logger.debug(f"PDF has {total_pages} pages")

                for page_num, page in enumerate(pdf.pages, start=1):
                    text = page.extract_text()

                    if text and text.strip():
                        all_text.append(f"--- Page {page_num} ---\n{text}")
                        pages_with_text += 1
                        logger.debug(f"Extracted {len(text)} chars from page {page_num}")
                    else:
                        logger.warning(f"No text found on page {page_num}")

            extracted_text = "\n\n".join(all_text)

            # Calculate confidence based on text extraction success
            if not extracted_text.strip():
                logger.warning("No text extracted from PDF - likely scanned")
                return "", 0.0

            # Confidence is based on percentage of pages with text
            confidence = (pages_with_text / total_pages) * 100.0

            logger.info(
                f"Successfully extracted {len(extracted_text)} characters "
                f"from {pages_with_text}/{total_pages} pages "
                f"(confidence: {confidence:.1f}%)"
            )

            return extracted_text, confidence

        except Exception as e:
            logger.error(f"Failed to extract text from PDF: {e}")
            raise ExtractionError(f"PDF extraction failed: {e}") from e

    def extract_tables(self, file_path: Path) -> list:
        """
        Extract tables from PDF.

        Args:
            file_path: Path to PDF file

        Returns:
            List of extracted tables (as pandas DataFrames)
        """
        self.validate_file(file_path)

        tables = []
        try:
            with pdfplumber.open(file_path) as pdf:
                for page_num, page in enumerate(pdf.pages, start=1):
                    page_tables = page.extract_tables()
                    if page_tables:
                        logger.debug(f"Found {len(page_tables)} tables on page {page_num}")
                        tables.extend(page_tables)

            logger.info(f"Extracted {len(tables)} tables from PDF")
            return tables

        except Exception as e:
            logger.error(f"Failed to extract tables from PDF: {e}")
            return []
