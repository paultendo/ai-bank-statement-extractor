"""
Bank Statement Extractor - Streamlit UI
Clean, minimal, professional design
"""

import streamlit as st
import pandas as pd
import sys
import os
from pathlib import Path
from datetime import datetime
from io import BytesIO

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.pipeline import ExtractionPipeline

# Page config
st.set_page_config(
    page_title="Bank Statement Extractor",
    page_icon="💎",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Minimal, clean CSS - work with Streamlit's default theme
st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Mono:wght@500;600&display=swap');

    * {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
    }

    .monospace {
        font-family: 'Space Mono', monospace !important;
    }

    h1, h2, h3 {
        font-weight: 700 !important;
        letter-spacing: -0.02em !important;
    }

    /* Buttons */
    .stButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1.5rem !important;
        transition: all 0.2s ease !important;
    }

    /* DataFrames */
    .dataframe {
        font-family: 'Space Mono', monospace !important;
        font-size: 0.9rem !important;
    }

    .dataframe thead tr th {
        font-weight: 600 !important;
        text-transform: uppercase !important;
        font-size: 0.75rem !important;
        letter-spacing: 0.05em !important;
        padding: 1rem !important;
        position: relative !important;
        z-index: 1 !important;
    }

    .dataframe tbody tr td {
        padding: 0.875rem 1rem !important;
    }

    /* Fix column sort dropdown visibility */
    [data-testid="stDataFrameResizable"] button {
        z-index: 100 !important;
        position: relative !important;
    }

    /* Fix dropdown menu positioning */
    .stDataFrame [role="menu"] {
        z-index: 1000 !important;
        background: white !important;
        box-shadow: 0 4px 12px rgba(0,0,0,0.15) !important;
    }

    /* Metrics */
    [data-testid="stMetricLabel"] {
        font-size: 0.875rem !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 0.05em !important;
    }

    [data-testid="stMetricValue"] {
        font-size: 1.75rem !important;
        font-weight: 700 !important;
    }

    /* File uploader */
    [data-testid="stFileUploader"] {
        border-radius: 12px !important;
        padding: 1.5rem !important;
    }

    /* Selectbox */
    .stSelectbox > div > div {
        border-radius: 8px !important;
    }

    /* Download buttons */
    .stDownloadButton>button {
        border-radius: 8px !important;
        font-weight: 600 !important;
        padding: 0.6rem 1.5rem !important;
    }

    /* Container spacing */
    .block-container {
        padding-top: 2rem !important;
        max-width: 1400px !important;
    }
    </style>
