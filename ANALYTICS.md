# Transaction Analytics for Legal Cases

## Overview

The Bank Statement Extractor now includes advanced analytics capabilities specifically designed for legal case analysis at Fifty Six Law. These analytics help identify patterns relevant to:

- **Contentious Probate Cases**: Unusual spending patterns, capacity assessments
- **APP Fraud Claims**: Fraud indicators, rapid transfers, account draining
- **Financial Coercion**: Pattern changes, volatility indicators
- **Lifestyle Assessments**: Spending categories, income analysis

## Features

### 1. Financial Overview

**Key Metrics:**
- Transaction count and period duration
- Opening, closing, and average daily balance
- Total income, expenditure, and net change
- Monthly breakdown with trend analysis

**Use Cases:**
- Quick snapshot of financial health
- Period-over-period comparisons
- Trend identification for court exhibits

---

### 2. Unusual Spending Detection

**What it Does:**
- Identifies transactions >3 standard deviations above average
- Flags potentially suspicious or uncharacteristic spending
- Calculates deviation multiplier for each transaction

**Legal Applications:**
- **Probate**: Detect suspicious withdrawals before death
- **Capacity**: Identify uncharacteristic spending patterns
- **Financial Abuse**: Flag unusual gifts or transfers

**Example Output:**
```
🚨 Found 1 unusual transaction
Date: 2023-03-06
Amount: £466.83
Description: NCC WEEKLY RENTS FIRST PAYMENT
Deviation: 7.7x above average
```

---

### 3. Gambling Activity Analysis

**Detection Includes:**
- Betting companies (Bet365, William Hill, Paddy Power, etc.)
- Online casinos
- Bingo sites
- Gaming platforms

**Metrics:**
- Total spent vs. total won
- Net loss calculation
- Frequency (transactions per day)
- Date range of activity

**Legal Applications:**
- **Probate**: Diminished capacity arguments
- **Divorce**: Asset dissipation
- **Vulnerability**: Gambling addiction evidence

**Example Output:**
```
⚠️  Gambling activity detected: 15 transactions
Total Spent: £2,450.00
Total Won: £180.00
Net Loss: £2,270.00
Frequency: 0.52 transactions/day
```

---

### 4. Fraud & Coercion Indicators

#### 4.1 Rapid Large Transfers
- Detects multiple transfers >£1,000 on the same day
- Common indicator of APP fraud or social engineering

#### 4.2 Account Drain Events
- Identifies >80% balance drops in single transactions
- Flags potential victim of fraud or coercion

#### 4.3 Unusual Transfer Activity
- Calculates transfer frequency
- Flags if >2 transfers per day on average

#### 4.4 Spending Pattern Changes
- Compares first half vs. second half of statement period
- Detects sudden changes in spending behavior
- May indicate loss of control or coercion

#### 4.5 Balance Volatility
- Measures standard deviation of account balance
- High volatility (>0.5) may indicate financial instability or manipulation

**Legal Applications:**
- **APP Fraud Claims**: Strong evidence for reimbursement
- **Financial Abuse**: Pattern of control or coercion
- **Elder Abuse**: Sudden changes after new relationship/caregiver

**Example Output:**
```
🚨 2 days with multiple large transfers (>£1,000)

2024-03-15: 3 transfers, total £8,500.00
  • TRANSFER TO J SMITH: £3,000.00
  • FASTER PAYMENT TO CRYPTO EXCHANGE: £5,000.00
  • TRANSFER TO UNKNOWN: £500.00

⚠️  Sudden spending pattern change detected
  First half avg: £45.23/txn
  Second half avg: £235.67/txn
  Change: +421.0%
```

---

### 5. Lifestyle Spending Analysis

