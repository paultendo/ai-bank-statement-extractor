# 🏦 Bank Statement Extractor - UI Guide

## Quick Start

### Launch the Application

**Option 1: Using the launch script (recommended)**
```bash
./run_ui.sh
```

**Option 2: Manual launch**
```bash
streamlit run ui/streamlit_app.py
```

The app will open automatically in your browser at: **http://localhost:8501**

---

## Using the Application

### 1. Upload a Statement 📤

1. Click **"Browse files"** or drag & drop a statement
2. Supported formats: PDF, PNG, JPG, JPEG
3. File size limit: 50MB

### 2. Select Bank (Optional) 🏦

- **Auto-detect (recommended)**: Let the system identify the bank automatically
- **Manual selection**: Choose from dropdown if you know the bank

Supported banks:
- Barclays
- HSBC
- Lloyds
- NatWest
- RBS
- Santander
- Nationwide
- TSB
- Monzo

### 3. Process Statement 🚀

1. Click **"Extract Data"** button
2. Wait for processing (typically 2-10 seconds)
3. Review the results

### 4. Review Results 📊

**Metrics Dashboard:**
- **Bank Detected**: Auto-identified bank name
- **Transactions**: Number of transactions extracted
- **Confidence**: Extraction accuracy score (aim for >90%)
- **Balance Check**: ✅ Pass or ⚠️ Review

**Transaction Table:**
- View all extracted transactions
- Sortable and searchable
- Color-coded confidence scores

**Summary Statistics:**
- Total Money In
- Total Money Out
- Net Change

### 5. Export Data 💾

**Excel Export:**
- Professional formatting
- Ready for court evidence
- Includes all transaction details

**CSV Export:**
- Plain text format
- Easy to import into other systems

---

## Understanding the Results

### Confidence Scores

| Score | Meaning | Action |
|-------|---------|--------|
| 90-100% | Excellent | Safe to use |
| 70-89% | Good | Review flagged items |
| <70% | Needs review | Manual verification recommended |

### Balance Validation

- **✅ Pass**: All transactions reconcile correctly
- **⚠️ Review**: Balance discrepancy detected - needs manual check

### Validation Warnings

If warnings appear:
1. Review the specific transaction(s) mentioned
2. Check the original statement
3. Manually verify amounts if needed
4. Contact support if persistent issues

---

## Tips for Best Results

### 📄 PDF Quality
- Use bank's official PDF downloads (not scanned)
- Avoid password-protected PDFs
- Ensure text is selectable (not image-only)

### 📸 Image Quality (if using photos/scans)
- High resolution (300 DPI minimum)
- Good lighting, no shadows
- Straight alignment (not skewed)
- Clear, legible text

### 🔍 Troubleshooting

**Problem: Low confidence score**
- Try uploading original PDF from bank
- Check if statement is complete (not partial)
- Verify all pages are included

**Problem: Wrong bank detected**
- Manually select bank from dropdown
- Check if statement has bank logo/name visible

**Problem: Missing transactions**
- Verify all pages uploaded
- Check if statement period is complete
- Try processing again

---

## Security & Privacy 🔒

✅ **All processing is LOCAL**
- No data sent to external servers
- Files stored temporarily during processing only
- Automatic cleanup after export

✅ **Court-Ready Evidence**
- Audit trail logged
- Extraction metadata included
- Timestamp and confidence scores recorded

---

## Support

For issues or questions:
1. Check the troubleshooting section above
2. Review validation warnings
3. Contact IT support with:
   - Statement filename
   - Bank name
   - Error message (if any)
   - Screenshot of results

---

**Built for Fifty Six Law Legal Team**
*Automated Bank Statement Extraction for Contentious Probate & APP Claims*
