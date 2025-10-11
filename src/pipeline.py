"""
Main extraction pipeline - ETL orchestration.

Coordinates extraction, parsing, validation, and export.
Based on Monopoly's Pipeline pattern with our enhancements.
"""
import logging
import time
from pathlib import Path
from typing import Optional
from datetime import datetime

from .models import ExtractionResult, Statement
from .extractors import PDFExtractor
from .extractors.pdftotext_extractor import PDFToTextExtractor
from .parsers import TransactionParser
from .validators import BalanceValidator
from .exporters import ExcelExporter, generate_output_filename
from .config import get_bank_config_loader, BankConfig
from .utils import setup_logger, log_extraction_audit

logger = setup_logger()


class ExtractionPipeline:
    """
    Main pipeline for bank statement extraction (ETL pattern).

    Phases:
    1. Extract - Get text from PDF/image (tries pdfplumber, falls back to pdftotext)
    2. Transform - Parse transactions, validate balances
    3. Load - Export to Excel

    Based on Monopoly's pipeline.py with our architecture.
    """

    def __init__(self):
        """Initialize pipeline with extractors and parsers."""
        self.pdf_extractor = PDFExtractor()
        self.pdftotext_extractor = PDFToTextExtractor()
        self.bank_config_loader = get_bank_config_loader()
        self.validator = BalanceValidator(tolerance=0.01)
        self.exporter = ExcelExporter()

    def process(
        self,
        file_path: Path,
        output_path: Optional[Path] = None,
        bank_name: Optional[str] = None,
        perform_validation: bool = True
    ) -> ExtractionResult:
        """
        Process a bank statement end-to-end.

        Args:
            file_path: Path to statement file (PDF or image)
            output_path: Output Excel path (auto-generated if None)
            bank_name: Bank name (auto-detect if None)
            perform_validation: Whether to perform balance validation

        Returns:
            ExtractionResult with all data and metadata
        """
        logger.info(f"=" * 80)
        logger.info(f"Processing statement: {file_path.name}")
        logger.info(f"=" * 80)

        start_time = time.time()

        try:
            # Phase 1: EXTRACT
            logger.info("Phase 1: EXTRACT")
            text, extraction_confidence, extraction_method = self._extract_text(file_path)

            if not text:
                return self._create_error_result(
                    "Text extraction failed",
                    processing_time=time.time() - start_time
                )

            # Phase 2: TRANSFORM
            logger.info("Phase 2: TRANSFORM")

            # 2a. Detect bank
            bank_config = self._detect_bank(text, bank_name)
            if not bank_config:
                return self._create_error_result(
                    f"Could not detect bank. Supported banks: {self.bank_config_loader.get_all_banks()}",
                    processing_time=time.time() - start_time
                )

            # 2b. Extract statement metadata
            statement = self._extract_statement_metadata(text, bank_config)
            if not statement:
                return self._create_error_result(
                    "Could not extract statement metadata",
                    processing_time=time.time() - start_time
                )

            # 2c. Parse transactions
            transactions = self._parse_transactions(text, bank_config, statement)
            if not transactions:
                return self._create_error_result(
                    "No transactions found in statement",
                    processing_time=time.time() - start_time
                )

            # 2d. Validate balances
            balance_reconciled = False
            warnings = []

            if perform_validation:
                balance_reconciled, validation_messages = self.validator.perform_full_validation(
                    statement,
                    transactions
                )
                if not balance_reconciled:
                    warnings.extend(validation_messages)

            # 2e. Calculate overall confidence
            overall_confidence = self._calculate_overall_confidence(
                transactions,
                extraction_confidence,
                balance_reconciled
            )

            # Create result
            result = ExtractionResult(
                statement=statement,
                transactions=transactions,
                success=True,
                balance_reconciled=balance_reconciled,
                confidence_score=overall_confidence,
                extraction_method=extraction_method,
                warnings=warnings,
                processing_time=time.time() - start_time
            )

            # Phase 3: LOAD
            logger.info("Phase 3: LOAD (Export)")
            if output_path is None:
                output_path = generate_output_filename(
                    bank_name=bank_config.bank_name,
                    statement_date=statement.statement_start_date
                )

            self.exporter.export(result, output_path)
            logger.info(f"✓ Export complete: {output_path}")

            # Log audit trail
            log_extraction_audit(
                file_path=file_path,
                method=extraction_method,
                success=True,
                transaction_count=len(transactions),
                confidence=overall_confidence
            )

            processing_time = time.time() - start_time
            logger.info(f"=" * 80)
            logger.info(f"Processing complete in {processing_time:.2f} seconds")
            logger.info(f"  Transactions: {len(transactions)}")
            logger.info(f"  Confidence: {overall_confidence:.1f}%")
            logger.info(f"  Reconciled: {'✓ Yes' if balance_reconciled else '✗ No'}")
            logger.info(f"=" * 80)

            return result

        except Exception as e:
            logger.exception(f"Pipeline failed: {e}")
            log_extraction_audit(
                file_path=file_path,
                method="unknown",
                success=False,
                error=str(e)
            )
            return self._create_error_result(
                f"Extraction failed: {e}",
                processing_time=time.time() - start_time
            )

    def _extract_text(self, file_path: Path) -> tuple[str, float, str]:
        """
        Extract text from file using cascading strategies.

        Strategy order:
        1. PDF text extraction with pdfplumber (fast, good for most PDFs)
        2. PDF text extraction with pdftotext (fallback for problematic PDFs like Halifax)
        3. OCR (medium speed/cost) - TODO
        4. Vision API (slow, expensive) - TODO

        Args:
            file_path: Path to statement file

        Returns:
            Tuple of (text, confidence, method_name)
        """
        logger.info(f"Extracting text from: {file_path.name}")

        # Try PDF text extraction
        if file_path.suffix.lower() == '.pdf':
            # Check if this is Halifax, HSBC, NatWest, or Barclays - use pdftotext for layout preservation
            # (Halifax PDFs have font issues, HSBC/NatWest/Barclays need precise column positions)
            try:
                # Quick peek to detect bank
                text_sample, _ = self.pdf_extractor.extract(file_path)
                if text_sample:
                    bank_detected = None
                    text_lower = text_sample.lower()

                    if 'halifax' in text_lower:
                        bank_detected = 'Halifax'
                    elif 'hsbc' in text_lower:
                        bank_detected = 'HSBC'
                    elif 'natwest' in text_lower or 'national westminster' in text_lower:
                        bank_detected = 'NatWest'
                    elif 'barclays' in text_lower:
                        bank_detected = 'Barclays'

                    if bank_detected:
                        logger.info(f"Detected {bank_detected} statement - using pdftotext for layout preservation")
                        text, confidence = self.pdftotext_extractor.extract(file_path)
                        if text:
                            logger.info(f"✓ pdftotext extraction successful")
                            return text, confidence, "pdftotext"
            except Exception:
                pass  # Continue to normal extraction flow

            # Try pdfplumber first (works well for most PDFs)
            try:
                text, confidence = self.pdf_extractor.extract(file_path)
                if text and confidence > 80:
                    logger.info(f"✓ PDF extraction successful (confidence: {confidence:.1f}%)")
                    return text, confidence, "pdfplumber"
                elif text:
                    logger.warning(f"pdfplumber produced low-confidence text ({confidence:.1f}%), trying pdftotext...")
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}, trying pdftotext...")

            # Try pdftotext as fallback (better for some PDFs with font issues)
            try:
                text, confidence = self.pdftotext_extractor.extract(file_path)
                if text:
                    logger.info(f"✓ pdftotext extraction successful")
                    return text, confidence, "pdftotext"
            except RuntimeError as e:
                # pdftotext not installed
                logger.warning(f"pdftotext not available: {e}")
            except Exception as e:
                logger.warning(f"pdftotext extraction failed: {e}")

        # TODO: Try OCR for scanned PDFs/images
        # TODO: Try Vision API as fallback

        return "", 0.0, "none"

    def _detect_bank(
        self,
        text: str,
        bank_name_hint: Optional[str]
    ) -> Optional[BankConfig]:
        """
        Detect bank from statement text.

        Args:
            text: Extracted text
            bank_name_hint: User-provided bank name (if any)

        Returns:
            BankConfig or None
        """
        logger.info("Detecting bank...")

        if bank_name_hint:
            config = self.bank_config_loader.get_config(bank_name_hint)
            if config:
                logger.info(f"✓ Using provided bank: {config.bank_name}")
                return config

        # Auto-detect
        config = self.bank_config_loader.detect_bank(text)
        if config:
            logger.info(f"✓ Detected bank: {config.bank_name}")
            return config

        logger.error("✗ Could not detect bank")
        return None

    def _extract_statement_metadata(
        self,
        text: str,
        bank_config: BankConfig
    ) -> Optional[Statement]:
        """
        Extract statement metadata from text.

        Uses header patterns from bank config to find:
        - Account number, sort code
        - Statement period dates
        - Opening/closing balances

        Args:
            text: Extracted text
            bank_config: Bank configuration

        Returns:
            Statement object or None
        """
        logger.info("Extracting statement metadata...")

        import re
        from .utils import parse_currency, parse_date

        header_patterns = bank_config.header_patterns

        # Extract fields using patterns
        extracted = {}
        for field_name, pattern in header_patterns.items():
            match = re.search(pattern, text, re.MULTILINE)
            if match:
                # Handle patterns with multiple capture groups (from alternation)
                # Get the first non-None group
                value = None
                if match.groups():
                    for group in match.groups():
                        if group is not None:
                            value = group
                            break
                if value is None:
                    value = match.group(0)
                extracted[field_name] = value
                logger.debug(f"Found {field_name}: {extracted[field_name]}")

        # Parse required fields
        try:
            # Account info
            account_number = extracted.get('account_number', 'Unknown')
            account_holder = extracted.get('account_name')  # Note: YAML uses 'account_name' key
            sort_code = extracted.get('sort_code')

            # Dates
            period_start_str = extracted.get('period_start')
            period_end_str = extracted.get('period_end')

            if not period_start_str or not period_end_str:
                logger.error("Missing statement period dates")
                return None

            # Parse end date first (it has the year)
            statement_end = parse_date(period_end_str, bank_config.date_formats)
            if not statement_end:
                logger.error("Could not parse statement end date")
                return None

            # For HSBC: if start date doesn't have year, add it from end date
            if bank_config.bank_name.lower() == 'hsbc':
                # Check if period_start_str has a 4-digit year
                import re
                if not re.search(r'\d{4}', period_start_str):
                    # Add year from end date
                    period_start_str = f"{period_start_str} {statement_end.year}"
                    logger.debug(f"Added year to HSBC period_start: {period_start_str}")

            statement_start = parse_date(period_start_str, bank_config.date_formats)
            if not statement_start:
                logger.error("Could not parse statement start date")
                return None

            # Balances
            opening_balance = parse_currency(extracted.get('previous_balance', '0'))
            closing_balance = parse_currency(extracted.get('new_balance', '0'))

            if opening_balance is None or closing_balance is None:
                logger.error("Could not parse statement balances")
                return None

            statement = Statement(
                bank_name=bank_config.bank_name,
                account_number=account_number,
                account_holder=account_holder,
                statement_start_date=statement_start,
                statement_end_date=statement_end,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                currency="GBP",
                sort_code=sort_code
            )

            logger.info(f"✓ Metadata extracted: {account_number}, {statement_start.date()} to {statement_end.date()}")
            logger.debug(f"Account holder: '{account_holder}', Sort code: '{sort_code}'")
            return statement

        except Exception as e:
            logger.error(f"Failed to extract statement metadata: {e}")
            return None

    def _parse_transactions(
        self,
        text: str,
        bank_config: BankConfig,
        statement: Statement
    ) -> list:
        """
        Parse transactions from text.

        Args:
            text: Extracted text
            bank_config: Bank configuration
            statement: Statement metadata (for date inference)

        Returns:
            List of Transaction objects
        """
        logger.info("Parsing transactions...")

        parser = TransactionParser(bank_config)
        transactions = parser.parse_text(
            text,
            statement_start_date=statement.statement_start_date,
            statement_end_date=statement.statement_end_date
        )

        logger.info(f"✓ Parsed {len(transactions)} transactions")
        return transactions

    def _calculate_overall_confidence(
        self,
        transactions: list,
        extraction_confidence: float,
        balance_reconciled: bool
    ) -> float:
        """
        Calculate overall confidence score.

        Factors:
        - Extraction confidence
        - Average transaction confidence
        - Balance reconciliation

        Args:
            transactions: List of transactions
            extraction_confidence: Text extraction confidence
            balance_reconciled: Whether balances reconciled

        Returns:
            Overall confidence score (0-100)
        """
        if not transactions:
            return 0.0

        # Average transaction confidence
        avg_txn_confidence = sum(t.confidence for t in transactions) / len(transactions)

        # Weighted average
        overall = (
            extraction_confidence * 0.3 +
            avg_txn_confidence * 0.5 +
            (100.0 if balance_reconciled else 50.0) * 0.2
        )

        return round(overall, 2)

    def _create_error_result(
        self,
        error_message: str,
        processing_time: float
    ) -> ExtractionResult:
        """Create error result."""
        logger.error(error_message)

        return ExtractionResult(
            statement=None,
            transactions=[],
            success=False,
            balance_reconciled=False,
            confidence_score=0.0,
            extraction_method="failed",
            error_message=error_message,
            processing_time=processing_time
        )
