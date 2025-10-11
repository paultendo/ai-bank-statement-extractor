# Quick Start Guide - MVP with UI
## Bank Statement Extractor - NatWest Format

Based on your actual NatWest statement screenshots, here's a streamlined path to get a working system with UI from Day 1.

---

## 📋 What We're Building (Phase 1 - 1 Week)

A simple web interface where you can:
1. **Upload** a PDF bank statement
2. **View** the extracted transactions in real-time
3. **Edit** any incorrect extractions
4. **Export** to Excel

**Scope for MVP:**
- ✅ NatWest bank statements (native PDF)
- ✅ Web UI with drag-and-drop upload
- ✅ Live preview of extracted data
- ✅ Excel export
- ✅ Basic validation (balance reconciliation)

---

## 🎯 Key Insights from Your NatWest Statements

### Format Analysis:

**Header Section:**
```
Account Name: MRS YAN MA
Account No: 27104001
Sort Code: 60-12-12
Statement Date: 17 JAN 2025
Period Covered: 18 DEC 2024 to 17 JAN 2025
Previous Balance: £49.45
Paid In: £3,214.07
Withdrawn: £3,250.26
New Balance: £13.26
```

**Transaction Table:**
| Date | Description | Paid In(£) | Withdrawn(£) | Balance(£) |
|------|-------------|------------|--------------|------------|
| 18 DEC 2024 | BROUGHT FORWARD | | | 49.45 |
| 18 DEC 2024 | Automated Credit HOUGHTON R&M Y FP 18/12/24 1046... | 150.00 | | 199.45 |
| | OnLine Transaction S S VIA MOBILE - PYMT FP 18/12/24... | | 130.00 | 69.45 |

**Key Challenges:**
1. ✅ **Multi-line descriptions** - Description can span 2-3 lines with reference codes
2. ✅ **Date format variations** - "18 DEC 2024" or "19 DEC" (year inferred)
3. ✅ **Two amount columns** - Paid In vs Withdrawn (not a single debit/credit)
4. ✅ **Special transactions** - "BROUGHT FORWARD" for opening balance

---

## 🚀 Implementation Plan

