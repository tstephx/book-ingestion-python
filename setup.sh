#!/bin/bash

# Quick setup script for Book Ingestion Pipeline (Python)

echo "🐍 Setting up Book Ingestion Pipeline..."
echo ""

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8+ first."
    exit 1
fi

echo "✓ Python 3 found: $(python3 --version)"
echo ""

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source venv/bin/activate

# Install dependencies
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "📝 Next steps:"
echo "1. Activate the virtual environment: source venv/bin/activate"
echo "2. Initialize the database: python src/cli.py init"
echo "3. Process a book: python src/cli.py process /path/to/book.pdf"
echo ""
echo "Run 'python src/cli.py --help' for more commands"
