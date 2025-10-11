# 🚀 GET STARTED - Bank Statement Extractor

## What You Have Now

Based on your NatWest statement screenshots and requirements, I've created a complete project specification ready for your agentic coder (Claude Code, GPT Codex, etc.).

---

## 📁 Documentation Package

You now have **5 comprehensive documents**:

### 1. **[BRIEF.md](BRIEF.md)** - Complete Project Specification
- Detailed functional & technical requirements
- Success criteria and validation rules
- 4-phase implementation plan
- Testing requirements
- Security & compliance guidelines
- Bank statement format documentation

**When to use**: Reference for complete project scope and detailed requirements

---

### 2. **[CLAUDE.md](CLAUDE.md)** - Technical Guide for AI Coders
- Concise technical stack overview
- Project structure and architecture
- Implementation approach with code examples
- Common pitfalls and solutions
- Quick-start commands
- Debugging tips

**When to use**: Primary guide for your agentic coder (Claude Code, GPT Codex, Devin)

---

### 3. **[QUICK_START.md](QUICK_START.md)** ⭐ **START HERE**
- **Based on your actual NatWest statements**
- 1-week MVP plan with UI from Day 1
- Complete code samples ready to implement
- Specific handling for NatWest format
- Streamlit UI code included
- Step-by-step daily tasks

**When to use**: Your primary implementation guide - follow this first!

---

### 4. **[UI_SPECIFICATION.md](UI_SPECIFICATION.md)** - Visual Design Guide
- Complete UI mockup and layout
- Component specifications
- Color scheme and styling
- User interaction flows
- Accessibility guidelines

**When to use**: Reference for UI development and design decisions

---

### 5. **[README.md](README.md)** - Project Overview
- High-level project summary
- Installation instructions
- Usage examples
- Architecture overview

**When to use**: Introduction to the project and quick reference

---

### 6. **[natwest_config.yaml](natwest_config.yaml)** - Bank Configuration
- NatWest-specific format patterns
- Transaction type mappings
- Validation rules
- Field mappings

**When to use**: Configuration file for the extractor

---

## ✅ Key Findings from Your Statements

### NatWest Format Analysis:

**Transaction Structure:**
```
Date: "18 DEC 2024" or "19 DEC" (year inferred)
Description: Multi-line (can span 2-3 lines with reference codes)
Columns: Date | Description | Paid In | Withdrawn | Balance
```

**Critical Features:**
- ✅ Multi-line descriptions (e.g., "Automated Credit HOUGHTON R&M Y FP 18/12/24 1046 918617916401812101")
- ✅ Two separate amount columns (Paid In / Withdrawn, not debit/credit)
- ✅ Running balance after each transaction
- ✅ "BROUGHT FORWARD" for opening balance
- ✅ Various transaction types: Automated Credit, Online Transaction, Card Transaction, Direct Debit

**Validation Points:**
- Balance reconciliation required (opening + transactions = closing)
- Date sequence should be chronological
- Each transaction must have date, description, and balance

---

## 🎯 Recommended Approach

### Phase 1: MVP (1 Week) - Following QUICK_START.md

**Day 1-2**: Core extraction logic
- PDF text extraction with pdfplumber
- Parse NatWest format (handle multi-line descriptions!)
- Extract metadata from header

**Day 3-4**: Simple Streamlit UI
- File upload component
- Display extracted transactions
- Show statement summary
- Basic filters

**Day 5**: Excel export
- Generate structured Excel file
- 3 sheets: Transactions, Metadata, Log
- Format and style

**Testing**: Use your actual NatWest statements throughout development

---

## 🤖 Prompt for Your Agentic Coder

Copy this prompt to Claude Code, GPT Codex, or your agentic coding tool:

