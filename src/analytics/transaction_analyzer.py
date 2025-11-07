"""Transaction analytics for legal case analysis."""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
from collections import defaultdict
import re

from ..models.transaction import Transaction, TransactionType


class TransactionAnalyzer:
    """
    Analyzes bank transactions for patterns relevant to legal cases.

    Particularly useful for:
    - Contentious probate (unusual spending patterns)
    - APP fraud reimbursement claims (fraud indicators)
    - Financial coercion detection
    - Lifestyle analysis
    """

    def __init__(self, transactions: List[Transaction]):
        """Initialize analyzer with transaction list."""
        self.transactions = transactions

        if not transactions:
            raise ValueError("Cannot analyze empty transaction list")

        self.df = self._to_dataframe()

    def _to_dataframe(self) -> pd.DataFrame:
        """Convert transactions to pandas DataFrame."""
        data = []
        for txn in self.transactions:
            data.append({
                'date': txn.date,
                'description': txn.description,
                'money_in': txn.money_in,
                'money_out': txn.money_out,
                'balance': txn.balance,
                'type': txn.transaction_type.value if txn.transaction_type else 'Other',
                'confidence': txn.confidence
            })

        df = pd.DataFrame(data)
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        return df

    def get_summary(self) -> Dict:
        """Get basic transaction summary."""
        return {
            'total_transactions': len(self.df),
            'date_range': {
                'start': self.df['date'].min().strftime('%Y-%m-%d'),
                'end': self.df['date'].max().strftime('%Y-%m-%d'),
                'days': (self.df['date'].max() - self.df['date'].min()).days
            },
            'total_in': float(self.df['money_in'].sum()),
            'total_out': float(self.df['money_out'].sum()),
            'net_change': float(self.df['money_in'].sum() - self.df['money_out'].sum()),
            'opening_balance': float(self.df['balance'].iloc[0] - self.df['money_in'].iloc[0] + self.df['money_out'].iloc[0]),
            'closing_balance': float(self.df['balance'].iloc[-1]),
            'avg_daily_balance': float(self.df['balance'].mean())
        }

    def detect_unusual_spending(self, threshold_multiplier: float = 3.0) -> List[Dict]:
        """
        Detect transactions that are unusually large.

        Useful for probate cases to identify:
        - Suspicious withdrawals before death
        - Unusual gifts or transfers
        - Uncharacteristic spending

        Args:
            threshold_multiplier: How many standard deviations above mean

        Returns:
            List of unusual transactions with context
        """
        # Calculate spending statistics (exclude £0 transactions)
        spending = self.df[self.df['money_out'] > 0]['money_out']
        mean_spend = spending.mean()
        std_spend = spending.std()
        threshold = mean_spend + (threshold_multiplier * std_spend)

        unusual = self.df[self.df['money_out'] > threshold].copy()
        unusual['deviation_from_mean'] = (unusual['money_out'] - mean_spend) / std_spend

        results = []
        for _, row in unusual.iterrows():
            results.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'description': row['description'],
                'amount': float(row['money_out']),
                'mean_spending': float(mean_spend),
                'deviation_multiplier': float(row['deviation_from_mean']),
                'balance_after': float(row['balance']),
                'type': row['type']
            })

        return sorted(results, key=lambda x: x['amount'], reverse=True)

    def analyze_gambling_activity(self) -> Dict:
        """
        Detect gambling transactions.

        Relevant for:
        - Probate cases (diminished capacity arguments)
        - Divorce/financial settlements
        - Vulnerability assessments
        """
        gambling_keywords = [
            'bet', 'betting', 'casino', 'poker', 'slots', 'ladbrokes',
            'william hill', 'paddy power', 'coral', 'skybet', 'betfair',
            'gala', 'gamble', 'bingo', 'jackpot', 'roulette', 'flutter',
            'betway', '888', 'unibet', 'matchbook', 'spreadex'
        ]

        pattern = '|'.join(gambling_keywords)
        gambling_df = self.df[
            self.df['description'].str.lower().str.contains(pattern, na=False)
        ]

        if len(gambling_df) == 0:
            return {
                'detected': False,
                'total_amount': 0,
                'transaction_count': 0,
                'transactions': []
            }

        transactions = []
        for _, row in gambling_df.iterrows():
            transactions.append({
                'date': row['date'].strftime('%Y-%m-%d'),
                'description': row['description'],
                'money_out': float(row['money_out']),
                'money_in': float(row['money_in'])
            })

        return {
            'detected': True,
            'total_spent': float(gambling_df['money_out'].sum()),
            'total_won': float(gambling_df['money_in'].sum()),
            'net_loss': float(gambling_df['money_out'].sum() - gambling_df['money_in'].sum()),
            'transaction_count': len(gambling_df),
            'date_range': {
                'first': gambling_df['date'].min().strftime('%Y-%m-%d'),
                'last': gambling_df['date'].max().strftime('%Y-%m-%d')
            },
            'frequency': len(gambling_df) / ((self.df['date'].max() - self.df['date'].min()).days + 1),
            'transactions': transactions
        }

    def detect_fraud_indicators(self) -> Dict:
        """
        Identify potential fraud indicators for APP claims.

        Looks for:
        - Rapid succession of large transfers
        - Unusual payees
        - Account being drained
        - Multiple failed transactions
        """
        indicators = {
            'rapid_large_transfers': [],
            'account_drained': False,
            'unusual_transfer_activity': False,
            'suspicious_patterns': []
        }

        # 1. Detect rapid succession of transfers (multiple large transfers same day)
        daily_transfers = self.df[
            (self.df['type'] == 'Transfer') & (self.df['money_out'] > 1000)
        ].groupby(self.df['date'].dt.date)

        for date, group in daily_transfers:
            if len(group) >= 2:
                indicators['rapid_large_transfers'].append({
                    'date': str(date),
                    'count': len(group),
                    'total_amount': float(group['money_out'].sum()),
                    'transactions': [
                        {
                            'description': row['description'],
                            'amount': float(row['money_out'])
                        }
                        for _, row in group.iterrows()
                    ]
                })

        # 2. Check if account was drained (balance dropped >80% suddenly)
        if len(self.df) > 1:
            max_balance = self.df['balance'].max()
            balance_drops = []

            for i in range(1, len(self.df)):
                prev_balance = self.df.iloc[i-1]['balance']
                curr_balance = self.df.iloc[i]['balance']

                if prev_balance > 0:
                    drop_pct = ((prev_balance - curr_balance) / prev_balance) * 100
                    if drop_pct > 80:
                        balance_drops.append({
                            'date': self.df.iloc[i]['date'].strftime('%Y-%m-%d'),
                            'drop_percentage': float(drop_pct),
                            'amount': float(prev_balance - curr_balance),
                            'description': self.df.iloc[i]['description']
                        })

            if balance_drops:
                indicators['account_drained'] = True
                indicators['drain_events'] = balance_drops

        # 3. Unusual transfer frequency
        transfers = self.df[self.df['type'] == 'Transfer']
        if len(transfers) > 0:
            days_span = (self.df['date'].max() - self.df['date'].min()).days + 1
            transfer_rate = len(transfers) / days_span

            # If more than 2 transfers per day on average, flag it
            if transfer_rate > 2:
                indicators['unusual_transfer_activity'] = True
                indicators['transfer_rate_per_day'] = float(transfer_rate)

        return indicators

    def analyze_lifestyle_spending(self) -> Dict:
        """
        Categorize spending to build lifestyle profile.

        Useful for:
        - Divorce settlements (standard of living)
        - Estate valuations (lifestyle before death)
        - Capacity assessments
        """
        categories = {
            'supermarkets': ['tesco', 'sainsbury', 'asda', 'morrisons', 'waitrose', 'aldi', 'lidl', 'marks & spencer', 'co-op', 'iceland'],
            'restaurants': ['restaurant', 'cafe', 'pizza', 'nando', 'mcdonald', 'kfc', 'burger', 'subway', 'starbucks', 'costa', 'pret'],
            'entertainment': ['cinema', 'theatre', 'netflix', 'spotify', 'amazon prime', 'disney', 'sky', 'apple music', 'xbox', 'playstation', 'steam'],
            'travel': ['trainline', 'uber', 'lyft', 'ryanair', 'easyjet', 'british airways', 'booking.com', 'airbnb', 'hotel', 'parking'],
            'shopping': ['amazon', 'ebay', 'argos', 'john lewis', 'next', 'zara', 'h&m', 'asos', 'primark', 'tkmaxx'],
            'utilities': ['electric', 'gas', 'water', 'council tax', 'broadband', 'phone', 'bt', 'virgin', 'vodafone', 'ee', 'three'],
            'health': ['pharmacy', 'boots', 'superdrug', 'hospital', 'dental', 'optician', 'gym', 'fitness', 'spa'],
            'insurance': ['insurance', 'aviva', 'axa', 'churchill', 'direct line', 'admiral', 'hastings'],
            'transfers': ['transfer', 'payment to'],
            'cash': ['cash', 'atm', 'withdrawal']
        }

        categorized = defaultdict(lambda: {'count': 0, 'total': 0.0, 'transactions': []})
        uncategorized = []

        for _, row in self.df.iterrows():
            desc_lower = row['description'].lower()
            amount = float(row['money_out'])

            if amount == 0:
                continue

            matched = False
            for category, keywords in categories.items():
                if any(keyword in desc_lower for keyword in keywords):
                    categorized[category]['count'] += 1
                    categorized[category]['total'] += amount
                    categorized[category]['transactions'].append({
                        'date': row['date'].strftime('%Y-%m-%d'),
                        'description': row['description'],
                        'amount': amount
                    })
                    matched = True
                    break

            if not matched:
                uncategorized.append({
                    'date': row['date'].strftime('%Y-%m-%d'),
                    'description': row['description'],
                    'amount': amount
                })

        # Sort by total spending
        sorted_categories = {
            k: v for k, v in sorted(
                categorized.items(),
                key=lambda item: item[1]['total'],
                reverse=True
            )
        }

        total_spending = self.df['money_out'].sum()

        return {
            'categories': dict(sorted_categories),
            'uncategorized': uncategorized[:20],  # Top 20 only
            'total_spending': float(total_spending),
            'categorized_percentage': float((sum(c['total'] for c in categorized.values()) / total_spending * 100) if total_spending > 0 else 0)
        }

    def analyze_income_sources(self) -> Dict:
        """
        Analyze income sources and regularity.

        Useful for:
        - Means assessments
        - Employment disputes
        - Estate income analysis
        """
        income_df = self.df[self.df['money_in'] > 0].copy()

        # Detect regular income (same amount, regular intervals)
        regular_income = []
        grouped = income_df.groupby('description')

        for desc, group in grouped:
            if len(group) >= 2:
                amounts = group['money_in'].values
                # Check if amounts are similar (within 5%)
                if amounts.std() / amounts.mean() < 0.05:
                    # Calculate average interval
                    dates = group['date'].sort_values()
                    intervals = dates.diff().dropna()
                    avg_interval = intervals.mean()

                    regular_income.append({
                        'description': desc,
                        'amount': float(amounts.mean()),
                        'frequency_days': float(avg_interval.days),
                        'occurrences': len(group),
                        'total': float(group['money_in'].sum()),
                        'first_date': dates.iloc[0].strftime('%Y-%m-%d'),
                        'last_date': dates.iloc[-1].strftime('%Y-%m-%d')
                    })

        # Categorize income types
        salary_keywords = ['salary', 'wage', 'pay', 'payroll', 'employer']
        benefits_keywords = ['universal credit', 'benefit', 'pension', 'dwp', 'hmrc', 'tax credit']
        transfer_keywords = ['transfer', 'payment from']

        income_sources = {
            'salary': income_df[income_df['description'].str.lower().str.contains('|'.join(salary_keywords), na=False)],
            'benefits': income_df[income_df['description'].str.lower().str.contains('|'.join(benefits_keywords), na=False)],
            'transfers': income_df[income_df['description'].str.lower().str.contains('|'.join(transfer_keywords), na=False)]
        }

        return {
            'total_income': float(income_df['money_in'].sum()),
            'transaction_count': len(income_df),
            'average_incoming': float(income_df['money_in'].mean()),
            'regular_income_streams': regular_income,
            'by_type': {
                'salary': float(income_sources['salary']['money_in'].sum()),
                'benefits': float(income_sources['benefits']['money_in'].sum()),
                'transfers': float(income_sources['transfers']['money_in'].sum()),
                'other': float(income_df['money_in'].sum() - sum(v['money_in'].sum() for v in income_sources.values()))
            }
        }

    def detect_financial_coercion_patterns(self) -> Dict:
        """
        Identify patterns that may indicate financial coercion or abuse.

        Looks for:
        - Sudden changes in spending patterns
        - Unusual beneficiaries appearing
        - Account control changes
        """
        indicators = {
            'sudden_pattern_changes': [],
            'new_regular_beneficiaries': [],
            'balance_volatility': 0.0
        }

        # 1. Detect sudden pattern changes (compare first half vs second half)
        midpoint = len(self.df) // 2
        first_half = self.df.iloc[:midpoint]
        second_half = self.df.iloc[midpoint:]

        if len(first_half) > 0 and len(second_half) > 0:
            first_avg_out = first_half['money_out'].mean()
            second_avg_out = second_half['money_out'].mean()

            if first_avg_out > 0:
                change_pct = ((second_avg_out - first_avg_out) / first_avg_out) * 100

                if abs(change_pct) > 50:  # 50% change in spending pattern
                    indicators['sudden_pattern_changes'].append({
                        'description': 'Average spending changed significantly',
                        'first_half_avg': float(first_avg_out),
                        'second_half_avg': float(second_avg_out),
                        'change_percentage': float(change_pct)
                    })

        # 2. Balance volatility (high volatility may indicate loss of control)
        balance_std = self.df['balance'].std()
        balance_mean = self.df['balance'].mean()

        if balance_mean > 0:
            indicators['balance_volatility'] = float(balance_std / balance_mean)

        return indicators

    def get_monthly_summary(self) -> List[Dict]:
        """
        Get month-by-month breakdown.

        Useful for:
        - Long-term trend analysis
        - Period comparisons
        - Court timeline exhibits
        """
        self.df['year_month'] = self.df['date'].dt.to_period('M')
        monthly = self.df.groupby('year_month')

        summaries = []
        for period, group in monthly:
            summaries.append({
                'month': str(period),
                'transaction_count': len(group),
                'total_in': float(group['money_in'].sum()),
                'total_out': float(group['money_out'].sum()),
                'net': float(group['money_in'].sum() - group['money_out'].sum()),
                'opening_balance': float(group['balance'].iloc[0]),
                'closing_balance': float(group['balance'].iloc[-1]),
                'avg_balance': float(group['balance'].mean())
            })

        return summaries

    def generate_report(self) -> Dict:
        """
        Generate comprehensive analysis report.

        Returns:
            Complete analysis suitable for legal review
        """
        return {
            'summary': self.get_summary(),
            'unusual_spending': self.detect_unusual_spending(),
            'gambling': self.analyze_gambling_activity(),
            'fraud_indicators': self.detect_fraud_indicators(),
            'lifestyle': self.analyze_lifestyle_spending(),
            'income': self.analyze_income_sources(),
            'coercion_indicators': self.detect_financial_coercion_patterns(),
            'monthly_breakdown': self.get_monthly_summary()
        }
