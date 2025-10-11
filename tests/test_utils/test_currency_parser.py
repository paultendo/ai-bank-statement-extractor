"""Tests for currency parser."""
import pytest
from src.utils.currency_parser import parse_currency, format_currency


class TestParseCurrency:
    """Test currency parsing."""

    def test_parse_basic_amount(self):
        """Test parsing basic numeric amount."""
        assert parse_currency("1234.56") == 1234.56

    def test_parse_with_pound_symbol(self):
        """Test parsing with £ symbol."""
        assert parse_currency("£1,234.56") == 1234.56

    def test_parse_with_dollar_symbol(self):
        """Test parsing with $ symbol."""
        assert parse_currency("$1,234.56") == 1234.56

    def test_parse_with_euro_symbol(self):
        """Test parsing with € symbol."""
        assert parse_currency("€1,234.56") == 1234.56

    def test_parse_with_thousands_separator(self):
        """Test parsing with comma thousands separator."""
        assert parse_currency("1,234,567.89") == 1234567.89

    def test_parse_negative_parentheses(self):
        """Test parsing negative amount with parentheses."""
        assert parse_currency("(1,234.56)") == -1234.56

    def test_parse_negative_with_minus(self):
        """Test parsing negative amount with minus sign."""
        assert parse_currency("-1234.56") == -1234.56

    def test_parse_with_cr_notation(self):
        """Test parsing with CR (credit) notation."""
        assert parse_currency("1234.56 CR") == -1234.56
        assert parse_currency("1234.56CR") == -1234.56

    def test_parse_with_db_notation(self):
        """Test parsing with DB (debit) notation."""
        assert parse_currency("1234.56 DB") == -1234.56

    def test_parse_empty_string(self):
        """Test parsing empty string."""
        assert parse_currency("") is None
        assert parse_currency("   ") is None

    def test_parse_none(self):
        """Test parsing None."""
        assert parse_currency(None) is None

    def test_parse_invalid_format(self):
        """Test parsing invalid format."""
        assert parse_currency("abc") is None
        assert parse_currency("£££") is None

    def test_parse_with_whitespace(self):
        """Test parsing with extra whitespace."""
        assert parse_currency("  £ 1,234.56  ") == 1234.56


class TestFormatCurrency:
    """Test currency formatting."""

    def test_format_basic_amount(self):
        """Test formatting basic amount."""
        assert format_currency(1234.56, "GBP") == "£1,234.56"

    def test_format_usd(self):
        """Test formatting USD."""
        assert format_currency(1234.56, "USD") == "$1,234.56"

    def test_format_euro(self):
        """Test formatting EUR."""
        assert format_currency(1234.56, "EUR") == "€1,234.56"

    def test_format_negative(self):
        """Test formatting negative amount."""
        assert format_currency(-1234.56, "GBP") == "-£1,234.56"

    def test_format_zero(self):
        """Test formatting zero."""
        assert format_currency(0, "GBP") == "£0.00"

    def test_format_large_amount(self):
        """Test formatting large amount with thousands separators."""
        assert format_currency(1234567.89, "GBP") == "£1,234,567.89"
