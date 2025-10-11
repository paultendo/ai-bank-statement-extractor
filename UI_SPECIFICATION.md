# UI Specification - Bank Statement Extractor
## Visual Design & Feature Requirements

---

## 🎨 Design Overview

**Framework**: Streamlit (Python-based web UI)  
**Theme**: Clean, professional, suitable for legal firm use  
**Colors**: Blue/Navy (trust, professionalism), Green (success), Amber (warnings)

---

## 📱 Main Interface Layout

```
┌─────────────────────────────────────────────────────────────────────┐
│  💰 Bank Statement Extractor                                   [⚙️] │
├─────────────────────────────────────────────────────────────────────┤
│ ┌─────────────────┐                                                 │
│ │   SIDEBAR       │  ┌──────────────────────────────────────────┐  │
│ │                 │  │  📄 Upload Statement                      │  │
│ │ Settings        │  │                                           │  │
│ │ ├─ Confidence   │  │  ┌───────────────────────────────────┐  │  │
│ │ │  Threshold    │  │  │  Drag & drop PDF here             │  │  │
│ │ │  [====|===]   │  │  │  or click to browse               │  │  │
│ │ │  70%          │  │  └───────────────────────────────────┘  │  │
│ │ │               │  │                                           │  │
│ │ └─ Banks        │  │  ✅ natwest_statement_jan2025.pdf        │  │
│ │    ✅ NatWest   │  │                                           │  │
│ │    ⏳ Barclays  │  │  [🔍 Extract Transactions]               │  │
│ │    ⏳ HSBC      │  └──────────────────────────────────────────┘  │
│ │                 │                                                 │
│ │ Help            │  ┌──────────────────────────────────────────┐  │
│ │ ├─ User Guide   │  │  ℹ️ Statement Info                       │  │
│ │ └─ Contact      │  │                                           │  │
│ │                 │  │  Account: ****4001                        │  │
│ └─────────────────┘  │  Sort Code: 60-12-12                      │  │
│                      │  Period: 18 DEC 2024 to 17 JAN 2025       │  │
│                      │  Opening: £49.45                           │  │
│                      │  Paid In: £3,214.07                        │  │
│                      │  Withdrawn: £3,250.26                      │  │
│                      │  Closing: £13.26                           │  │
│                      │                                           │  │
│                      │  📊 47 transactions  ⚠️ 3 flagged        │  │
│                      └──────────────────────────────────────────┘  │
├─────────────────────────────────────────────────────────────────────┤
│  📊 Extracted Transactions                                          │
│                                                                     │
│  Filters: [▢ Show flagged only] [Type: ▼] [Date: ▼]                │
│                                                                     │
│  ┌──────┬─────────────┬──────────────────┬──────────┬──────────┐  │
│  │ Date │ Type        │ Description      │ Money In │ Money Out│  │
│  ├──────┼─────────────┼──────────────────┼──────────┼──────────┤  │
│  │ 18/12│ Auto Credit │ HOUGHTON R&M Y...│ £150.00  │          │  │
│  │ 18/12│ Online      │ S S VIA MOBILE...│          │ £130.00  │  │
│  │ 19/12│ Auto Credit │ HOUGHTON FP...   │ £20.00   │          │  │
│  │ 19/12│ Online      │ ACC-NWESTMSTGL...│          │ £20.00   │  │
│  │⚠️20/12│ Auto Credit │ HOUGHTON R&M...  │ £100.00  │          │  │
│  │ ...  │ ...         │ ...              │ ...      │ ...      │  │
│  └──────┴─────────────┴──────────────────┴──────────┴──────────┘  │
│                                                                     │
│  [📥 Export to Excel]  [🔄 Reset]                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 🔑 Key Features

### 1. File Upload Area

**Location**: Top-left of main content area  
**Size**: Medium (approximately 400px wide)

**Features:**
- Drag-and-drop zone
- Click to browse file system
- Accept only `.pdf` files
- Display uploaded filename with checkmark
- Show file size
- Error message if wrong file type

**States:**
- Empty: "Drag & drop PDF here or click to browse"
- Hover: Blue border highlight
- File loaded: Green checkmark + filename
- Error: Red border + error message

**Code Example:**
```python
uploaded_file = st.file_uploader(
    "Choose a PDF file",
    type=['pdf'],
    help="Upload a NatWest bank statement PDF"
)

