#!/bin/bash

# Batch Book Processor
# Processes all books in a directory

echo "📚 Batch Book Processor"
echo "======================"
echo ""

# Check if directory argument provided
if [ -z "$1" ]; then
    echo "Usage: ./batch_process.sh <directory>"
    echo ""
    echo "Example:"
    echo "  ./batch_process.sh /path/to/your/ebooks"
    exit 1
fi

BOOK_DIR="$1"

# Check if directory exists
if [ ! -d "$BOOK_DIR" ]; then
    echo "❌ Directory not found: $BOOK_DIR"
    exit 1
fi

# Count books
BOOK_COUNT=$(find "$BOOK_DIR" -type f \( -name "*.pdf" -o -name "*.epub" \) | wc -l | tr -d ' ')

if [ "$BOOK_COUNT" -eq 0 ]; then
    echo "❌ No PDF or EPUB files found in: $BOOK_DIR"
    exit 1
fi

echo "Found $BOOK_COUNT books to process"
echo ""

# Process each book
PROCESSED=0
FAILED=0

for book in "$BOOK_DIR"/*.{pdf,epub}; do
    # Skip if glob doesn't match
    [ -e "$book" ] || continue
    
    BOOK_NAME=$(basename "$book")
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "📖 Processing: $BOOK_NAME"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    
    if python src/cli.py process "$book"; then
        PROCESSED=$((PROCESSED + 1))
        echo "✅ Success: $BOOK_NAME"
    else
        FAILED=$((FAILED + 1))
        echo "❌ Failed: $BOOK_NAME"
    fi
    
    echo ""
done

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "📊 Batch Processing Complete"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "✅ Processed: $PROCESSED books"
echo "❌ Failed: $FAILED books"
echo "📚 Total: $BOOK_COUNT books"
echo ""
echo "Run 'python src/cli.py list' to see all books"