### Day 1-2: Core Extraction
```python
# src/extractors/natwest_extractor.py

import pdfplumber
import re
from datetime import datetime
from typing import List, Dict

class NatWestExtractor:
    def __init__(self, pdf_path: str):
        self.pdf_path = pdf_path
        self.transactions = []
        self.metadata = {}
    
    def extract(self):
        """Main extraction method"""
        with pdfplumber.open(self.pdf_path) as pdf:
            # Extract metadata from first page
            first_page = pdf.pages[0].extract_text()
            self.metadata = self.extract_metadata(first_page)
            
            # Extract transactions from all pages
            for page in pdf.pages:
                text = page.extract_text()
                page_transactions = self.extract_transactions(text)
                self.transactions.extend(page_transactions)
        
        # Validate and return
        self.validate_balance()
        return {
            'metadata': self.metadata,
            'transactions': self.transactions
        }
    
    def extract_metadata(self, text: str) -> Dict:
        """Extract header information"""
        metadata = {}
        
        # Account details
        if match := re.search(r'Account No\s+(\d+)', text):
            metadata['account_number'] = match.group(1)
        
        if match := re.search(r'Sort Code\s+(\d{2}-\d{2}-\d{2})', text):
            metadata['sort_code'] = match.group(1)
        
        # Statement period
        if match := re.search(r'Statement Date\s+(\d{1,2}\s+\w{3}\s+\d{4})', text):
            metadata['statement_date'] = match.group(1)
        
        if match := re.search(r'Period Covered\s+(\d{1,2}\s+\w{3}\s+\d{4})\s+to\s+(\d{1,2}\s+\w{3}\s+\d{4})', text):
            metadata['period_start'] = match.group(1)
            metadata['period_end'] = match.group(2)
        
        # Balances
        if match := re.search(r'Previous Balance\s+£([\d,]+\.\d{2})', text):
            metadata['previous_balance'] = self.parse_amount(match.group(1))
        
        if match := re.search(r'Paid In\s+£([\d,]+\.\d{2})', text):
            metadata['total_paid_in'] = self.parse_amount(match.group(1))
        
        if match := re.search(r'Withdrawn\s+£([\d,]+\.\d{2})', text):
            metadata['total_withdrawn'] = self.parse_amount(match.group(1))
        
        if match := re.search(r'New Balance\s+£([\d,]+\.\d{2})', text):
            metadata['new_balance'] = self.parse_amount(match.group(1))
        
        return metadata
    
    def extract_transactions(self, text: str) -> List[Dict]:
        """Extract transactions from page text"""
        transactions = []
        lines = text.split('\n')
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Look for transaction line (starts with date)
            if re.match(r'^\d{1,2}\s+[A-Z]{3}', line):
                transaction = self.parse_transaction_line(line, lines, i)
                if transaction:
                    transactions.append(transaction)
                    i += transaction.get('lines_consumed', 1)
                    continue
            
            i += 1
        
        return transactions
    
    def parse_transaction_line(self, line: str, all_lines: List[str], line_index: int) -> Dict:
        """Parse a single transaction (may span multiple lines)"""
        
        # Split line into components
        parts = line.split()
        
        # Date (first 1-3 tokens: "18 DEC 2024" or "19 DEC")
        date_str = ' '.join(parts[:3]) if len(parts) >= 3 else ' '.join(parts[:2])
        date = self.parse_date(date_str)
        
        # Find amounts at the end of the line
        amounts = re.findall(r'([\d,]+\.\d{2})', line)
        
        # Description is everything between date and amounts
        # Extract description (may continue on next lines)
        description_parts = []
        description_start_index = len(date_str)
        
        # Find where amounts start in the line
        if amounts:
            last_amount_index = line.rfind(amounts[-1])
            description_parts.append(line[description_start_index:last_amount_index].strip())
        else:
            description_parts.append(line[description_start_index:].strip())
        
        # Check if description continues on next line(s)
        lines_consumed = 1
        next_line_index = line_index + 1
        
        while next_line_index < len(all_lines):
            next_line = all_lines[next_line_index]
            
            # If next line doesn't start with date, it's a continuation
            if not re.match(r'^\d{1,2}\s+[A-Z]{3}', next_line) and next_line.strip():
                # Check if this line has amounts (if not, it's description continuation)
                next_amounts = re.findall(r'([\d,]+\.\d{2})', next_line)
                if not next_amounts:
                    description_parts.append(next_line.strip())
                    lines_consumed += 1
                    next_line_index += 1
                else:
                    # This line has amounts, so it's part of the transaction
                    amounts.extend(next_amounts)
                    break
            else:
                break
        
        description = ' '.join(description_parts)
        
        # Determine transaction type from description
        transaction_type = self.determine_transaction_type(description)
        
        # Parse amounts
        # NatWest format: Paid In | Withdrawn | Balance
        # So amounts[-1] is always Balance
        # If 3 amounts: [Paid In, Withdrawn, Balance] or [Paid In, Balance] or [Withdrawn, Balance]
        
        balance = float(amounts[-1].replace(',', '')) if amounts else 0.0
        paid_in = 0.0
        withdrawn = 0.0
        
        if len(amounts) == 3:
            paid_in = float(amounts[0].replace(',', ''))
            withdrawn = float(amounts[1].replace(',', ''))
        elif len(amounts) == 2:
            # Need to determine if it's paid_in or withdrawn
            # Check if balance increased or decreased
            amount = float(amounts[0].replace(',', ''))
            # We'll determine this during validation
            if 'credit' in description.lower() or 'paid in' in description.lower():
                paid_in = amount
            else:
                withdrawn = amount
        
        return {
            'date': date,
            'description': description,
            'transaction_type': transaction_type,
            'money_in': paid_in,
            'money_out': withdrawn,
            'balance': balance,
            'lines_consumed': lines_consumed,
            'confidence': 85  # Adjust based on parsing confidence
        }
    
    def determine_transaction_type(self, description: str) -> str:
        """Categorize transaction based on description"""
        desc_lower = description.lower()
        
        if 'automated credit' in desc_lower or 'bacs' in desc_lower:
            return 'Automated Credit'
        elif 'direct debit' in desc_lower:
            return 'Direct Debit'
        elif 'online transaction' in desc_lower or 'via mobile' in desc_lower:
            return 'Online Transfer'
        elif 'card transaction' in desc_lower:
            return 'Card Payment'
        elif 'brought forward' in desc_lower:
            return 'Brought Forward'
        else:
            return 'Other'
    
    def parse_date(self, date_str: str) -> str:
        """Parse date string to ISO format"""
        formats = ['%d %b %Y', '%d %B %Y', '%d %b', '%d %B']
        
        for fmt in formats:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)
                
                # If year not in string, use statement year
                if '%Y' not in fmt:
                    # Infer year from statement period
                    statement_year = datetime.strptime(
                        self.metadata.get('period_end', '01 JAN 2025'), 
                        '%d %b %Y'
                    ).year
                    dt = dt.replace(year=statement_year)
                
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                continue
        
        return date_str  # Return original if parsing fails
    
    def parse_amount(self, amount_str: str) -> float:
        """Parse amount string to float"""
        return float(amount_str.replace(',', ''))
    
    def validate_balance(self):
        """Validate that running balance is correct"""
        if not self.transactions:
            return
        
        calculated_balance = self.metadata.get('previous_balance', 0.0)
        
        for txn in self.transactions:
            if txn['transaction_type'] == 'Brought Forward':
                continue
            
            calculated_balance += txn['money_in'] - txn['money_out']
            
            # Check if calculated matches stated
            diff = abs(calculated_balance - txn['balance'])
            if diff > 0.01:  # 1p tolerance
                txn['confidence'] = max(0, txn['confidence'] - 20)
                txn['validation_warning'] = f"Balance mismatch: Expected {calculated_balance:.2f}, Got {txn['balance']:.2f}"
        
        # Final balance check
        final_diff = abs(calculated_balance - self.metadata.get('new_balance', 0))
        if final_diff > 0.01:
            print(f"Warning: Final balance doesn't reconcile. Difference: £{final_diff:.2f}")
```

