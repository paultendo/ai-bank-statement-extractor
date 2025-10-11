"""Setup script for bank statement extractor."""
from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="bank-statement-extractor",
    version="0.1.0",
    author="Fifty Six Law",
    description="Extract financial transaction data from bank statements",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/bank-statement-extractor",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 3 - Alpha",
        "Intended Audience :: Legal Industry",
        "Topic :: Office/Business :: Financial",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
    python_requires=">=3.10",
    install_requires=[
        "pdfplumber>=0.10.0",
        "PyMuPDF>=1.23.0",
        "camelot-py[cv]>=0.11.0",
        "pytesseract>=0.3.10",
        "opencv-python>=4.8.0",
        "Pillow>=10.0.0",
        "anthropic>=0.25.0",
        "openai>=1.0.0",
        "pandas>=2.0.0",
        "openpyxl>=3.1.0",
        "python-dateutil>=2.8.2",
        "arrow>=1.3.0",
        "python-dotenv>=1.0.0",
        "pyyaml>=6.0",
        "rich>=13.0.0",
        "click>=8.1.0",
    ],
    extras_require={
        "ui": ["streamlit>=1.28.0"],
        "dev": [
            "pytest>=7.4.0",
            "pytest-cov>=4.1.0",
            "black>=23.0.0",
            "flake8>=6.1.0",
            "mypy>=1.5.0",
            "ipython>=8.15.0",
            "ipdb>=0.13.13",
            "pip-audit>=2.6.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "bank-extract=src.cli:main",
        ],
    },
)
