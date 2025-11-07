"""PagSeguro bank statement parser.

Handles PagSeguro (Brazilian digital bank) statement format with:
- Brazilian Real currency (R$)
- Portuguese language descriptions
- Date format: DD/MM/YYYY
- Three-column format: Data, Descrição, Valor
- Daily balance rows ("Saldo do dia")
- Negative amounts for money out (-R$)
- Positive amounts for money in (R$)

Format characteristics:
- Date format: "02/03/2025" (day/month/year)
- Description in Portuguese
- Amount format: "R$ 25,80" or "-R$ 25,80"
- Uses comma for decimal separator
- Daily balance summary rows
"""

import logging
import re
from datetime import datetime
from typing import Optional, List
from pathlib import Path

try:
    import pdfplumber
    HAS_PDFPLUMBER = True
except ImportError:
    HAS_PDFPLUMBER = False

from .base_parser import BaseTransactionParser
from ..models import Transaction
from ..utils import parse_date, infer_year_from_period

logger = logging.getLogger(__name__)


class PagSeguroParser(BaseTransactionParser):
    """Parser for PagSeguro bank statements.

    Uses pdfplumber for text extraction and pattern-based parsing.
    """

    # Class variable to store PDF path (set by pipeline before parsing)
    _pdf_path: Optional[Path] = None

    def parse_transactions(
        self,
        text: str,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse PagSeguro statement using pdfplumber text extraction.

        PagSeguro format:
        - Data column (date)
        - Descrição column (description)
        - Valor column (amount with R$ prefix)
        - "Saldo do dia" rows showing daily balance

        Args:
            text: Raw text from pdftotext (unused, kept for interface compatibility)
            statement_start_date: Statement period start
            statement_end_date: Statement period end

        Returns:
            List of Transaction objects
        """
        if not HAS_PDFPLUMBER:
            logger.error("pdfplumber is required for PagSeguro parsing but not installed")
            return []

        if not self._pdf_path:
            logger.error(f"PDF path not set: {self._pdf_path}")
            return []

        if not Path(self._pdf_path).exists():
            logger.error(f"PDF file not found: {self._pdf_path}")
            return []

        logger.info(f"Using pdfplumber text extraction for PagSeguro statement")

        return self._parse_with_pdfplumber(statement_start_date, statement_end_date)

    def _parse_with_pdfplumber(
        self,
        statement_start_date: Optional[datetime],
        statement_end_date: Optional[datetime]
    ) -> List[Transaction]:
        """
        Parse PagSeguro statement using pdfplumber text extraction.

        Returns:
            List of Transaction objects
        """
        transactions = []
        current_balance = 0.0

        try:
            with pdfplumber.open(self._pdf_path) as pdf:
                for page_num, page in enumerate(pdf.pages, 1):
                    # Extract text from page
                    text = page.extract_text()

                    if not text:
                        continue

                    # Split into lines
                    lines = text.split('\n')

                    for line in lines:
                        # Skip header/metadata lines
                        # Note: Use specific patterns to avoid false matches
                        # E.g., "Conta 17015908-1" (account number) vs "Cartão da Conta" (debit card)
                        skip_patterns = [
                            'PagSeguro Internet',
                            'Agência',
                            'CPF:',
                            'Extrato da conta',
                            'Emitido em:',
                            'Periodo:',
                            'Data Descrição Valor'
                        ]

                        # Check for "Conta" only at start of line (account number metadata)
                        if any(skip in line for skip in skip_patterns):
                            continue
                        if line.strip().startswith('Conta '):
                            continue

                        # Check if it's a balance line
                        if 'Saldo do dia' in line:
                            balance_match = re.search(r'R\$\s*([\d.,]+)', line)
                            if balance_match:
                                current_balance = self._parse_brazilian_number(balance_match.group(1))
                                logger.debug(f"Balance update: R${current_balance:,.2f}")
                            continue

                        # Parse transaction line
                        # Format: DD/MM/YYYY Description -R$ amount or R$ amount
                        date_match = re.match(r'^(\d{2}/\d{2}/\d{4})\s+(.+?)\s+(-?R\$\s*[\d.,]+)$', line.strip())

                        if not date_match:
                            continue

                        date_str = date_match.group(1)
                        description = date_match.group(2).strip()
                        amount_str = date_match.group(3)

                        # Parse date
                        transaction_date = parse_date(date_str, self.config.date_formats)
                        if not transaction_date:
                            logger.warning(f"Could not parse date: {date_str}")
                            continue

                        # Parse amount
                        amount = self._parse_brazilian_number(amount_str.replace('R$', '').strip())

                        # Determine if money in or out
                        if '-' in amount_str:
                            money_out = abs(amount)
                            money_in = 0.0
                        else:
                            money_in = amount
                            money_out = 0.0

                        # Translate description to English
                        translated_description = self._translate_description(description)

                        # Create transaction
                        transaction = Transaction(
                            date=transaction_date,
                            description=description,
                            description_translated=translated_description,
                            money_in=money_in,
                            money_out=money_out,
                            balance=current_balance,
                            confidence=self._calculate_confidence(
                                transaction_date, description, money_in, money_out, current_balance
                            )
                        )

                        transactions.append(transaction)

        except Exception as e:
            logger.error(f"Error parsing PagSeguro PDF with pdfplumber: {e}")
            import traceback
            logger.error(traceback.format_exc())
            return []

        logger.info(f"Parsed {len(transactions)} PagSeguro transactions using pdfplumber")
        return transactions

    def _parse_brazilian_number(self, number_str: str) -> float:
        """
        Parse Brazilian number format to float.

        Brazilian format: 1.234,56 (dot for thousands, comma for decimal)

        Args:
            number_str: String representation of number

        Returns:
            Float value
        """
        if not number_str:
            return 0.0

        # Remove any leading minus/negative symbols
        is_negative = number_str.strip().startswith('-')

        # Remove currency symbols and spaces
        clean = number_str.replace('R$', '').replace('-', '').replace(' ', '').strip()

        # Replace thousand separator (dot) and decimal separator (comma)
        clean = clean.replace('.', '')  # Remove thousands separator
        clean = clean.replace(',', '.')  # Convert decimal separator to dot

        try:
            value = float(clean)
            return -value if is_negative else value
        except ValueError:
            logger.warning(f"Could not parse Brazilian number: {number_str}")
            return 0.0

    def _translate_description(self, description: str) -> str:
        """
        Translate Portuguese banking description to English.

        Uses pattern-based replacement to translate common Portuguese banking terms
        while preserving merchant names, dates, and amounts.

        Args:
            description: Portuguese transaction description

        Returns:
            English translation
        """
        if not description:
            return ""

        translated = description

        # Translation mappings (Portuguese -> English)
        translations = {
            # Transaction types
            r'\bPix enviado\b': 'Pix sent',
            r'\bPix recebido\b': 'Pix received',
            r'\bCartão da Conta\b': 'Debit Card',
            r'\bRecarga de celular\b': 'Mobile top-up',
            r'\bSaldo do dia\b': 'Daily balance',
            r'\bRendimento da conta\b': 'Account yield',
            r'\bRendimento líquido\b': 'Net yield',
            r'\bTransferência enviada\b': 'Transfer sent',
            r'\bTransferência recebida\b': 'Transfer received',
            r'\bPagamento\b': 'Payment',
            r'\bDepósito\b': 'Deposit',
            r'\bSaque\b': 'Withdrawal',
            r'\bEstorno\b': 'Refund',
            r'\bTarifa\b': 'Fee',

            # Common phrases
            r'\bsobre dinheiro em conta\b': 'on account balance',
            r'\bde celular\b': 'mobile',

            # Mobile operators (keep as-is but could translate)
            # r'\bClaro\b': 'Claro',
            # r'\bVivo\b': 'Vivo',
            # r'\bTim\b': 'Tim',
        }

        # Apply translations using regex for word boundaries
        for portuguese_pattern, english_term in translations.items():
            translated = re.sub(portuguese_pattern, english_term, translated, flags=re.IGNORECASE)

        return translated