```
I need you to build a bank statement extraction system for a UK law firm.

PROJECT CONTEXT:
- Extract financial transaction data from bank statements (PDF format)
- Used for legal claims (contentious probate, bank APP reimbursement)
- Accuracy is critical (used as court evidence)
- Must include simple web UI from the start for easy testing

IMMEDIATE TASK - MVP (1 Week):
Follow the implementation guide in QUICK_START.md to build:

1. PDF extraction engine (src/extractors/natwest_extractor.py)
   - Use pdfplumber for text extraction
   - Handle multi-line transaction descriptions
   - Parse NatWest statement format specifically
   - Extract: Date, Type, Description, Money In, Money Out, Balance
   - Validate balance reconciliation

2. Simple Streamlit web UI (ui/app.py)
   - Drag-and-drop PDF upload
   - Display statement summary (account, dates, balances)
   - Show transactions in table format
   - Filters: flagged transactions, transaction type
   - Export to Excel button

3. Excel exporter (src/exporters/excel_exporter.py)
   - Generate .xlsx with 3 sheets:
     * Transactions (main data)
     * Statement Metadata (account info, totals)
     * Extraction Log (audit trail)
   - Professional formatting

CRITICAL REQUIREMENTS:
- Handle multi-line descriptions (descriptions span 2-3 lines in NatWest format)
- Parse two separate amount columns: "Paid In" and "Withdrawn"
- Validate balance reconciliation (opening + transactions = closing)
- Flag low-confidence extractions (<70%) for manual review
- Simple, professional UI suitable for legal staff

DELIVERABLES:
- Working Streamlit app that processes NatWest PDFs
- Accurate extraction (95%+ target)
- Excel export functionality
- Basic tests

FILES TO REFERENCE:
- QUICK_START.md (primary guide - follow this!)
- natwest_config.yaml (bank format configuration)
- CLAUDE.md (technical details)
- UI_SPECIFICATION.md (UI design)

START IMPLEMENTATION:
Begin with src/extractors/natwest_extractor.py, following the code template in QUICK_START.md.
Focus on handling the multi-line descriptions correctly - this is the most important feature.

Let me know when you're ready to start, and we'll test with real NatWest statement PDFs.
```

---

## 📂 Suggested Project Structure

Create this folder structure before starting:

```
bank-statement-extractor/
├── src/
│   ├── __init__.py
│   ├── extractors/
│   │   ├── __init__.py
│   │   └── natwest_extractor.py
│   ├── exporters/
│   │   ├── __init__.py
│   │   └── excel_exporter.py
│   └── config/
│       └── natwest_config.yaml
├── ui/
│   └── app.py
├── tests/
│   ├── __init__.py
│   └── fixtures/
│       └── (place test PDFs here)
├── temp/              (for uploaded files)
├── output/            (for generated Excel files)
├── docs/
│   ├── BRIEF.md
│   ├── CLAUDE.md
│   ├── QUICK_START.md
│   ├── UI_SPECIFICATION.md
│   └── README.md
├── .env               (API keys - create from .env.example)
├── .gitignore
├── requirements.txt
└── README.md
```

---

## 🔧 Initial Setup Commands

```bash
# 1. Create project directory
mkdir bank-statement-extractor
cd bank-statement-extractor

# 2. Create folder structure
mkdir -p src/extractors src/exporters src/config ui tests/fixtures temp output docs

# 3. Copy documentation files
cp /path/to/outputs/*.md docs/
cp /path/to/outputs/natwest_config.yaml src/config/

# 4. Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 5. Create requirements.txt
cat > requirements.txt << EOF
streamlit>=1.28.0
pdfplumber>=0.10.0
pandas>=2.0.0
openpyxl>=3.1.0
python-dateutil>=2.8.0
PyYAML>=6.0
EOF

# 6. Install dependencies
pip install -r requirements.txt

# 7. Create .env file for API keys (if using Vision APIs later)
cat > .env << EOF
ANTHROPIC_API_KEY=your_key_here
OPENAI_API_KEY=your_key_here
EOF

# 8. Initialize git repository
git init
git add .
git commit -m "Initial commit: Project setup"
```

---

## 🧪 Testing Strategy

### Test Files Needed:
1. **Your actual NatWest statements** (anonymize if needed)
2. Place in `tests/fixtures/natwest/`
3. Test variations:
   - Short statement (1-2 pages)
   - Long statement (5+ pages)
   - Statement with many small transactions
   - Statement with large transactions

### Testing Checklist:
- [ ] PDF opens without errors
- [ ] Metadata extracted correctly (account, dates, balances)
- [ ] All transactions extracted (count matches statement)
- [ ] Multi-line descriptions captured fully
- [ ] Balance reconciles (opening + in - out = closing)
- [ ] Excel export generates successfully
- [ ] UI displays data correctly
- [ ] Filters work as expected

