#!/bin/bash

# Bank Statement Extractor - Launch Script
# Fifty Six Law

echo "🏦 Starting Bank Statement Extractor..."
echo ""

# Check if streamlit is installed
if ! python3 -c "import streamlit" 2>/dev/null; then
    echo "📦 Installing dependencies..."
    pip3 install streamlit openpyxl
fi

# Launch Streamlit app
echo "🚀 Launching UI on http://localhost:8501"
echo ""
streamlit run ui/streamlit_app.py --server.port 8501 --server.headless false
