"""Regression tests for NatWest parser layout path."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from src.config import get_bank_config_loader
from src.extractors.pdf_extractor import PDFExtractor
from src.parsers.natwest_parser import NatWestParser


REPO_ROOT = Path(__file__).resolve().parents[2]
STATEMENTS_DIR = REPO_ROOT / "statements" / "Y Jones"


@pytest.fixture(scope="module")
def natwest_config():
    loader = get_bank_config_loader()
    config = loader.get_config("natwest")
    if config is None:
        pytest.skip("NatWest configuration not available")
    return config


def _period_from_filename(filename: str) -> tuple[datetime, datetime]:
    tail = Path(filename).stem.split("--")[-1]
    tokens = tail.split("-")
    if len(tokens) < 6:
        raise ValueError(f"Cannot parse period from {filename}")
    start = datetime(int(tokens[2]), int(tokens[1]), int(tokens[0]))
    end = datetime(int(tokens[5]), int(tokens[4]), int(tokens[3]))
    return start, end


def _parse_transactions(filename: str, config) -> list:
    file_path = STATEMENTS_DIR / filename
    extractor = PDFExtractor()
    text_kwargs = config.pdfplumber_text_kwargs
    text, _, layout = extractor.extract(
        file_path,
        capture_words=True,
        text_kwargs=text_kwargs
    )
    parser = NatWestParser(config)
    parser.set_word_layout(layout)
    start, end = _period_from_filename(filename)
    return parser.parse_transactions(text, start, end)


def test_natwest_layout_parser_handles_modern_statement(natwest_config):
    filename = "Statement--600923-89102398--10-04-2020-12-05-2020.pdf"
    transactions = _parse_transactions(filename, natwest_config)

    assert len(transactions) == 4
    assert transactions[0].description.startswith("BROUGHT FORWARD")
    assert transactions[1].money_out == pytest.approx(0.79, abs=0.01)
    assert transactions[2].money_in == pytest.approx(1000.0, abs=0.01)
    assert transactions[-1].balance == pytest.approx(1511.97, abs=0.01)


def test_natwest_layout_parser_handles_legacy_statement(natwest_config):
    filename = "Statement--600923-89102398--12-05-2018-12-06-2018.pdf"
    transactions = _parse_transactions(filename, natwest_config)

    # 2018 statement spans five pages and should include 50+ rows
    assert len(transactions) >= 50
    # First debit row should capture the JR-Heinemann transaction correctly
    assert transactions[1].money_out == pytest.approx(280.56, abs=0.01)
    assert "JR- HEINEMANN" in transactions[1].description


def test_natwest_layout_parser_handles_select_account_layout(natwest_config):
    filename = "Statement--600923-89102398--11-05-2024-12-06-2024.pdf"
    transactions = _parse_transactions(filename, natwest_config)

    assert len(transactions) == 4
    assert transactions[1].money_out == pytest.approx(18000.00, abs=0.01)
    assert transactions[-1].balance == pytest.approx(3318.54, abs=0.01)