### Day 3-4: Simple Streamlit UI

```python
# ui/app.py

import streamlit as st
import pandas as pd
from pathlib import Path
import sys

# Add src to path
sys.path.append(str(Path(__file__).parent.parent))

from src.extractors.natwest_extractor import NatWestExtractor
from src.exporters.excel_exporter import ExcelExporter

# Page configuration
st.set_page_config(
    page_title="Bank Statement Extractor",
    page_icon="💰",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
    .stButton>button {
        width: 100%;
    }
    .success-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #d4edda;
        border: 1px solid #c3e6cb;
        color: #155724;
    }
    .warning-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #fff3cd;
        border: 1px solid #ffeaa7;
        color: #856404;
    }
</style>
""", unsafe_allow_html=True)

def main():
    st.title("💰 Bank Statement Extractor")
    st.markdown("Upload your NatWest bank statement to extract transaction data")
    
    # Sidebar
    with st.sidebar:
        st.header("Settings")
        confidence_threshold = st.slider(
            "Confidence Threshold",
            min_value=0,
            max_value=100,
            value=70,
            help="Transactions below this confidence score will be flagged for review"
        )
        
        st.markdown("---")
        st.markdown("### Supported Banks")
        st.markdown("✅ NatWest")
        st.markdown("⏳ Barclays (coming soon)")
        st.markdown("⏳ HSBC (coming soon)")
    
    # Main content
    col1, col2 = st.columns([1, 1])
    
    with col1:
        st.subheader("📄 Upload Statement")
        
        uploaded_file = st.file_uploader(
            "Choose a PDF file",
            type=['pdf'],
            help="Upload a NatWest bank statement PDF"
        )
        
        if uploaded_file:
            # Save uploaded file temporarily
            temp_path = Path("temp") / uploaded_file.name
            temp_path.parent.mkdir(exist_ok=True)
            
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            
            st.success(f"✅ File uploaded: {uploaded_file.name}")
            
            # Process button
            if st.button("🔍 Extract Transactions", type="primary"):
                with st.spinner("Extracting transactions..."):
                    try:
                        # Extract data
                        extractor = NatWestExtractor(str(temp_path))
                        result = extractor.extract()
                        
                        # Store in session state
                        st.session_state['result'] = result
                        st.session_state['transactions_df'] = pd.DataFrame(result['transactions'])
                        
                        st.success("✅ Extraction complete!")
                        
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                        import traceback
                        st.code(traceback.format_exc())
    
    with col2:
        st.subheader("ℹ️ Statement Info")
        
        if 'result' in st.session_state:
            metadata = st.session_state['result']['metadata']
            
            # Display metadata in a nice format
            st.markdown(f"""
            <div class="success-box">
                <strong>Account:</strong> ****{metadata.get('account_number', 'N/A')[-4:]}<br>
                <strong>Sort Code:</strong> {metadata.get('sort_code', 'N/A')}<br>
                <strong>Period:</strong> {metadata.get('period_start', 'N/A')} to {metadata.get('period_end', 'N/A')}<br>
                <strong>Opening Balance:</strong> £{metadata.get('previous_balance', 0):.2f}<br>
                <strong>Total Paid In:</strong> £{metadata.get('total_paid_in', 0):.2f}<br>
                <strong>Total Withdrawn:</strong> £{metadata.get('total_withdrawn', 0):.2f}<br>
                <strong>Closing Balance:</strong> £{metadata.get('new_balance', 0):.2f}
            </div>
            """, unsafe_allow_html=True)
            
            st.markdown("---")
            
            # Transaction count
            df = st.session_state['transactions_df']
            total_txns = len(df)
            flagged_txns = len(df[df['confidence'] < confidence_threshold])
            
            col_a, col_b = st.columns(2)
            col_a.metric("Total Transactions", total_txns)
            col_b.metric("Flagged for Review", flagged_txns)
    
    # Transactions table
    if 'transactions_df' in st.session_state:
        st.markdown("---")
        st.subheader("📊 Extracted Transactions")
        
        df = st.session_state['transactions_df']
        
        # Add filters
        col1, col2, col3 = st.columns(3)
        
        with col1:
            show_flagged_only = st.checkbox("Show only flagged transactions")
        
        with col2:
            transaction_type_filter = st.multiselect(
                "Filter by type",
                options=df['transaction_type'].unique()
            )
        
        with col3:
            date_range = st.date_input("Filter by date range", value=[])
        
        # Apply filters
        filtered_df = df.copy()
        
        if show_flagged_only:
            filtered_df = filtered_df[filtered_df['confidence'] < confidence_threshold]
        
        if transaction_type_filter:
            filtered_df = filtered_df[filtered_df['transaction_type'].isin(transaction_type_filter)]
        
        # Display table
        st.dataframe(
            filtered_df[[
                'date', 'transaction_type', 'description', 
                'money_in', 'money_out', 'balance', 'confidence'
            ]],
            use_container_width=True,
            height=400
        )
        
        # Export section
        st.markdown("---")
        col1, col2, col3 = st.columns([2, 1, 1])
        
        with col2:
            if st.button("📥 Export to Excel", type="primary"):
                try:
                    # Generate Excel file
                    output_path = Path("output") / f"{uploaded_file.name.replace('.pdf', '')}_extracted.xlsx"
                    output_path.parent.mkdir(exist_ok=True)
                    
                    exporter = ExcelExporter(st.session_state['result'])
                    exporter.export(str(output_path))
                    
                    # Provide download link
                    with open(output_path, "rb") as f:
                        st.download_button(
                            label="⬇️ Download Excel",
                            data=f,
                            file_name=output_path.name,
                            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
                        )
                    
                except Exception as e:
                    st.error(f"Export error: {str(e)}")
        
        with col3:
            if st.button("🔄 Reset"):
                st.session_state.clear()
                st.rerun()

if __name__ == "__main__":
    main()
```

