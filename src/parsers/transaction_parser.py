"""Transaction parser factory.

This module provides a factory for creating bank-specific transaction parsers.
Each bank has its own parser class that inherits from BaseTransactionParser.

Design Pattern: Factory Method
- Encapsulates parser instantiation logic
- Makes it easy to add new banks without modifying existing code
- Provides a single entry point for all parsing operations
"""

import logging
from typing import Optional, List
from datetime import datetime

from ..config import BankConfig
from ..models import Transaction
from .base_parser import BaseTransactionParser
from .halifax_parser import HalifaxParser
from .hsbc_parser import HSBCParser
from .natwest_parser import NatWestParser
from .barclays_parser import BarclaysParser
from .monzo_parser import MonzoTransactionParser
from .santander_parser import SantanderParser
from .tsb_parser import TSBParser
from .nationwide_parser import NationwideParser

logger = logging.getLogger(__name__)


class TransactionParser:
    """
    Factory class for creating bank-specific transaction parsers.

    This class acts as a facade that routes to the appropriate bank-specific
    parser based on the bank configuration.

    Usage:
        parser = TransactionParser(bank_config)
        transactions = parser.parse_text(text, start_date, end_date)
    """

    def __init__(self, bank_config: BankConfig):
        """
        Initialize parser factory with bank configuration.

        Args:
            bank_config: Bank-specific configuration
        """
        self.config = bank_config
        self._parser = self._create_parser()

    def _create_parser(self) -> BaseTransactionParser:
        """
        Create the appropriate bank-specific parser.

        Returns:
            BaseTransactionParser instance for the bank

        Raises:
            ValueError: If bank is not supported
        """
        bank_name = self.config.bank_name.lower()

        parser_map = {
            'halifax': HalifaxParser,
            'hsbc': HSBCParser,
            'natwest': NatWestParser,
            'barclays': BarclaysParser,
            'monzo': MonzoTransactionParser,
            'santander': SantanderParser,
            'tsb': TSBParser,
            'nationwide': NationwideParser,
        }

        parser_class = parser_map.get(bank_name)
        if not parser_class:
            supported = ', '.join(parser_map.keys())
            raise ValueError(
                f"Unsupported bank: {bank_name}. "
                f"Supported banks: {supported}"
            )

        logger.info(f"Created {parser_class.__name__} for {bank_name}")
        return parser_class(self.config)

    def parse_text(
        self,
        text: str,
        statement_start_date: Optional[datetime] = None,
        statement_end_date: Optional[datetime] = None
    ) -> List[Transaction]:
        """
        Parse transactions from statement text.

        This method delegates to the bank-specific parser's parse_transactions method.

        Args:
            text: Extracted text from statement
            statement_start_date: Statement period start (for year inference)
            statement_end_date: Statement period end (for year inference)

        Returns:
            List of parsed Transaction objects
        """
        logger.info(f"Parsing transactions with {self._parser.__class__.__name__}")
        return self._parser.parse_transactions(
            text,
            statement_start_date,
            statement_end_date
        )

    @property
    def bank_name(self) -> str:
        """Get the bank name for this parser."""
        return self.config.bank_name

    @staticmethod
    def get_supported_banks() -> List[str]:
        """
        Get list of supported bank names.

        Returns:
            List of supported bank names
        """
        return ['halifax', 'hsbc', 'natwest', 'barclays', 'monzo', 'santander']
