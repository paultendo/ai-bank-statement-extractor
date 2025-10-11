"""Smart date parsing for bank statements."""
import logging
from datetime import datetime
from typing import Optional, List
import re

try:
    from dateutil import parser as dateutil_parser
except ImportError:
    dateutil_parser = None

logger = logging.getLogger(__name__)


def parse_date(
    date_string: str,
    date_formats: Optional[List[str]] = None,
    reference_year: Optional[int] = None
) -> Optional[datetime]:
    """
    Parse date string using multiple strategies.

    Args:
        date_string: String containing date
        date_formats: List of strptime formats to try
        reference_year: Year to use if date doesn't include year

    Returns:
        datetime object or None if parsing fails
    """
    if not date_string or not isinstance(date_string, str):
        return None

    date_string = date_string.strip()

    if not date_string:
        return None

    # Default UK/European date formats
    if date_formats is None:
        date_formats = [
            "%d/%m/%Y",      # 01/12/2024
            "%d-%m-%Y",      # 01-12-2024
            "%d %b %Y",      # 01 Dec 2024
            "%d %B %Y",      # 01 December 2024
            "%d %b",         # 01 Dec (no year)
            "%d %B",         # 01 December (no year)
            "%Y-%m-%d",      # 2024-12-01 (ISO)
            "%d.%m.%Y",      # 01.12.2024
        ]

    # Try each format
    for fmt in date_formats:
        try:
            parsed = datetime.strptime(date_string, fmt)

            # If format doesn't include year, add reference year
            if '%Y' not in fmt and '%y' not in fmt:
                if reference_year:
                    parsed = parsed.replace(year=reference_year)
                else:
                    # Use current year as fallback
                    parsed = parsed.replace(year=datetime.now().year)

            return parsed

        except ValueError:
            continue

    # Try dateutil parser as fallback (more flexible but slower)
    if dateutil_parser:
        try:
            # dayfirst=True for UK/European date format preference
            parsed = dateutil_parser.parse(date_string, dayfirst=True)
            return parsed
        except (ValueError, TypeError):
            pass

    logger.warning(f"Could not parse date: {date_string}")
    return None


def infer_year_from_period(
    date_str: str,
    period_start: datetime,
    period_end: datetime
) -> Optional[datetime]:
    """
    Parse date and infer year from statement period with cross-year logic.

    Useful when dates in transactions don't include year.
    Handles cross-year scenarios (e.g., statement from Jan 2025 with Dec 2024 transactions).

    Based on Monopoly's cross-year logic:
    reference/monopoly/src/monopoly/pipeline.py:106-110

    Args:
        date_str: Date string (e.g., "01 Dec" or "28 DEC")
        period_start: Statement period start date
        period_end: Statement period end date

    Returns:
        datetime object with correct year

    Example:
        >>> # Statement period: 15 Dec 2024 - 05 Jan 2025
        >>> # Transaction: "28 DEC" -> Should be 28 Dec 2024
        >>> # Transaction: "02 JAN" -> Should be 02 Jan 2025
    """
    # Parse without year (will use current year as placeholder)
    parsed = parse_date(date_str)

    if not parsed:
        return None

    # Check if date string already contains a year
    has_year = bool(re.search(r'\d{4}', date_str))

    if has_year:
        # Year explicitly provided, use as-is
        return parsed

    # Start with statement start year as base
    base_year = period_start.year
    candidate = parsed.replace(year=base_year)

    # Try both years from period
    possible_years = [period_start.year, period_end.year]

    for year in set(possible_years):
        candidate = parsed.replace(year=year)

        # Check if date falls within period
        if period_start.date() <= candidate.date() <= period_end.date():
            return candidate

    # Cross-year detection (Monopoly pattern):
    # If statement is from early in the year (Jan/Feb) and transaction is from late year (Nov/Dec),
    # the transaction likely belongs to the previous year
    START_OF_YEAR_MONTHS = (1, 2)
    YEAR_CUTOFF_MONTH = 10  # Oct-Dec are "late year"

    if period_start.month in START_OF_YEAR_MONTHS and parsed.month >= YEAR_CUTOFF_MONTH:
        logger.debug(
            f"Cross-year detected: statement month={period_start.month}, "
            f"transaction month={parsed.month}, adjusting to previous year"
        )
        return parsed.replace(year=period_start.year - 1)

    # If no match and statement spans year boundary, check which year is closer
    if period_start.year != period_end.year:
        # Statement spans year boundary
        candidate_start_year = parsed.replace(year=period_start.year)
        candidate_end_year = parsed.replace(year=period_end.year)

        # Calculate days difference from period bounds
        days_from_start = abs((candidate_start_year.date() - period_start.date()).days)
        days_from_end = abs((candidate_end_year.date() - period_end.date()).days)

        if days_from_start < days_from_end:
            return candidate_start_year
        else:
            return candidate_end_year

    # Default: use the period start year
    return parsed.replace(year=period_start.year)


def normalize_date_string(date_str: str) -> str:
    """
    Normalize date string for consistent parsing.

    Args:
        date_str: Raw date string

    Returns:
        Normalized date string
    """
    # Remove extra whitespace
    normalized = ' '.join(date_str.split())

    # Normalize month abbreviations (remove periods)
    normalized = re.sub(r'(\w{3})\.', r'\1', normalized)

    return normalized
