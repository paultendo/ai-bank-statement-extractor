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
    1. Extract - Get text from PDF/image
    2. Transform - Parse transactions, validate balances
    3. Load - Export to Excel

    Based on Monopoly's pipeline.py with our architecture.
    """

    def __init__(self):
        """Initialize pipeline with extractors and parsers."""
        self.pdf_extractor = PDFExtractor()
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
        1. PDF text extraction (fast, cheap)
        2. OCR (medium speed/cost) - TODO
        3. Vision API (slow, expensive) - TODO

        Args:
            file_path: Path to statement file

        Returns:
            Tuple of (text, confidence, method_name)
        """
        logger.info(f"Extracting text from: {file_path.name}")

        # Try PDF text extraction
        if file_path.suffix.lower() == '.pdf':
            try:
                text, confidence = self.pdf_extractor.extract(file_path)
                if text and confidence > 80:
                    logger.info(f"✓ PDF extraction successful (confidence: {confidence:.1f}%)")
                    return text, confidence, "pdf_text"
            except Exception as e:
                logger.warning(f"PDF extraction failed: {e}")

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
            match = re.search(pattern, text)
            if match:
                extracted[field_name] = match.group(1) if match.groups() else match.group(0)
                logger.debug(f"Found {field_name}: {extracted[field_name]}")

        # Parse required fields
        try:
            # Account info
            account_number = extracted.get('account_number', 'Unknown')
            sort_code = extracted.get('sort_code')

            # Dates
            period_start_str = extracted.get('period_start')
            period_end_str = extracted.get('period_end')

            if not period_start_str or not period_end_str:
                logger.error("Missing statement period dates")
                return None

            statement_start = parse_date(period_start_str, bank_config.date_formats)
            statement_end = parse_date(period_end_str, bank_config.date_formats)

            if not statement_start or not statement_end:
                logger.error("Could not parse statement dates")
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
                statement_start_date=statement_start,
                statement_end_date=statement_end,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                currency="GBP",
                sort_code=sort_code
            )

            logger.info(f"✓ Metadata extracted: {account_number}, {statement_start.date()} to {statement_end.date()}")
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