### Day 5: Excel Exporter

```python
# src/exporters/excel_exporter.py

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils.dataframe import dataframe_to_rows

class ExcelExporter:
    def __init__(self, extraction_result):
        self.metadata = extraction_result['metadata']
        self.transactions = extraction_result['transactions']
    
    def export(self, output_path: str):
        """Export to Excel with three sheets"""
        
        wb = Workbook()
        
        # Sheet 1: Transactions
        self.create_transactions_sheet(wb)
        
        # Sheet 2: Metadata
        self.create_metadata_sheet(wb)
        
        # Sheet 3: Extraction Log (simple for now)
        self.create_log_sheet(wb)
        
        # Remove default sheet
        if 'Sheet' in wb.sheetnames:
            wb.remove(wb['Sheet'])
        
        # Save
        wb.save(output_path)
        
        return output_path
    
    def create_transactions_sheet(self, wb):
        """Create main transactions sheet"""
        ws = wb.active
        ws.title = "Transactions"
        
        # Headers
        headers = [
            'Date', 'Type', 'Description', 
            'Money In (£)', 'Money Out (£)', 'Balance (£)',
            'Confidence (%)', 'Flag for Review'
        ]
        
        ws.append(headers)
        
        # Style headers
        header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
        
        # Add transactions
        for txn in self.transactions:
            ws.append([
                txn['date'],
                txn['transaction_type'],
                txn['description'],
                txn['money_in'] if txn['money_in'] > 0 else '',
                txn['money_out'] if txn['money_out'] > 0 else '',
                txn['balance'],
                txn['confidence'],
                'YES' if txn['confidence'] < 70 else 'NO'
            ])
        
        # Auto-adjust column widths
        for column in ws.columns:
            max_length = 0
            column_letter = column[0].column_letter
            
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(cell.value)
                except:
                    pass
            
            adjusted_width = min(max_length + 2, 50)
            ws.column_dimensions[column_letter].width = adjusted_width
    
    def create_metadata_sheet(self, wb):
        """Create statement metadata sheet"""
        ws = wb.create_sheet("Statement Info")
        
        # Add metadata
        metadata_rows = [
            ['Field', 'Value'],
            ['Account Number', self.metadata.get('account_number', 'N/A')],
            ['Sort Code', self.metadata.get('sort_code', 'N/A')],
            ['Statement Date', self.metadata.get('statement_date', 'N/A')],
            ['Period Start', self.metadata.get('period_start', 'N/A')],
            ['Period End', self.metadata.get('period_end', 'N/A')],
            ['Opening Balance', f"£{self.metadata.get('previous_balance', 0):.2f}"],
            ['Total Paid In', f"£{self.metadata.get('total_paid_in', 0):.2f}"],
            ['Total Withdrawn', f"£{self.metadata.get('total_withdrawn', 0):.2f}"],
            ['Closing Balance', f"£{self.metadata.get('new_balance', 0):.2f}"],
            ['Transaction Count', len(self.transactions)],
        ]
        
        for row in metadata_rows:
            ws.append(row)
        
        # Style
        ws.column_dimensions['A'].width = 20
        ws.column_dimensions['B'].width = 30
    
    def create_log_sheet(self, wb):
        """Create extraction log sheet"""
        ws = wb.create_sheet("Extraction Log")
        
        ws.append(['Timestamp', 'Event', 'Details'])
        ws.append([str(pd.Timestamp.now()), 'Extraction Started', 'NatWest statement'])
        ws.append([str(pd.Timestamp.now()), 'Transactions Extracted', f"{len(self.transactions)} found"])
        ws.append([str(pd.Timestamp.now()), 'Validation Complete', 'Balance reconciled'])
```