---

## 🎯 Success Criteria (MVP)

Your MVP is complete when:

1. ✅ **Extraction works**: Process your NatWest statement PDF end-to-end
2. ✅ **Accuracy**: 90%+ of transactions extracted correctly
3. ✅ **UI functional**: Upload, view, export via web interface
4. ✅ **Balance validates**: Opening + transactions = closing balance
5. ✅ **Excel exports**: Professional formatted spreadsheet
6. ✅ **No crashes**: Handles errors gracefully

---

## 🚨 Common Issues & Solutions

### Issue 1: Multi-line Descriptions Not Captured
**Problem**: Description cuts off after first line  
**Solution**: Look ahead to next lines that don't start with a date (see QUICK_START.md code)

### Issue 2: Amounts in Wrong Columns
**Problem**: Paid In vs Withdrawn confused  
**Solution**: Use table extraction (camelot-py) or better regex patterns

### Issue 3: Balance Doesn't Reconcile
**Problem**: Calculated balance ≠ stated balance  
**Solution**: 
- Check all transactions extracted
- Verify amount parsing (handle commas)
- Check opening balance correct
- Look for hidden fees/interest

### Issue 4: Date Year Inference Wrong
**Problem**: "19 DEC" parsed to wrong year  
**Solution**: Extract statement period from header, use that year

### Issue 5: PDF Text Extraction Empty
**Problem**: pdfplumber returns no text  
**Solution**: PDF might be scanned (image-based) - need OCR (Phase 2)

---

## 📞 Next Steps

1. **Set up project structure** (use commands above)
2. **Copy documentation** to your project
3. **Give prompt to agentic coder** (use prompt above)
4. **Start with QUICK_START.md** - follow day-by-day plan
5. **Test with your NatWest statements** throughout development
6. **Iterate based on results**

---

## 💡 Pro Tips

1. **Start simple**: Get basic extraction working before adding complexity
2. **Test frequently**: Use your actual statements as test cases from Day 1
3. **UI from start**: Makes testing much easier and more intuitive
4. **Version control**: Commit after each feature
5. **Ask for help**: If extractor struggles with a specific format, provide examples
6. **Iterate quickly**: Don't aim for perfection in MVP - aim for working

---

## 🎓 Learning Resources

If your agentic coder needs more context:

**pdfplumber**: https://github.com/jsvine/pdfplumber  
**Streamlit**: https://docs.streamlit.io/  
**openpyxl**: https://openpyxl.readthedocs.io/  
**pandas**: https://pandas.pydata.org/docs/

---

## ✨ What Happens After MVP

Once MVP works with NatWest:

**Phase 2** (Week 2-3):
- Add OCR support (scanned statements)
- Support more banks (Barclays, HSBC)
- Claude/GPT Vision API integration
- Enhanced UI with editing

**Phase 3** (Week 4+):
- Batch processing
- Case management
- Analytics dashboard
- Integration with your case management system

---

## 📋 Final Checklist Before Starting

- [ ] All documentation files downloaded
- [ ] Project structure created
- [ ] Virtual environment set up
- [ ] Dependencies installed
- [ ] Test PDFs ready (your NatWest statements)
- [ ] Prompt prepared for agentic coder
- [ ] QUICK_START.md read and understood

---

## 🚀 Ready to Build!

You have everything needed:
- ✅ Complete specifications
- ✅ Code templates ready to implement
- ✅ Real examples from your statements
- ✅ Clear MVP scope (1 week)
- ✅ UI included from Day 1
- ✅ Testing strategy

**Your next action**: 
1. Set up the project structure
2. Give the prompt to your agentic coder
3. Follow QUICK_START.md day by day
4. Test with your actual NatWest statements

---

**Good luck! You're going to have a working bank statement extractor very soon!** 🎉

For questions or issues during development, refer back to:
- **QUICK_START.md** for implementation guidance
- **CLAUDE.md** for technical details
- **UI_SPECIFICATION.md** for UI questions
- **BRIEF.md** for comprehensive requirements
