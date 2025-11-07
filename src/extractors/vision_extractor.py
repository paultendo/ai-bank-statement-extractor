"""Vision API extraction using Anthropic Claude."""
import logging
import os
import base64
import json
from pathlib import Path
from typing import Optional, List, Dict, Any
import tempfile

try:
    import anthropic
except ImportError:
    anthropic = None

try:
    from pdf2image import convert_from_path
except ImportError:
    convert_from_path = None

try:
    from PIL import Image
except ImportError:
    Image = None

from .base_extractor import BaseExtractor, ExtractionError

logger = logging.getLogger(__name__)


class VisionExtractor(BaseExtractor):
    """
    Extract text from scanned/image-based PDFs using Anthropic Claude Vision API.

    This is the most robust method for scanned documents, photos, or
    poor quality PDFs where text extraction and OCR fail.

    Cost: ~$0.10-0.50 per statement depending on page count and complexity.
    """

    # Claude Vision API prompt for bank statement extraction
    EXTRACTION_PROMPT = """Analyze this bank statement page and extract ALL transactions visible.

Return a JSON object with this EXACT structure:
{
  "metadata": {
    "bank_name": "Bank name from statement",
    "account_number": "Last 4 digits only",
    "account_holder": "Account holder name",
    "statement_date": "YYYY-MM-DD or null",
    "period_start": "YYYY-MM-DD or null",
    "period_end": "YYYY-MM-DD or null",
    "opening_balance": 0.00,
    "closing_balance": 0.00,
    "currency": "EUR or GBP or BRL etc"
  },
  "transactions": [
    {
      "date": "YYYY-MM-DD",
      "description": "Transaction description",
      "money_in": 0.00,
      "money_out": 0.00,
      "balance": 0.00
    }
  ]
}

CRITICAL RULES:
1. Extract EVERY transaction - do not skip any
2. Dates must be in YYYY-MM-DD format
3. Use 0.00 for money_in if it's a debit (money out)
4. Use 0.00 for money_out if it's a credit (money in)
5. Preserve original descriptions exactly as shown
6. For balance field:
   - If statement shows running balance per transaction, extract it
   - If NO running balance shown (e.g., French banks), use 0.00 or null
7. For metadata:
   - Look for opening balance (ancien solde, solde précédent, opening balance)
   - Look for closing balance (nouveau solde, solde actuel, closing balance, solde en euros)
   - Look for intermediate/monthly balances (solde intermédiaire, solde à fin [mois])
   - Look for period dates (usually at top-right: "Du DD/MM/YYYY au DD/MM/YYYY" or similar)
   - Look for totals (totaux) showing sum of debits and credits
8. If metadata is not visible on this page, use null values
9. Return ONLY valid JSON - no explanatory text

Be extremely precise with amounts. Double-check every number."""

    def __init__(self, api_key: Optional[str] = None):
        """
        Initialize Vision API extractor.

        Args:
            api_key: Anthropic API key (if not provided, reads from ANTHROPIC_API_KEY env var)
        """
        super().__init__()

        if anthropic is None:
            raise ImportError(
                "anthropic is required for Vision extraction. "
                "Install it with: pip install anthropic"
            )

        if convert_from_path is None:
            raise ImportError(
                "pdf2image is required for Vision extraction. "
                "Install it with: pip install pdf2image"
            )

        if Image is None:
            raise ImportError(
                "Pillow is required for Vision extraction. "
                "Install it with: pip install Pillow"
            )

        # Get API key from parameter or environment
        self.api_key = api_key or os.getenv('ANTHROPIC_API_KEY')
        if not self.api_key:
            raise ValueError(
                "Anthropic API key required. Set ANTHROPIC_API_KEY environment variable "
                "or pass api_key parameter"
            )

        # Initialize Anthropic client
        self.client = anthropic.Anthropic(api_key=self.api_key)

        logger.info("Vision API extractor initialized")

    def can_handle(self, file_path: Path) -> bool:
        """
        Check if file is a PDF or image that can be processed.

        Args:
            file_path: Path to the document file

        Returns:
            True if file is PDF or image format
        """
        valid_extensions = {'.pdf', '.png', '.jpg', '.jpeg', '.tiff', '.bmp'}
        return file_path.suffix.lower() in valid_extensions

    def extract(self, file_path: Path) -> tuple[str, float]:
        """
        Extract text from document using Vision API.

        Args:
            file_path: Path to PDF or image file

        Returns:
            Tuple of (extracted_text, confidence_score)

        Raises:
            ExtractionError: If extraction fails
        """
        self.validate_file(file_path)

        if not self.can_handle(file_path):
            raise ExtractionError(f"File type not supported by Vision API: {file_path}")

        # Set up checkpoint file for incremental saving
        checkpoint_file = file_path.parent / f".{file_path.stem}_vision_checkpoint.json"

        try:
            logger.info(f"Extracting text using Vision API: {file_path}")

            # Convert PDF to images
            if file_path.suffix.lower() == '.pdf':
                images = self._pdf_to_images(file_path)
            else:
                # Single image file
                images = [Image.open(file_path)]

            logger.info(f"Processing {len(images)} page(s) with Vision API")

            # Process each page
            all_transactions = []
            metadata = None

            for page_num, image in enumerate(images, 1):
                # Progress indicator for user
                print(f"📄 Processing page {page_num}/{len(images)}...", flush=True)
                logger.info(f"Processing page {page_num}/{len(images)} with Vision API")

                try:
                    result = self._process_page(image, page_num)

                    # Extract metadata from first page that has it
                    if not metadata and result.get('metadata'):
                        meta = result['metadata']
                        # Only use if it has meaningful data
                        if meta.get('bank_name'):
                            metadata = meta
                            print(f"   ✓ Found bank: {meta.get('bank_name')}", flush=True)

                    # Accumulate transactions
                    if result.get('transactions'):
                        all_transactions.extend(result['transactions'])
                        txn_count = len(result['transactions'])
                        print(f"   ✓ Extracted {txn_count} transaction(s) from page {page_num}", flush=True)
                        logger.info(f"Extracted {txn_count} transactions from page {page_num}")

                    # Save checkpoint after each page
                    self._save_checkpoint(checkpoint_file, {
                        'metadata': metadata,
                        'transactions': all_transactions,
                        'pages_processed': page_num,
                        'total_pages': len(images)
                    })

                except Exception as e:
                    print(f"   ✗ Failed to process page {page_num}: {e}", flush=True)
                    logger.warning(f"Failed to process page {page_num}: {e}")
                    # Save checkpoint even on failure so we don't lose progress
                    self._save_checkpoint(checkpoint_file, {
                        'metadata': metadata,
                        'transactions': all_transactions,
                        'pages_processed': page_num,
                        'total_pages': len(images),
                        'last_error': str(e)
                    })
                    continue

            # Format output as text (similar to PDF extractor format)
            output_text = self._format_output(metadata, all_transactions)

            # Confidence based on successful extraction
            confidence = 85.0 if all_transactions else 50.0

            logger.info(f"Vision API extracted {len(all_transactions)} transactions with {confidence}% confidence")

            # Clean up checkpoint file on success
            if checkpoint_file.exists():
                checkpoint_file.unlink()
                logger.debug(f"Removed checkpoint file: {checkpoint_file}")

            return output_text, confidence

        except Exception as e:
            logger.error(f"Vision API extraction failed: {e}")
            logger.info(f"Progress saved to checkpoint: {checkpoint_file}")
            raise ExtractionError(f"Vision API extraction failed: {e}")

    def _pdf_to_images(self, pdf_path: Path) -> List[Image.Image]:
        """
        Convert PDF pages to images.

        Args:
            pdf_path: Path to PDF file

        Returns:
            List of PIL Image objects
        """
        try:
            # Convert PDF to images at 200 DPI (balance quality vs size)
            # Lower DPI to stay under Claude's 5MB limit per image
            images = convert_from_path(
                pdf_path,
                dpi=200,
                fmt='png'
            )
            logger.debug(f"Converted PDF to {len(images)} images")
            return images
        except Exception as e:
            raise ExtractionError(f"Failed to convert PDF to images: {e}")

    def _process_page(self, image: Image.Image, page_num: int) -> Dict[str, Any]:
        """
        Process a single page image with Vision API.

        Args:
            image: PIL Image object
            page_num: Page number for logging

        Returns:
            Dictionary with metadata and transactions
        """
        # Convert image to base64
        image_data = self._image_to_base64(image)

        # Call Claude Vision API
        try:
            message = self.client.messages.create(
                model="claude-sonnet-4-5-20250929",  # Sonnet 4.5 with vision
                max_tokens=4096,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": "image/jpeg",
                                    "data": image_data,
                                },
                            },
                            {
                                "type": "text",
                                "text": self.EXTRACTION_PROMPT
                            }
                        ],
                    }
                ],
            )

            # Parse JSON response
            response_text = message.content[0].text

            # Extract JSON from response (might have markdown code blocks)
            json_text = self._extract_json(response_text)
            result = json.loads(json_text)

            return result

        except Exception as e:
            logger.error(f"Vision API call failed for page {page_num}: {e}")
            raise

    def _image_to_base64(self, image: Image.Image) -> str:
        """
        Convert PIL Image to base64 string with compression.

        Args:
            image: PIL Image object

        Returns:
            Base64 encoded image string
        """
        import io

        # Convert to RGB if necessary
        if image.mode != 'RGB':
            image = image.convert('RGB')

        # Save to bytes buffer as JPEG with quality=85 (good balance of quality/size)
        buffer = io.BytesIO()
        image.save(buffer, format='JPEG', quality=85, optimize=True)
        buffer.seek(0)

        # Check size and reduce quality if needed to stay under 5MB
        image_bytes = buffer.getvalue()
        if len(image_bytes) > 5_000_000:  # 5MB
            logger.debug(f"Image too large ({len(image_bytes)} bytes), reducing quality")
            buffer = io.BytesIO()
            image.save(buffer, format='JPEG', quality=70, optimize=True)
            buffer.seek(0)
            image_bytes = buffer.getvalue()

            if len(image_bytes) > 5_000_000:
                logger.debug(f"Still too large ({len(image_bytes)} bytes), further reducing to quality=50")
                buffer = io.BytesIO()
                image.save(buffer, format='JPEG', quality=50, optimize=True)
                buffer.seek(0)
                image_bytes = buffer.getvalue()

        # Encode to base64
        return base64.b64encode(image_bytes).decode('utf-8')

    def _extract_json(self, text: str) -> str:
        """
        Extract JSON from response text (handles markdown code blocks).

        Args:
            text: Response text that may contain JSON

        Returns:
            Clean JSON string
        """
        # Remove markdown code blocks if present
        if '```json' in text:
            start = text.find('```json') + 7
            end = text.find('```', start)
            return text[start:end].strip()
        elif '```' in text:
            start = text.find('```') + 3
            end = text.find('```', start)
            return text[start:end].strip()
        else:
            # Assume entire text is JSON
            return text.strip()

    def _save_checkpoint(self, checkpoint_file: Path, data: Dict[str, Any]) -> None:
        """
        Save progress checkpoint to JSON file.

        Args:
            checkpoint_file: Path to checkpoint file
            data: Dictionary with metadata, transactions, and progress info
        """
        try:
            with open(checkpoint_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)
            logger.debug(f"Checkpoint saved: {data['pages_processed']}/{data['total_pages']} pages")
        except Exception as e:
            logger.warning(f"Failed to save checkpoint: {e}")

    def _format_output(self, metadata: Optional[Dict], transactions: List[Dict]) -> str:
        """
        Format extracted data as text (similar to PDF text extraction format).

        Args:
            metadata: Statement metadata
            transactions: List of transactions

        Returns:
            Formatted text string
        """
        lines = []

        # Add metadata
        if metadata:
            lines.append("=== STATEMENT METADATA ===")
            lines.append(f"Bank: {metadata.get('bank_name', 'Unknown')}")
            lines.append(f"Account: {metadata.get('account_number', 'Unknown')}")
            lines.append(f"Holder: {metadata.get('account_holder', 'Unknown')}")
            lines.append(f"Currency: {metadata.get('currency', 'Unknown')}")
            if metadata.get('period_start') and metadata.get('period_end'):
                lines.append(f"Period: {metadata['period_start']} to {metadata['period_end']}")
            if metadata.get('opening_balance') is not None:
                lines.append(f"Opening Balance: {metadata['opening_balance']}")
            if metadata.get('closing_balance') is not None:
                lines.append(f"Closing Balance: {metadata['closing_balance']}")
            lines.append("")

        # Add transactions
        lines.append("=== TRANSACTIONS ===")
        for txn in transactions:
            date = txn.get('date', 'Unknown')
            desc = txn.get('description', 'Unknown')
            money_in = txn.get('money_in', 0.0) or 0.0
            money_out = txn.get('money_out', 0.0) or 0.0
            balance = txn.get('balance', 0.0) or 0.0

            # Format similar to bank statement text
            if money_in > 0:
                lines.append(f"{date} | {desc} | +{money_in:.2f} | Balance: {balance:.2f}")
            else:
                lines.append(f"{date} | {desc} | -{money_out:.2f} | Balance: {balance:.2f}")

        return '\n'.join(lines)
