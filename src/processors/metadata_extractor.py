"""Metadata extraction from text and file formats"""

import re
from pathlib import Path

class MetadataExtractor:
    def extract(self, text, source_file, converter_metadata=None):
        """
        Extract metadata from text and converter metadata
        
        Args:
            text: Full text content
            source_file: Source file path
            converter_metadata: Metadata from converter (EPUB/PDF)
        """
        metadata = {
            'source_file': source_file,
            'language': 'en',
            'processing_status': 'processing'
        }
        
        # PRIORITY 1: Use converter metadata (from EPUB/PDF)
        if converter_metadata:
            if converter_metadata.get('title') and converter_metadata['title'].strip():
                metadata['title'] = converter_metadata['title'].strip()
            
            if converter_metadata.get('author') and converter_metadata['author'].strip():
                metadata['author'] = converter_metadata['author'].strip()
            
            if converter_metadata.get('language') and converter_metadata['language'].strip():
                metadata['language'] = converter_metadata['language'].strip()
        
        # PRIORITY 2: Extract from filename if no title
        if 'title' not in metadata or not metadata['title']:
            filename = Path(source_file).stem
            # Clean up filename
            title = filename
            # Remove common patterns
            title = re.sub(r'\s*-\s*\d+(?:st|nd|rd|th)?\s*Edition', '', title, flags=re.IGNORECASE)
            title = re.sub(r'\s*\([^)]*\)', '', title)  # Remove parentheses content
            title = re.sub(r'\s+', ' ', title).strip()
            metadata['title'] = title[:100]  # Max 100 chars
        
        # PRIORITY 3: Find author from text if not in metadata
        if 'author' not in metadata or not metadata['author']:
            # Look for "by Author Name" pattern in first 3000 chars
            author_patterns = [
                r'(?:by|By|BY)\s+([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',  # by John Doe
                r'(?:Author|AUTHOR):\s*([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)',  # Author: John Doe
                r'^([A-Z][a-z]+\s+[A-Z][a-z]+)\s*$',  # Standalone name on line
            ]
            
            for pattern in author_patterns:
                author_match = re.search(pattern, text[:3000], re.MULTILINE)
                if author_match:
                    metadata['author'] = author_match.group(1).strip()
                    break
        
        # Ensure we have at least some title
        if not metadata.get('title') or metadata['title'] == 'Unknown Title':
            # Last resort: use first substantial line
            lines = [line.strip() for line in text.split('\n') if line.strip() and len(line.strip()) > 10]
            if lines:
                # Skip common prefixes
                skip_prefixes = ['table of contents', 'contents', 'praise for', 'copyright', 'preface']
                for line in lines[:10]:  # Check first 10 lines
                    lower_line = line.lower()
                    if not any(lower_line.startswith(prefix) for prefix in skip_prefixes):
                        metadata['title'] = line[:100]
                        break
                else:
                    metadata['title'] = lines[0][:100]
        
        # Calculate word count
        metadata['word_count'] = len(text.split())
        
        return metadata