**Categories Include:**
- Supermarkets (Tesco, Sainsbury's, Asda, etc.)
- Restaurants & takeaways
- Entertainment (Netflix, Sky, cinema, etc.)
- Travel (Uber, Trainline, airlines, hotels)
- Shopping (Amazon, ASOS, Next, etc.)
- Utilities (electric, gas, water, phone)
- Health (pharmacy, gym, dental)
- Insurance
- Cash withdrawals

**Metrics:**
- Total spending per category
- Transaction count
- Average per transaction
- Categorization percentage

**Legal Applications:**
- **Divorce**: Standard of living evidence
- **Estate Valuation**: Lifestyle before death
- **Means Assessments**: Income vs. expenditure analysis

**Example Output:**
```
✓ Categorized 78.5% of spending

Spending by Category:
1. Supermarkets: £845.23 (45 txns, avg: £18.78)
2. Utilities: £667.56 (4 txns, avg: £166.89)
3. Shopping: £456.78 (12 txns, avg: £38.07)
4. Restaurants: £234.56 (18 txns, avg: £13.03)
```

---

### 6. Income Analysis

**Detects:**
- Regular income streams (salary, pension, benefits)
- Income frequency and consistency
- Income source categorization

**Metrics:**
- Total income and average per transaction
- Income by type (Salary, Benefits, Transfers, Other)
- Regular income stream identification
- Frequency calculation (e.g., every 28 days)

**Legal Applications:**
- **Means Assessments**: Income verification
- **Employment Disputes**: Income pattern evidence
- **Estate Income**: Deceased's income sources

**Example Output:**
```
💰 Income Analysis
Total Income: £2,579.59
Regular Streams: 2

1. UNIVERSAL CREDIT: £350.00 every 28 days
   Occurrences: 4
   Total: £1,400.00
   Period: 2023-02-07 to 2023-03-06

2. STATE PENSION: £220.00 every 7 days
   Occurrences: 4
   Total: £880.00
```

---

### 7. Monthly Breakdown

**Provides:**
- Transaction count per month
- Money in, money out, net change
- Average balance per month
- Trend analysis across periods

**Legal Applications:**
- Court exhibits (visual timeline)
- Period comparisons for arguments
- Seasonal spending pattern identification

---

## Usage

### Command Line Demo

```bash
python3 demo_analytics.py statements/your_statement.pdf
```

### Streamlit UI

1. Start the UI:
```bash
streamlit run ui/streamlit_app.py --server.port 8501
```

2. Upload a statement
3. Click "Extract Data"
4. Scroll to "🔍 Advanced Analytics" section
5. Explore the 5 analytics tabs:
   - 📊 Overview
   - 🚨 Unusual Spending
   - 🎰 Gambling
   - 🔍 Fraud Indicators
   - 🛍️ Lifestyle

### Programmatic Usage

```python
from src.pipeline import ExtractionPipeline
from src.analytics import TransactionAnalyzer
from pathlib import Path

# Extract statement
pipeline = ExtractionPipeline()
result = pipeline.process(Path('statement.pdf'))

# Run analytics
analyzer = TransactionAnalyzer(result.transactions)

# Get specific analyses
unusual = analyzer.detect_unusual_spending()
gambling = analyzer.analyze_gambling_activity()
fraud = analyzer.detect_fraud_indicators()
lifestyle = analyzer.analyze_lifestyle_spending()
income = analyzer.analyze_income_sources()

# Or get comprehensive report
report = analyzer.generate_report()
```

---

## Analytics Confidence

All analytics respect the transaction confidence scores from extraction. Low-confidence transactions are included but should be manually verified before using in legal proceedings.

**Best Practice:**
- Review unusual spending detections manually
- Cross-reference fraud indicators with bank fraud reports
- Verify income streams against official documents
- Use analytics as supporting evidence, not sole evidence

---

## Performance

- **Processing Time**: <1 second for typical statements (100-500 transactions)
- **Large Statements**: ~2-3 seconds for 1000+ transactions
- **Memory Usage**: Minimal (<50MB per statement)

---

## Future Enhancements

Potential additions for future versions:

1. **Machine Learning Models**
   - Predict transaction categories with higher accuracy
   - Anomaly detection using unsupervised learning
   - Fraud risk scoring

2. **Comparative Analysis**
   - Compare multiple statements
   - Identify changes over time
   - Benchmark against similar cases

3. **Visualization**
   - Interactive charts (Plotly/Altair)
   - Spending heatmaps
   - Timeline visualizations

4. **Export**
   - PDF report generation
   - Word document with analysis
   - Court-ready exhibits

5. **Legal Templates**
   - Pre-formatted analysis for specific case types
   - Automated witness statement sections
   - Evidence bundle generation

---

## Technical Details

**File**: `src/analytics/transaction_analyzer.py`

**Key Methods:**
- `get_summary()`: Basic financial overview
- `detect_unusual_spending(threshold=3.0)`: Statistical outlier detection
- `analyze_gambling_activity()`: Keyword-based gambling detection
- `detect_fraud_indicators()`: Multi-factor fraud analysis
- `analyze_lifestyle_spending()`: Category-based spending breakdown
- `analyze_income_sources()`: Income pattern detection
- `detect_financial_coercion_patterns()`: Coercion indicator analysis
- `get_monthly_summary()`: Period-based aggregation
- `generate_report()`: Comprehensive analysis

**Dependencies:**
- pandas: Data manipulation
- numpy: Statistical calculations
- datetime: Date handling
- collections: Data structures

---

## Support

For questions or issues with analytics:
- Check [CLAUDE.md](CLAUDE.md) for technical context
- Review [BRIEF.md](BRIEF.md) for project requirements
- Open an issue on GitHub (if applicable)

---

**Built for Fifty Six Law**
*Advanced analytics for contentious probate and financial fraud cases*