if uploaded_file:
    st.success(f"✅ {uploaded_file.name} ({uploaded_file.size / 1024:.1f} KB)")
```

---

### 2. Statement Info Panel

**Location**: Top-right of main content area  
**Size**: Medium (approximately 400px wide)  
**Background**: Light blue/grey (#F0F8FF)

**Display Fields:**
- Account number (masked: ****XXXX)
- Sort code (XX-XX-XX format)
- Statement period (dates)
- Opening balance
- Total paid in
- Total withdrawn
- Closing balance
- Transaction count
- Flagged count

**Visual Design:**
```python
st.markdown(f"""
<div style="background-color: #F0F8FF; padding: 1.5rem; border-radius: 8px; border: 1px solid #D1E7FF;">
    <h4 style="margin-top: 0;">📄 Statement Summary</h4>
    <table style="width: 100%;">
        <tr><td><strong>Account:</strong></td><td>****{account[-4:]}</td></tr>
        <tr><td><strong>Period:</strong></td><td>{start} to {end}</td></tr>
        <tr><td><strong>Opening:</strong></td><td style="color: #28a745;">£{opening:.2f}</td></tr>
        <tr><td><strong>Paid In:</strong></td><td style="color: #28a745;">£{paid_in:.2f}</td></tr>
        <tr><td><strong>Withdrawn:</strong></td><td style="color: #dc3545;">£{withdrawn:.2f}</td></tr>
        <tr><td><strong>Closing:</strong></td><td style="font-weight: bold;">£{closing:.2f}</td></tr>
    </table>
</div>
""", unsafe_allow_html=True)
```

---

### 3. Transaction Table

**Location**: Full-width below upload/info sections  
**Size**: Dynamic height (scrollable)

**Columns:**
1. **Date** (80px) - Format: DD/MM/YYYY or DD MMM
2. **Type** (120px) - Transaction category
3. **Description** (300px) - Full description, truncated with tooltip
4. **Money In** (100px) - Green text, right-aligned
5. **Money Out** (100px) - Red text, right-aligned
6. **Balance** (100px) - Bold, right-aligned
7. **Confidence** (80px) - Progress bar visualization
8. **Actions** (80px) - Edit/View icons

**Features:**
- **Sortable columns** (click header to sort)
- **Row highlighting**:
  - Low confidence (<70%): Light amber background
  - Balance mismatch: Light red background
  - Hover: Light blue background
- **Expandable rows**: Click to see full description
- **Inline editing**: Click to edit (future feature)
- **Row selection**: Checkbox for batch operations

**Visual Indicators:**
```python
def color_confidence(val):
    """Color code confidence scores"""
    if val < 50:
        color = '#dc3545'  # Red
    elif val < 70:
        color = '#ffc107'  # Amber
    else:
        color = '#28a745'  # Green
    return f'color: {color}; font-weight: bold'

# Apply styling
styled_df = df.style.applymap(color_confidence, subset=['confidence'])
st.dataframe(styled_df, use_container_width=True, height=500)
```

---

### 4. Filters & Search

**Location**: Above transaction table  
**Layout**: Horizontal row

**Filter Options:**

1. **Show Flagged Only** (Checkbox)
   - Toggle to display only transactions needing review
   - Icon: ⚠️

2. **Transaction Type** (Multi-select dropdown)
   - Options: All, Direct Debit, Card Payment, Online Transfer, Automated Credit, etc.
   - Multiple selection allowed

3. **Date Range** (Date picker)
   - Start date and end date inputs
   - Default: Full statement period

4. **Search Box** (Text input)
   - Search descriptions
   - Real-time filtering
   - Icon: 🔍

**Code Example:**
```python
col1, col2, col3, col4 = st.columns([1, 2, 2, 2])

with col1:
    show_flagged = st.checkbox("⚠️ Flagged only")

with col2:
    type_filter = st.multiselect(
        "Transaction Type",
        options=df['transaction_type'].unique(),
        default=[]
    )

