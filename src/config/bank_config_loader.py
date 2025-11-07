"""Load and manage bank-specific configurations."""
import logging
from pathlib import Path
from typing import Dict, Optional, List
import yaml

from .settings import BANK_TEMPLATES_DIR

logger = logging.getLogger(__name__)


class BankConfig:
    """Represents a bank-specific configuration."""

    def __init__(self, config_dict: dict, bank_name: str):
        """Initialize bank config from dictionary."""
        self.bank_name = bank_name
        self._config = config_dict

    @property
    def identifiers(self) -> List[str]:
        """Get list of bank identifier strings."""
        return self._config.get('identifiers', [])

    @property
    def header_patterns(self) -> Dict[str, str]:
        """Get regex patterns for header fields."""
        return self._config.get('header_patterns', {})

    @property
    def date_formats(self) -> List[str]:
        """Get list of date formats used by this bank."""
        return self._config.get('date_formats', [])

    @property
    def transaction_patterns(self) -> Dict[str, str]:
        """Get regex patterns for transaction parsing."""
        return self._config.get('transaction_patterns', {})

    @property
    def field_mapping(self) -> Dict[str, str]:
        """Get field name mappings to standardized names."""
        return self._config.get('field_mapping', {})

    @property
    def transaction_types(self) -> Dict[str, List[str]]:
        """Get transaction type keywords."""
        return self._config.get('transaction_types', {})

    @property
    def validation(self) -> Dict:
        """Get validation rules."""
        return self._config.get('validation', {})

    @property
    def balance_tolerance(self) -> float:
        """Get balance tolerance for reconciliation."""
        return self.validation.get('balance_tolerance', 0.01)

    @property
    def currency(self) -> str:
        """Get currency code (e.g., 'GBP', 'EUR', 'BRL')."""
        return self._config.get('currency', 'GBP')

    def get(self, key: str, default=None):
        """Get any config value by key."""
        return self._config.get(key, default)


class BankConfigLoader:
    """Loads and manages bank configurations."""

    def __init__(self, config_dir: Path = BANK_TEMPLATES_DIR):
        """
        Initialize config loader.

        Args:
            config_dir: Directory containing bank config YAML files
        """
        self.config_dir = config_dir
        self._configs: Dict[str, BankConfig] = {}
        self._load_all_configs()

    def _load_all_configs(self) -> None:
        """Load all bank configuration files."""
        if not self.config_dir.exists():
            logger.warning(f"Bank config directory not found: {self.config_dir}")
            return

        yaml_files = list(self.config_dir.glob("*.yaml")) + list(self.config_dir.glob("*.yml"))

        if not yaml_files:
            logger.warning(f"No bank config files found in {self.config_dir}")
            return

        for yaml_file in yaml_files:
            try:
                self._load_config(yaml_file)
            except Exception as e:
                logger.error(f"Failed to load config {yaml_file}: {e}")

        logger.info(f"Loaded {len(self._configs)} bank configurations")

    def _load_config(self, yaml_file: Path) -> None:
        """
        Load a single bank configuration file.

        Args:
            yaml_file: Path to YAML config file
        """
        with open(yaml_file, 'r', encoding='utf-8') as f:
            data = yaml.safe_load(f)

        # Each YAML file should have a top-level key with the bank name
        # e.g., natwest: {...}
        for bank_name, config_dict in data.items():
            if isinstance(config_dict, dict):
                self._configs[bank_name.lower()] = BankConfig(config_dict, bank_name)
                logger.debug(f"Loaded config for {bank_name}")

    def get_config(self, bank_name: str) -> Optional[BankConfig]:
        """
        Get configuration for a specific bank.

        Args:
            bank_name: Bank name (case-insensitive)

        Returns:
            BankConfig object or None if not found
        """
        return self._configs.get(bank_name.lower())

    def detect_bank(self, text: str) -> Optional[BankConfig]:
        """
        Detect bank from statement text using identifiers.

        Args:
            text: Extracted text from statement

        Returns:
            BankConfig object or None if bank cannot be detected
        """
        # Only check first 2000 characters (header/metadata section)
        # This prevents false matches on transaction descriptions
        # (e.g., transfers to "Santander" in an HSBC statement)
        header_text = text[:2000].lower()

        for bank_name, config in self._configs.items():
            for identifier in config.identifiers:
                if identifier.lower() in header_text:
                    logger.info(f"Detected bank: {bank_name}")
                    return config

        logger.warning("Could not detect bank from statement")
        return None

    def get_all_banks(self) -> List[str]:
        """Get list of all supported bank names."""
        return list(self._configs.keys())

    @property
    def supported_banks_count(self) -> int:
        """Get count of supported banks."""
        return len(self._configs)


# Singleton instance
_loader: Optional[BankConfigLoader] = None


def get_bank_config_loader() -> BankConfigLoader:
    """Get singleton instance of BankConfigLoader."""
    global _loader
    if _loader is None:
        _loader = BankConfigLoader()
    return _loader
