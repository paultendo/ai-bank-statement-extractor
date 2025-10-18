#!/usr/bin/env python3
"""
Demo script showcasing the advanced analytics capabilities.
Designed for legal case analysis at Fifty Six Law.
"""

import sys
from pathlib import Path
import json

sys.path.insert(0, str(Path(__file__).parent))

from src.pipeline import ExtractionPipeline
from src.analytics import TransactionAnalyzer


def format_currency(amount):
    """Format currency with pound sign."""
    return f"£{amount:,.2f}"


def print_section(title):
    """Print formatted section header."""
    print(f"\n{'='*80}")
    print(f"{title:^80}")
    print(f"{'='*80}\n")


def demo_analytics(statement_path: str):
    """Run comprehensive analytics demo."""

    print_section("🏦 BANK STATEMENT ANALYTICS DEMO")
    print(f"Processing: {statement_path}\n")

    # Extract statement
    print("📄 Extracting statement...")
    pipeline = ExtractionPipeline()
    result = pipeline.process(Path(statement_path))

    if not result.transactions:
        print("❌ No transactions extracted. Exiting.")
        return

    print(f"✓ Extracted {len(result.transactions)} transactions")
    print(f"✓ Confidence: {result.confidence_score:.1f}%")
    print(f"✓ Balance reconciled: {result.balance_reconciled}")

    # Run analytics
    analyzer = TransactionAnalyzer(result.transactions)

    # 1. SUMMARY
    print_section("📊 FINANCIAL SUMMARY")
    summary = analyzer.get_summary()

    print(f"Statement Period: {summary['date_range']['start']} to {summary['date_range']['end']}")
    print(f"Duration: {summary['date_range']['days']} days")
    print(f"Total Transactions: {summary['total_transactions']}")
    print(f"\nOpening Balance: {format_currency(summary['opening_balance'])}")
    print(f"Closing Balance: {format_currency(summary['closing_balance'])}")
    print(f"Average Daily Balance: {format_currency(summary['avg_daily_balance'])}")
    print(f"\nTotal Income: {format_currency(summary['total_in'])}")
    print(f"Total Expenditure: {format_currency(summary['total_out'])}")
    print(f"Net Change: {format_currency(summary['net_change'])}")

    # 2. UNUSUAL SPENDING
    print_section("🚨 UNUSUAL SPENDING ANALYSIS")
    unusual = analyzer.detect_unusual_spending()

    if unusual:
        print(f"Found {len(unusual)} transactions significantly above average (3σ+)\n")
        print("Top 5 unusual transactions:")
        print("-" * 80)
        for i, txn in enumerate(unusual[:5], 1):
            print(f"\n{i}. Date: {txn['date']}")
            print(f"   Amount: {format_currency(txn['amount'])}")
            print(f"   Description: {txn['description']}")
            print(f"   Deviation: {txn['deviation_multiplier']:.1f}x above average")
            print(f"   Type: {txn['type']}")
            print(f"   Balance after: {format_currency(txn['balance_after'])}")
    else:
        print("✓ No unusual spending patterns detected")

    # 3. GAMBLING
    print_section("🎰 GAMBLING ACTIVITY")
    gambling = analyzer.analyze_gambling_activity()

    if gambling['detected']:
        print("⚠️  GAMBLING ACTIVITY DETECTED\n")
        print(f"Transaction Count: {gambling['transaction_count']}")
        print(f"Period: {gambling['date_range']['first']} to {gambling['date_range']['last']}")
        print(f"\nTotal Spent: {format_currency(gambling['total_spent'])}")
        print(f"Total Won: {format_currency(gambling['total_won'])}")
        print(f"Net Loss: {format_currency(gambling['net_loss'])}")
        print(f"Frequency: {gambling['frequency']:.2f} transactions per day")

        print("\nGambling Transactions:")
        print("-" * 80)
        for txn in gambling['transactions'][:10]:
            print(f"{txn['date']}: {txn['description']} - " +
                  f"Out: {format_currency(txn['money_out'])}, In: {format_currency(txn['money_in'])}")
    else:
        print("✓ No gambling activity detected")

    # 4. FRAUD INDICATORS
    print_section("🔍 FRAUD & COERCION INDICATORS")
    fraud = analyzer.detect_fraud_indicators()

    print("Rapid Large Transfers (multiple >£1k same day):")
    if fraud['rapid_large_transfers']:
        print(f"  ⚠️  {len(fraud['rapid_large_transfers'])} suspicious days detected")
        for event in fraud['rapid_large_transfers']:
            print(f"\n  {event['date']}: {event['count']} transfers, total {format_currency(event['total_amount'])}")
            for txn in event['transactions']:
                print(f"    • {txn['description']}: {format_currency(txn['amount'])}")
    else:
        print("  ✓ None detected")

    print(f"\nAccount Drain Events (>80% balance drop):")
    if fraud['account_drained']:
        print(f"  ⚠️  Account drain detected")
        for drain in fraud['drain_events']:
            print(f"    {drain['date']}: {drain['drop_percentage']:.1f}% drop")
            print(f"    Amount: {format_currency(drain['amount'])}")
            print(f"    Transaction: {drain['description']}")
    else:
        print("  ✓ None detected")

    print(f"\nTransfer Activity:")
    if fraud['unusual_transfer_activity']:
        print(f"  ⚠️  High frequency: {fraud['transfer_rate_per_day']:.1f} transfers/day")
    else:
        print("  ✓ Normal transfer activity")

    # Coercion indicators
    coercion = analyzer.detect_financial_coercion_patterns()

    print(f"\nSpending Pattern Changes:")
    if coercion['sudden_pattern_changes']:
        print(f"  ⚠️  Sudden pattern changes detected")
        for change in coercion['sudden_pattern_changes']:
            print(f"    • {change['description']}")
            print(f"      First half: {format_currency(change['first_half_avg'])}/txn")
            print(f"      Second half: {format_currency(change['second_half_avg'])}/txn")
            print(f"      Change: {change['change_percentage']:+.1f}%")
    else:
        print("  ✓ Consistent spending patterns")

    volatility = coercion['balance_volatility']
    volatility_status = "HIGH (>0.5)" if volatility > 0.5 else "Normal"
    print(f"\nBalance Volatility: {volatility:.2f} - {volatility_status}")

    # 5. LIFESTYLE ANALYSIS
    print_section("🛍️  LIFESTYLE SPENDING PROFILE")
    lifestyle = analyzer.analyze_lifestyle_spending()

    print(f"Categorized {lifestyle['categorized_percentage']:.1f}% of spending\n")
    print("Spending by Category:")
    print("-" * 80)

    for i, (category, data) in enumerate(lifestyle['categories'].items(), 1):
        avg_per_txn = data['total'] / data['count']
        print(f"{i:2}. {category.title():20} {format_currency(data['total']):>15} ({data['count']:3} txns, avg: {format_currency(avg_per_txn)})")

    # 6. INCOME ANALYSIS
    print_section("💰 INCOME ANALYSIS")
    income = analyzer.analyze_income_sources()

    print(f"Total Income: {format_currency(income['total_income'])}")
    print(f"Average Incoming Transaction: {format_currency(income['average_incoming'])}")
    print(f"Transaction Count: {income['transaction_count']}")
    print(f"Regular Income Streams Detected: {len(income['regular_income_streams'])}\n")

    print("Income by Type:")
    print("-" * 80)
    for itype, amount in income['by_type'].items():
        if amount > 0:
            pct = (amount / income['total_income'] * 100) if income['total_income'] > 0 else 0
            print(f"{itype.title():20} {format_currency(amount):>15} ({pct:5.1f}%)")

    if income['regular_income_streams']:
        print("\nRegular Income Streams:")
        print("-" * 80)
        for stream in income['regular_income_streams']:
            print(f"\n{stream['description']}")
            print(f"  Amount: {format_currency(stream['amount'])}")
            print(f"  Frequency: Every {stream['frequency_days']:.0f} days")
            print(f"  Occurrences: {stream['occurrences']}")
            print(f"  Total: {format_currency(stream['total'])}")
            print(f"  Period: {stream['first_date']} to {stream['last_date']}")

    # 7. MONTHLY BREAKDOWN
    print_section("📅 MONTHLY BREAKDOWN")
    monthly = analyzer.get_monthly_summary()

    print(f"{'Month':<15} {'Txns':>6} {'Money In':>15} {'Money Out':>15} {'Net':>15} {'Avg Balance':>15}")
    print("-" * 80)
    for month in monthly:
        print(f"{month['month']:<15} {month['transaction_count']:>6} " +
              f"{format_currency(month['total_in']):>15} " +
              f"{format_currency(month['total_out']):>15} " +
              f"{format_currency(month['net']):>15} " +
              f"{format_currency(month['avg_balance']):>15}")

    print_section("✅ ANALYTICS COMPLETE")
    print("\nThese insights are now available in the Streamlit UI at http://localhost:8501")
    print("\nFor legal cases, this analysis helps with:")
    print("  • Contentious probate (unusual spending, capacity assessment)")
    print("  • APP fraud claims (fraud indicators, rapid transfers)")
    print("  • Financial coercion detection (pattern changes, volatility)")
    print("  • Lifestyle/means assessments (spending categories, income sources)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        statement_path = sys.argv[1]
    else:
        # Use default test statement
        statement_path = "statements/05990425.pdf"

    try:
        demo_analytics(statement_path)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