with col3:
    date_from, date_to = st.date_input(
        "Date Range",
        value=[df['date'].min(), df['date'].max()]
    )

with col4:
    search_term = st.text_input("🔍 Search", "")
```

---

### 5. Action Buttons

**Location**: Below transaction table  
**Layout**: Right-aligned horizontal row

**Buttons:**

1. **📥 Export to Excel** (Primary action)
   - Blue background (#0066CC)
   - White text
   - Generates Excel file
   - Triggers download dialog
   - Shows success message

2. **📄 Export to CSV** (Secondary action)
   - Light blue background
   - Alternative export format

3. **🔄 Reset** (Tertiary action)
   - Grey background
   - Clears all data
   - Confirmation dialog: "Are you sure?"

**Code Example:**
```python
col1, col2, col3, col4 = st.columns([3, 1, 1, 1])

with col2:
    if st.button("📥 Export to Excel", type="primary"):
        # Generate Excel
        output_file = generate_excel(transactions, metadata)
        
        with open(output_file, "rb") as f:
            st.download_button(
                label="⬇️ Download",
                data=f,
                file_name="statement_extract.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )

with col3:
    if st.button("📄 CSV"):
        csv = df.to_csv(index=False)
        st.download_button("⬇️ Download", csv, "statement.csv", "text/csv")

with col4:
    if st.button("🔄 Reset"):
        if st.confirm("Clear all data?"):
            st.session_state.clear()
            st.rerun()
```

---

### 6. Sidebar Configuration

**Location**: Left sidebar (collapsible)  
**Width**: 280px

**Sections:**

**A. Settings**
```python
st.sidebar.header("⚙️ Settings")

confidence_threshold = st.sidebar.slider(
    "Confidence Threshold",
    min_value=0,
    max_value=100,
    value=70,
    step=5,
    help="Transactions below this score will be flagged"
)

auto_export = st.sidebar.checkbox(
    "Auto-export after extraction",
    value=False,
    help="Automatically generate Excel file"
)
```

**B. Supported Banks**
```python
st.sidebar.markdown("---")
st.sidebar.subheader("🏦 Supported Banks")
st.sidebar.markdown("✅ NatWest")
st.sidebar.markdown("⏳ Barclays (coming soon)")
st.sidebar.markdown("⏳ HSBC (coming soon)")
st.sidebar.markdown("⏳ Lloyds (coming soon)")
```

**C. Help & Support**
```python
st.sidebar.markdown("---")
st.sidebar.subheader("❓ Help")

with st.sidebar.expander("📖 User Guide"):
    st.markdown("""
    1. Upload your bank statement PDF
    2. Click "Extract Transactions"
    3. Review extracted data
    4. Edit if needed
    5. Export to Excel
    """)

with st.sidebar.expander("📧 Contact Support"):
    st.markdown("Email: support@fiftysixlaw.com")
    st.markdown("Phone: +44 XXX XXX XXXX")
```

---

## 🎨 Color Scheme

### Primary Colors
- **Primary Blue**: `#0066CC` (buttons, links)
- **Success Green**: `#28a745` (positive amounts, success messages)
- **Warning Amber**: `#ffc107` (flagged items, medium confidence)
- **Danger Red**: `#dc3545` (errors, negative amounts)

### Background Colors
- **Page Background**: `#FFFFFF` (white)
- **Panel Background**: `#F8F9FA` (light grey)
- **Info Box**: `#F0F8FF` (light blue)
- **Success Box**: `#D4EDDA` (light green)
- **Warning Box**: `#FFF3CD` (light yellow)
- **Error Box**: `#F8D7DA` (light red)

### Text Colors
- **Primary Text**: `#212529` (dark grey)
- **Secondary Text**: `#6C757D` (medium grey)
- **Link Text**: `#0066CC` (blue)

---

## 📊 Transaction Row States

### Visual Indicators

```python
def style_transaction_row(row):
    """Apply conditional styling to transaction rows"""
    styles = []
    
    # Low confidence - amber background
    if row['confidence'] < 50:
        styles.append('background-color: #FFF3CD')
    elif row['confidence'] < 70:
        styles.append('background-color: #FFF9E6')
    
    # Balance mismatch warning
    if 'validation_warning' in row and row['validation_warning']:
        styles.append('border-left: 4px solid #dc3545')
    
    return styles
```

**Row Examples:**

1. **Normal transaction** (confidence 85%+)
   - White background
   - No special indicators

2. **Medium confidence** (70-84%)
   - Very light amber background (#FFF9E6)
   - Small warning icon (⚡)

3. **Low confidence** (<70%)
   - Light amber background (#FFF3CD)
   - Warning icon (⚠️)
   - "Review Required" badge

4. **Balance mismatch**
   - Red left border (4px)
   - Error icon (❌)
   - Tooltip with details

---

## 🔔 Notifications & Feedback

### Success Messages
```python
st.success("✅ Statement extracted successfully! 47 transactions found.")
```

### Warning Messages
```python
st.warning("⚠️ 3 transactions flagged for manual review (confidence <70%)")
```

### Error Messages
```python
st.error("❌ Failed to extract statement. Please check the file format.")
```

### Info Messages
```python
st.info("ℹ️ Processing may take 30-60 seconds for large statements")
```

### Progress Indicators
```python
with st.spinner("🔍 Extracting transactions..."):
    # Long-running task
    time.sleep(2)

st.progress(0.75, text="Processing page 3 of 4...")
```

---

## 📱 Responsive Design Notes

Streamlit handles most responsiveness automatically, but consider:

1. **Column layouts** adapt to screen width
2. **Tables** scroll horizontally on small screens
3. **Sidebar** collapses on mobile
4. **Buttons** stack vertically on narrow screens

---

## 🔐 Data Privacy Indicators

Show users their data is safe:

```python
st.markdown("""
<div style="background-color: #E8F4F8; padding: 1rem; border-radius: 8px; margin-top: 2rem;">
    🔒 <strong>Your data is secure</strong><br>
    • All processing happens locally<br>
    • No data uploaded to cloud<br>
    • Files deleted after processing
</div>
""", unsafe_allow_html=True)
```

---

## ✨ Advanced Features (Future)

### Phase 2 Enhancements:

1. **Inline Editing**
   - Click cell to edit
   - Save changes
   - Recalculate balance

2. **Transaction Details Modal**
   - Click row to expand
   - Show full description
   - Display extraction confidence breakdown
   - Link to source page in PDF

3. **Batch Processing**
   - Upload multiple statements
   - Process queue
   - Consolidated export

4. **Comparison View**
   - Side-by-side original PDF and extracted data
   - Highlight extracted text in PDF

5. **Manual Correction Interface**
   - Split/merge transactions
   - Categorize manually
   - Add notes

---

## 🎯 Accessibility Considerations

1. **Keyboard Navigation**: All actions accessible via keyboard
2. **Screen Reader**: Proper ARIA labels
3. **Color Contrast**: WCAG AA compliant (4.5:1 minimum)
4. **Focus Indicators**: Clear visual focus states
5. **Error Messages**: Descriptive and actionable

---

## 🚀 Performance Targets

- **Page Load**: <2 seconds
- **File Upload**: <5 seconds for 50-page PDF
- **Extraction**: <30 seconds for typical statement
- **Export**: <3 seconds for Excel generation
- **UI Responsiveness**: No lag on interactions

---

## 📝 Implementation Checklist

### Phase 1 (Week 1):
- [x] Basic file upload component
- [x] Statement info display
- [x] Transaction table with sorting
- [x] Basic filters (flagged only)
- [x] Excel export button
- [x] Success/error notifications

### Phase 2 (Week 2-3):
- [ ] Advanced filters (type, date range, search)
- [ ] Confidence score visualization
- [ ] Inline editing capability
- [ ] Transaction detail modal
- [ ] CSV export option
- [ ] Better error handling

### Phase 3 (Future):
- [ ] Batch processing
- [ ] PDF preview side-by-side
- [ ] Manual correction tools
- [ ] Analytics dashboard
- [ ] Multi-user support with cases

---

**This UI spec ensures a professional, easy-to-use interface that legal staff can operate without technical knowledge!** 🎨
