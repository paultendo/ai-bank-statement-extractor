"""
Balance validation and reconciliation.

Ensures extracted transactions are mathematically correct.
Critical for legal evidence accuracy.
"""
import logging
from typing import Optional, Tuple
from dataclasses import dataclass

from ..models import Transaction, Statement

logger = logging.getLogger(__name__)


@dataclass
class ValidationResult:
    """Result of balance validation."""
    success: bool
    message: str
    failed_at_index: Optional[int] = None
    expected_balance: Optional[float] = None
    actual_balance: Optional[float] = None
    difference: Optional[float] = None


class BalanceValidator:
    """
    Validate transaction balances and reconcile with statement totals.

    Implements "safety check" pattern from Monopoly:
    - Validates each transaction balance
    - Reconciles opening/closing balances
    - Allows configurable tolerance for rounding
    """

    def __init__(self, tolerance: float = 0.01):
        """
        Initialize validator.

        Args:
            tolerance: Maximum allowed difference in pence/cents (default: 0.01 = 1p)
        """
        self.tolerance = tolerance

    def validate_transactions(
        self,
        transactions: list[Transaction],
        opening_balance: float
    ) -> ValidationResult:
        """
        Validate that all transaction balances reconcile.

        Each transaction's balance should equal:
        previous_balance + money_in - money_out

        Args:
            transactions: List of transactions in chronological order
            opening_balance: Starting balance

        Returns:
            ValidationResult with success status and details
        """
        if not transactions:
            return ValidationResult(
                success=False,
                message="No transactions to validate"
            )

        logger.info(f"Validating {len(transactions)} transactions")
        logger.debug(f"Opening balance: £{opening_balance:.2f}")

        calculated_balance = opening_balance

        for i, txn in enumerate(transactions):
            # Calculate expected balance
            calculated_balance += txn.money_in - txn.money_out

            # Check against stated balance
            difference = abs(calculated_balance - txn.balance)

            if difference > self.tolerance:
                error_msg = (
                    f"Balance mismatch at transaction {i+1} "
                    f"(date: {txn.date.strftime('%Y-%m-%d')}): "
                    f"Expected £{calculated_balance:.2f}, "
                    f"Got £{txn.balance:.2f}, "
                    f"Difference: £{difference:.2f}"
                )
                logger.error(error_msg)

                return ValidationResult(
                    success=False,
                    message=error_msg,
                    failed_at_index=i,
                    expected_balance=calculated_balance,
                    actual_balance=txn.balance,
                    difference=difference
                )

            logger.debug(
                f"Transaction {i+1}: {txn.description[:30]}... "
                f"Balance OK: £{txn.balance:.2f}"
            )

        success_msg = f"All {len(transactions)} transactions reconciled successfully"
        logger.info(success_msg)

        return ValidationResult(
            success=True,
            message=success_msg
        )

    def validate_statement_totals(
        self,
        statement: Statement,
        transactions: list[Transaction]
    ) -> ValidationResult:
        """
        Validate statement opening/closing balances match transactions.

        Checks:
        opening_balance + sum(money_in) - sum(money_out) = closing_balance

        Args:
            statement: Statement metadata with opening/closing balances
            transactions: List of transactions

        Returns:
            ValidationResult with success status and details
        """
        if not transactions:
            return ValidationResult(
                success=False,
                message="No transactions to validate"
            )

        logger.info("Validating statement totals")

        # Calculate totals
        total_in = sum(txn.money_in for txn in transactions)
        total_out = sum(txn.money_out for txn in transactions)

        calculated_closing = statement.opening_balance + total_in - total_out

        difference = abs(calculated_closing - statement.closing_balance)

        if difference > self.tolerance:
            error_msg = (
                f"Statement balance mismatch: "
                f"Opening £{statement.opening_balance:.2f} + "
                f"In £{total_in:.2f} - Out £{total_out:.2f} = "
                f"£{calculated_closing:.2f}, "
                f"but statement shows closing balance of £{statement.closing_balance:.2f}. "
                f"Difference: £{difference:.2f}"
            )
            logger.error(error_msg)

            return ValidationResult(
                success=False,
                message=error_msg,
                expected_balance=calculated_closing,
                actual_balance=statement.closing_balance,
                difference=difference
            )

        success_msg = (
            f"Statement totals reconciled: "
            f"£{statement.opening_balance:.2f} + £{total_in:.2f} - "
            f"£{total_out:.2f} = £{statement.closing_balance:.2f}"
        )
        logger.info(success_msg)

        return ValidationResult(
            success=True,
            message=success_msg
        )

    def perform_full_validation(
        self,
        statement: Statement,
        transactions: list[Transaction]
    ) -> Tuple[bool, list[str]]:
        """
        Perform complete validation (Monopoly's "safety check").

        Validates:
        1. Individual transaction balances
        2. Statement opening/closing totals

        Args:
            statement: Statement metadata
            transactions: List of transactions

        Returns:
            Tuple of (success: bool, messages: list[str])
        """
        logger.info("Performing full safety check")

        results = []
        all_passed = True

        # 1. Validate transaction balances
        txn_result = self.validate_transactions(
            transactions,
            statement.opening_balance
        )
        results.append(txn_result.message)
        if not txn_result.success:
            all_passed = False

        # 2. Validate statement totals
        total_result = self.validate_statement_totals(statement, transactions)
        results.append(total_result.message)
        if not total_result.success:
            all_passed = False

        if all_passed:
            logger.info("✓ Safety check PASSED")
        else:
            logger.error("✗ Safety check FAILED")

        return all_passed, results


def calculate_running_balance(
    transactions: list[Transaction],
    opening_balance: float
) -> list[Transaction]:
    """
    Calculate running balance for transactions that don't have balance field.

    Useful for statements that only show final balance.

    Args:
        transactions: List of transactions (may have balance=0)
        opening_balance: Starting balance

    Returns:
        List of transactions with calculated balances
    """
    logger.info("Calculating running balances")

    running_balance = opening_balance

    for txn in transactions:
        if txn.balance == 0.0:
            # Calculate balance
            running_balance += txn.money_in - txn.money_out
            txn.balance = running_balance
            logger.debug(
                f"Calculated balance for {txn.description[:30]}...: "
                f"£{txn.balance:.2f}"
            )

    return transactions
