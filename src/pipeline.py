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
            transactions = self._parse_transactions(text, bank_config, statement, file_path)
            if not transactions:
                return self._create_error_result(
                    "No transactions found in statement",
                    processing_time=time.time() - start_time
                )

            # 2c.1. Fix balances for combined statements
            # For combined statements, the opening/closing balances extracted from metadata
            # refer to the first period only. We need to use transaction data instead.
            if hasattr(statement, '_is_combined') and statement._is_combined and transactions:
                # Sort transactions by date to find chronological first/last
                sorted_txns = sorted(transactions, key=lambda t: t.date)

                # Calculate opening balance from chronologically first transaction
                first_txn = sorted_txns[0]
                calculated_opening = first_txn.balance - first_txn.money_in + first_txn.money_out

                # Use chronologically last transaction's balance as closing
                calculated_closing = sorted_txns[-1].balance

                logger.info(f"Combined statement balance correction:")
                logger.info(f"  Opening: £{statement.opening_balance:.2f} → £{calculated_opening:.2f} (from {first_txn.date.date()})")
                logger.info(f"  Closing: £{statement.closing_balance:.2f} → £{calculated_closing:.2f} (from {sorted_txns[-1].date.date()})")

                statement.opening_balance = calculated_opening
                statement.closing_balance = calculated_closing

            # 2c.2. Refine period dates from transactions if needed
            # When statement only has a single date (not a period range), infer the range from transactions
            if statement.statement_start_date == statement.statement_end_date and transactions:
                sorted_txns = sorted(transactions, key=lambda t: t.date)

                # Check for BROUGHT FORWARD transaction (marks official statement start)
                brought_forward_txn = None
                for txn in sorted_txns:
                    if "BROUGHT FORWARD" in txn.description.upper() or "START BALANCE" in txn.description.upper():
                        brought_forward_txn = txn
                        break

                # Use BROUGHT FORWARD date as start if present, otherwise use earliest transaction
                actual_start = brought_forward_txn.date if brought_forward_txn else sorted_txns[0].date
                actual_end = sorted_txns[-1].date

                logger.info(f"Refining statement period from transactions:")
                if statement.statement_start_date and statement.statement_end_date:
                    logger.info(f"  Original: {statement.statement_start_date.date()} to {statement.statement_end_date.date()}")
                else:
                    logger.info(f"  Original: None (no dates in metadata)")
                logger.info(f"  Refined: {actual_start.date()} to {actual_end.date()}")
                if brought_forward_txn:
                    logger.info(f"  (Using BROUGHT FORWARD transaction date as start)")

                statement.statement_start_date = actual_start
                statement.statement_end_date = actual_end

            # 2c.3. Calculate balances from transactions if missing
            # When statement has no balance metadata (both opening and closing are 0), calculate from transactions
            if statement.opening_balance == 0.0 and statement.closing_balance == 0.0 and transactions:
                sorted_txns = sorted(transactions, key=lambda t: t.date)

                # Check for BROUGHT FORWARD transaction (authoritative opening balance)
                brought_forward_txn = None
                for txn in sorted_txns:
                    if "BROUGHT FORWARD" in txn.description.upper() or "START BALANCE" in txn.description.upper():
                        brought_forward_txn = txn
                        break

                # Calculate opening balance
                if brought_forward_txn:
                    # Use BROUGHT FORWARD balance as the authoritative opening balance
                    calculated_opening = brought_forward_txn.balance
                    opening_date = brought_forward_txn.date
                    logger.info(f"Using BROUGHT FORWARD transaction for opening balance")
                else:
                    # Calculate from first transaction (backward from its balance)
                    first_txn = sorted_txns[0]
                    calculated_opening = first_txn.balance - first_txn.money_in + first_txn.money_out
                    opening_date = first_txn.date

                # Use last transaction's balance as closing
                calculated_closing = sorted_txns[-1].balance

                logger.info(f"Calculating statement balances from transactions:")
                logger.info(f"  Opening: £0.00 → £{calculated_opening:.2f} (from {opening_date.date()})")
                logger.info(f"  Closing: £0.00 → £{calculated_closing:.2f} (from {sorted_txns[-1].date.date()})")

                statement.opening_balance = calculated_opening
                statement.closing_balance = calculated_closing

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
            # Try pdftotext first (better layout preservation with -layout flag)
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

            # Fallback to pdfplumber
            try:
                text, confidence = self.pdf_extractor.extract(file_path)
                if text:
                    logger.info(f"✓ pdfplumber extraction successful (fallback)")
                    return text, confidence, "pdfplumber"
            except Exception as e:
                logger.warning(f"pdfplumber extraction failed: {e}")

        # Try Vision API for scanned PDFs/images (last resort - expensive but robust)
        try:
            from .extractors.vision_extractor import VisionExtractor
            logger.info("Attempting Vision API extraction (scanned document detected)")

            vision_extractor = VisionExtractor()
            text, confidence = vision_extractor.extract(file_path)
            if text:
                logger.info(f"✓ Vision API extraction successful")
                return text, confidence, "vision_api"
        except ImportError as e:
            logger.warning(f"Vision API extractor not available: {e}")
        except ValueError as e:
            logger.warning(f"Vision API not configured: {e}")
        except Exception as e:
            logger.error(f"Vision API extraction failed: {e}")

        # TODO: Try OCR (Tesseract) for medium quality scans (cheaper than Vision API)

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

            # Handle statements with only a statement_date (no explicit period range)
            if not period_start_str or not period_end_str:
                statement_date_str = extracted.get('statement_date')
                if not statement_date_str:
                    # No dates in metadata - will infer from transactions
                    logger.warning("Missing statement period dates in metadata - will infer from transactions")
                    statement_start = None
                    statement_end = None
                else:
                    # Use statement date as a reference point
                    # We'll infer the actual period from transaction dates later
                    statement_date = parse_date(statement_date_str, bank_config.date_formats)
                    if not statement_date:
                        logger.error("Could not parse statement date")
                        return None

                    # Use statement date for both start and end (will be refined from transactions)
                    statement_start = statement_date
                    statement_end = statement_date
                    logger.info(f"Using statement date {statement_date.date()} as initial period (will be refined from transactions)")
            else:
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

            # Check if this is a combined statement with multiple periods
            # For combined statements, expand date range to cover all periods
            expanded_start, expanded_end = self._detect_combined_statement_date_range(
                text,
                statement_start,
                statement_end,
                bank_config
            )

            is_combined_statement = False
            if expanded_start and expanded_end:
                logger.info(f"Combined statement detected - expanded date range from "
                           f"{statement_start.date()} to {statement_end.date()} → "
                           f"{expanded_start.date()} to {expanded_end.date()}")
                statement_start = expanded_start
                statement_end = expanded_end
                is_combined_statement = True
                # Note: For combined statements, balances will be corrected after parsing transactions

            statement = Statement(
                bank_name=bank_config.bank_name,
                account_number=account_number,
                account_holder=account_holder,
                statement_start_date=statement_start,
                statement_end_date=statement_end,
                opening_balance=opening_balance,
                closing_balance=closing_balance,
                currency=bank_config.currency,
                sort_code=sort_code
            )

            # Store combined statement flag for later use
            statement._is_combined = is_combined_statement

            # Log metadata extraction
            if statement_start and statement_end:
                logger.info(f"✓ Metadata extracted: {account_number}, {statement_start.date()} to {statement_end.date()}")
            else:
                logger.info(f"✓ Metadata extracted: {account_number} (dates will be inferred from transactions)")
            logger.debug(f"Account holder: '{account_holder}', Sort code: '{sort_code}'")
            return statement

        except Exception as e:
            logger.error(f"Failed to extract statement metadata: {e}")
            return None

    def _detect_combined_statement_date_range(
        self,
        text: str,
        initial_start: datetime,
        initial_end: datetime,
        bank_config: BankConfig
    ) -> tuple:
        """
        Detect if this is a combined statement with multiple periods.
        If so, find the full date range by scanning all period markers.

        Args:
            text: Statement text
            initial_start: Initial statement start date
            initial_end: Initial statement end date
            bank_config: Bank configuration

        Returns:
            Tuple of (expanded_start, expanded_end) or (None, None) if not combined
        """
        import re
        from .utils import parse_date, infer_year_from_period

        # Look for period markers - different banks use different patterns:
        # - Barclays: "DD Mon YYYY Start balance" or "DD Mon YYYY BROUGHT FORWARD"
        # - Monzo: "DD/MM/YYYY - DD/MM/YYYY" date ranges

        # Pattern 1: Barclays-style period markers
        barclays_markers = re.findall(
            r'^\s*(\d{1,2}\s+[A-Z][a-z]{2,9}(?:\s+\d{4})?)\s+(?:Start balance|BROUGHT FORWARD)',
            text,
            re.MULTILINE | re.IGNORECASE
        )

        # Pattern 2: Monzo-style date ranges (extract both start and end dates)
        monzo_ranges = re.findall(
            r'(\d{1,2}/\d{1,2}/\d{4})\s*-\s*(\d{1,2}/\d{1,2}/\d{4})',
            text,
            re.MULTILINE
        )

        # Pattern 3: Crédit Agricole-style balance dates
        # "Ancien solde créditeur au 01.09.2025" and "Nouveau solde créditeur au 01.10.2025"
        credit_agricole_dates = re.findall(
            r'(?:Ancien|Nouveau)\s+solde.*?au\s+(\d{2}\.\d{2}\.\d{4})',
            text,
            re.MULTILINE | re.IGNORECASE
        )

        # Use whichever pattern found more matches
        if len(barclays_markers) > 1:
            period_markers = barclays_markers
            pattern_type = "Barclays-style"
        elif len(monzo_ranges) > 1:
            period_markers = monzo_ranges
            pattern_type = "Monzo-style"
        elif len(credit_agricole_dates) > 2:  # Need at least opening and closing dates
            period_markers = credit_agricole_dates
            pattern_type = "CreditAgricole-style"
        else:
            # Single period, no expansion needed
            return None, None

        logger.info(f"Found {len(period_markers)} {pattern_type} period markers - this is a combined statement")

        # Parse all period dates
        period_dates = []
        for marker in period_markers:
            if pattern_type == "Barclays-style":
                # Parse start dates only
                parsed = infer_year_from_period(marker, initial_start, initial_end, bank_config.date_formats)
                if not parsed:
                    parsed = parse_date(marker, bank_config.date_formats)
                if parsed:
                    period_dates.append(parsed)
                    logger.debug(f"Parsed period marker: {marker} → {parsed.date()}")
                else:
                    logger.warning(f"Could not parse period marker: {marker}")
            elif pattern_type == "Monzo-style":
                # Monzo: marker is a tuple (start_date, end_date)
                start_str, end_str = marker
                start_parsed = parse_date(start_str, bank_config.date_formats)
                end_parsed = parse_date(end_str, bank_config.date_formats)
                if start_parsed and end_parsed:
                    period_dates.append(start_parsed)
                    period_dates.append(end_parsed)
                    logger.debug(f"Parsed period range: {start_str} - {end_str} → {start_parsed.date()} to {end_parsed.date()}")
                else:
                    logger.warning(f"Could not parse period range: {start_str} - {end_str}")
            else:
                # CreditAgricole: marker is a date string "DD.MM.YYYY"
                parsed = parse_date(marker, bank_config.date_formats)
                if parsed:
                    period_dates.append(parsed)
                    logger.debug(f"Parsed period marker: {marker} → {parsed.date()}")
                else:
                    logger.warning(f"Could not parse period marker: {marker}")

        if len(period_dates) < 2:
            # Couldn't parse enough dates to determine range
            return None, None

        # Find earliest and latest dates
        earliest = min(period_dates)
        latest = max(period_dates)

        # The latest period marker is the START of the last period
        # The actual end date is likely ~30 days after the last marker
        # Use the original end date if it's later than the latest marker
        if initial_end > latest:
            latest = initial_end

        # Similarly, use original start if earlier than earliest marker
        if initial_start < earliest:
            earliest = initial_start

        logger.info(f"Combined statement date range: {earliest.date()} to {latest.date()}")

        return earliest, latest

    def _parse_transactions(
        self,
        text: str,
        bank_config: BankConfig,
        statement: Statement,
        file_path: Path
    ) -> list:
        """
        Parse transactions from text.

        Args:
            text: Extracted text
            bank_config: Bank configuration
            statement: Statement metadata (for date inference)
            file_path: Path to PDF file (for parsers that need direct PDF access)

        Returns:
            List of Transaction objects
        """
        logger.info("Parsing transactions...")

        # Set PDF path for parsers that use pdfplumber for direct PDF access
        if bank_config.bank_name.lower() == 'credit_agricole':
            from .parsers.credit_agricole_parser import CreditAgricoleParser
            CreditAgricoleParser._pdf_path = file_path
        elif bank_config.bank_name.lower() == 'pagseguro':
            from .parsers.pagseguro_parser import PagSeguroParser
            PagSeguroParser._pdf_path = file_path

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
