#!/bin/bash

# Clear all books and reset database

echo "🗑️  Clearing Book Database"
echo "=========================="
echo ""

# Backup current database
if [ -f data/library.db ]; then
    BACKUP="data/library.db.backup.$(date +%Y%m%d_%H%M%S)"
    echo "📦 Backing up current database to: $BACKUP"
    cp data/library.db "$BACKUP"
fi

# Delete database
echo "🗑️  Deleting database..."
rm -f data/library.db

# Delete all processed books
echo "🗑️  Deleting processed book files..."
rm -rf data/books/*

# Reinitialize database
echo "🔧 Reinitializing database..."
python src/cli.py init

echo ""
echo "✅ Database cleared and reinitialized!"
echo ""
echo "To process books, run:"
echo "  ./batch_process.sh /path/to/books"