""", unsafe_allow_html=True)

# Session state
if 'extraction_result' not in st.session_state:
    st.session_state.extraction_result = None
if 'uploaded_file_data' not in st.session_state:
    st.session_state.uploaded_file_data = None

def format_currency(amount: float) -> str:
    if pd.isna(amount):
        return "-"
    return f"£{amount:,.2f}"

def main():
    # Header
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0 1.5rem 0;'>
            <h1 style='font-size: 3rem; margin-bottom: 0.5rem;'>
                💎 Bank Statement Extractor
            </h1>
            <p style='font-size: 1.1rem; opacity: 0.7;'>
                Automated data extraction for legal evidence
            </p>
        </div>
    """, unsafe_allow_html=True)

    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Configuration")

        supported_banks = [
            'Auto-detect', 'Barclays', 'HSBC', 'Lloyds', 'NatWest',
            'RBS', 'Santander', 'Nationwide', 'TSB', 'Monzo'
        ]

        selected_bank = st.selectbox("Bank", supported_banks)
        output_format = st.selectbox("Format", ['Excel (.xlsx)', 'CSV (.csv)'])

        st.markdown("---")
        st.markdown("### 🏦 Supported Banks")
        st.markdown(" · ".join(supported_banks[1:]))

        st.markdown("---")
        st.markdown("""
            ### 🔒 Privacy
            All processing is **100% local**.
            Your data never leaves this system.
        """)

    # Main content
    col1, col2 = st.columns([1, 1])

    with col1:
        st.markdown("### 📤 Upload Statement")
        uploaded_file = st.file_uploader(
            "Drag and drop or browse",
            type=['pdf', 'png', 'jpg', 'jpeg'],
            label_visibility="collapsed"
        )

        if uploaded_file:
            st.session_state.uploaded_file_data = uploaded_file.read()
            uploaded_file.seek(0)
            st.success(f"✅ **{uploaded_file.name}** ({len(st.session_state.uploaded_file_data) / 1024:.1f} KB)")

    with col2:
        st.markdown("### 🚀 Process")
        if uploaded_file:
            if st.button("🔍 Extract Data", use_container_width=True):
                temp_path = Path(f"/tmp/{uploaded_file.name}")
                with open(temp_path, "wb") as f:
                    f.write(st.session_state.uploaded_file_data)

                with st.spinner("Processing statement..."):
                    try:
                        pipeline = ExtractionPipeline()
                        bank_param = None if selected_bank == 'Auto-detect' else selected_bank.lower()
                        result = pipeline.process(temp_path, bank_name=bank_param)
                        st.session_state.extraction_result = result
                        st.success("✅ Extraction complete!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {str(e)}")
                    finally:
                        if os.path.exists(temp_path):
                            os.remove(temp_path)
        else:
            st.info("👆 Upload a statement file to begin")

    # Results
    if st.session_state.extraction_result:
        result = st.session_state.extraction_result

        st.markdown("---")
        st.markdown("## 📊 Extraction Results")

        # Metrics row
        cols = st.columns(4)

        with cols[0]:
            st.metric(
                "Bank Detected",
                result.statement.bank_name.upper() if result.statement.bank_name else 'Unknown'
            )

        with cols[1]:
            st.metric("Transactions", f"{len(result.transactions):,}")

        with cols[2]:
            confidence = result.confidence_score
            st.metric("Confidence", f"{confidence:.1f}%")

        with cols[3]:
            status = "✅ Reconciled" if result.balance_reconciled else "⚠️ Review"
            st.metric("Balance Check", status)

        # Statement details
        st.markdown("### 📋 Statement Details")
        detail_cols = st.columns(3)

        with detail_cols[0]:
            st.metric("Account", result.statement.account_number or "N/A")

        with detail_cols[1]:
            if result.statement.statement_start_date and result.statement.statement_end_date:
                period = f"{result.statement.statement_start_date.strftime('%d/%m/%Y')} - {result.statement.statement_end_date.strftime('%d/%m/%Y')}"
            else:
                period = "N/A"
            st.metric("Period", period)

        with detail_cols[2]:
            opening = format_currency(result.statement.opening_balance)
            closing = format_currency(result.statement.closing_balance)
            st.metric("Balance", f"{opening} → {closing}")

        # Transactions table
        st.markdown("### 💰 Transactions")

        with st.spinner("Loading transaction table..."):
            df_data = []
            for txn in result.transactions:
                df_data.append({
                    'Date': txn.date.strftime('%d/%m/%Y') if txn.date else '',
                    'Description': txn.description,
                    'Money In': txn.money_in if txn.money_in > 0 else None,
                    'Money Out': txn.money_out if txn.money_out > 0 else None,
                    'Balance': txn.balance,
                    'Type': txn.transaction_type.value if txn.transaction_type else '',
                    'Confidence': txn.confidence if txn.confidence else 0.0
                })

            df = pd.DataFrame(df_data)

            st.dataframe(
                df.style.format({
                    'Money In': lambda x: format_currency(x) if pd.notna(x) else '-',
                    'Money Out': lambda x: format_currency(x) if pd.notna(x) else '-',
                    'Balance': lambda x: format_currency(x) if pd.notna(x) else '-',
                    'Confidence': lambda x: f"{x:.1f}%" if pd.notna(x) and x > 0 else '-'
                }).background_gradient(
                    subset=['Confidence'],
                    cmap='RdYlGn',
                    vmin=70,
                    vmax=100
                ),
                use_container_width=True,
                height=400
            )

        # Summary statistics
        st.markdown("### 📈 Summary")
        sum_cols = st.columns(3)

        total_in = sum(txn.money_in for txn in result.transactions)
        total_out = sum(txn.money_out for txn in result.transactions)
        net = total_in - total_out

        with sum_cols[0]:
            st.metric("Total Money In", format_currency(total_in))

        with sum_cols[1]:
            st.metric("Total Money Out", format_currency(total_out))

        with sum_cols[2]:
            st.metric("Net Change", format_currency(net))

        # Warnings
        if result.warnings:
            st.markdown("### ⚠️ Validation Warnings")
            for msg in result.warnings:
                st.warning(msg)

        # Export section
        st.markdown("### 💾 Export Data")
        exp_cols = st.columns(2)

        with exp_cols[0]:
            # Generate Excel
            from openpyxl import Workbook
            from openpyxl.styles import Font, PatternFill, Alignment

            wb = Workbook()
            ws = wb.active
            ws.title = "Transactions"

            # Headers
            headers = ['Date', 'Description', 'Money In', 'Money Out', 'Balance', 'Type']
            for col, header in enumerate(headers, 1):
                cell = ws.cell(row=1, column=col, value=header)
                cell.font = Font(bold=True)
                cell.fill = PatternFill(start_color="667eea", end_color="667eea", fill_type="solid")
                cell.alignment = Alignment(horizontal="center")

            # Data
            for row, txn in enumerate(result.transactions, 2):
                ws.cell(row=row, column=1, value=txn.date.strftime('%d/%m/%Y') if txn.date else '')
                ws.cell(row=row, column=2, value=txn.description)
                ws.cell(row=row, column=3, value=txn.money_in if txn.money_in > 0 else None)
                ws.cell(row=row, column=4, value=txn.money_out if txn.money_out > 0 else None)
                ws.cell(row=row, column=5, value=txn.balance)
                ws.cell(row=row, column=6, value=txn.transaction_type.value if txn.transaction_type else '')

            # Column widths
            ws.column_dimensions['A'].width = 12
            ws.column_dimensions['B'].width = 50
            ws.column_dimensions['C'].width = 12
            ws.column_dimensions['D'].width = 12
            ws.column_dimensions['E'].width = 12
            ws.column_dimensions['F'].width = 20

            output = BytesIO()
            wb.save(output)

            timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
            bank_name = result.statement.bank_name or 'statement'

            st.download_button(
                "📥 Download Excel",
                data=output.getvalue(),
                file_name=f"{bank_name}_{timestamp}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )

        with exp_cols[1]:
            csv_data = df.to_csv(index=False)
            st.download_button(
                "📥 Download CSV",
                data=csv_data,
                file_name=f"{bank_name}_{timestamp}.csv",
                mime="text/csv",
                use_container_width=True
            )

    # Footer
    st.markdown("---")
    st.markdown("""
        <div style='text-align: center; padding: 2rem 0; opacity: 0.6;'>
            <p>Built for <strong>Fifty Six Law</strong> | Powered by AI & Python</p>
            <p style='font-size: 0.9rem;'>🔒 All processing is local. Your data never leaves this system.</p>
        </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