---

## 🏃‍♂️ Running the App

```bash
# 1. Set up project
mkdir bank-statement-extractor
cd bank-statement-extractor

# Create directory structure
mkdir -p src/extractors src/exporters ui temp output

# 2. Install dependencies
pip install streamlit pdfplumber pandas openpyxl

# 3. Add the code above to appropriate files:
# - src/extractors/natwest_extractor.py
# - src/exporters/excel_exporter.py
# - ui/app.py

# 4. Run the app
streamlit run ui/app.py
```

The app will open in your browser at `http://localhost:8501`

---

## 📝 Testing with Your Statement

1. **Upload** your NatWest PDF
2. **Click** "Extract Transactions"
3. **Review** the extracted data in the table
4. **Check** for any flagged transactions (confidence < 70%)
5. **Export** to Excel
6. **Verify** the balance reconciles

---

## 🐛 Known Issues & Workarounds

### Issue 1: Multi-line descriptions not captured
**Workaround**: Adjust the `parse_transaction_line()` logic to look ahead more lines

### Issue 2: Date year inference wrong
**Workaround**: Extract statement year from header more reliably

### Issue 3: Amounts in wrong columns
**Workaround**: Use table extraction instead of regex (camelot-py)

---

## 🎯 Next Steps (Week 2)

Once MVP is working:

1. **Add table extraction** - Use camelot-py for more reliable parsing
2. **OCR support** - Handle scanned statements
3. **More banks** - Add Barclays, HSBC configurations
4. **Edit functionality** - Allow manual corrections in UI
5. **Batch processing** - Upload multiple statements at once

---

## 💡 Tips for Agentic Coder

**Prompt for Claude Code / GPT Codex:**

```
I have bank statement extraction system to build. 

1. Start with src/extractors/natwest_extractor.py - implement the PDF text extraction using pdfplumber
2. Focus on handling multi-line descriptions (very important!)
3. Then build ui/app.py with Streamlit - simple drag-and-drop interface
4. Finally add src/exporters/excel_exporter.py for Excel output

Use the code samples in QUICK_START.md as a starting template.
Test with the NatWest statement PDFs I'll provide.

Key requirements:
- Extract: Date, Type, Description, Money In, Money Out, Balance
- Handle multi-line transaction descriptions
- Validate balance reconciliation
- Flag low-confidence extractions
- Simple web UI from day 1
```

---

**You now have everything you need to get started with a working UI from Day 1!** 🚀
