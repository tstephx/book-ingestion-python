"""
Enhanced Text Cleaner with LLM-Era Best Practices

Based on Python Data Cleaning and Preparation Best Practices (Chapter 30):
- Unicode normalization (NFKC)
- Smart quote standardization
- HTML/XML tag stripping
- Control character removal
- Whitespace normalization

These techniques reduce token counts and improve LLM processing quality.
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class CleaningStats:
    """Statistics from the cleaning process"""
    original_length: int = 0
    cleaned_length: int = 0
    unicode_normalizations: int = 0
    smart_quotes_replaced: int = 0
    html_tags_removed: int = 0
    control_chars_removed: int = 0
    whitespace_normalized: int = 0
    ligatures_expanded: int = 0
    page_numbers_removed: int = 0
    
    @property
    def bytes_saved(self) -> int:
        return self.original_length - self.cleaned_length
    
    @property
    def reduction_percent(self) -> float:
        if self.original_length == 0:
            return 0.0
        return (self.bytes_saved / self.original_length) * 100


class EnhancedTextCleaner:
    """
    LLM-optimized text cleaner following best practices.
    
    Focuses on:
    1. Consistent encoding (Unicode normalization)
    2. Standard quotation marks and punctuation
    3. Clean whitespace (no excessive spacing)
    4. Removal of page numbers and headers
    5. Expansion of common ligatures
    """
    
    # Smart quote replacements (curly → straight)
    # Using explicit Unicode escapes to ensure correct character matching
    QUOTE_REPLACEMENTS = {
        '\u201c': '"',   # Left double quotation mark "
        '\u201d': '"',   # Right double quotation mark "
        '\u2018': "'",   # Left single quotation mark '
        '\u2019': "'",   # Right single quotation mark '
        '\u201e': '"',   # German opening double quote „
        '\u201f': '"',   # German closing double quote ‟
        '\u00ab': '"',   # French left guillemet «
        '\u00bb': '"',   # French right guillemet »
        '\u2039': "'",   # French left single guillemet ‹
        '\u203a': "'",   # French right single guillemet ›
    }
    
    # Dash/hyphen normalizations (using explicit Unicode escapes)
    DASH_REPLACEMENTS = {
        '\u2013': '-',   # En dash –
        '\u2014': ' - ', # Em dash — (with spaces)
        '\u2212': '-',   # Minus sign −
        '\u2010': '-',   # Hyphen ‐
        '\u2011': '-',   # Non-breaking hyphen ‑
        '\u2012': '-',   # Figure dash ‒
    }
    
    # Common ligatures to expand (using explicit Unicode escapes)
    LIGATURE_EXPANSIONS = {
        '\ufb01': 'fi',  # ﬁ
        '\ufb02': 'fl',  # ﬂ
        '\ufb00': 'ff',  # ﬀ
        '\ufb03': 'ffi', # ﬃ
        '\ufb04': 'ffl', # ﬄ
        '\u0132': 'IJ',  # Ĳ
        '\u0133': 'ij',  # ĳ
        '\u0153': 'oe',  # œ
        '\u0152': 'OE',  # Œ
        '\u00e6': 'ae',  # æ
        '\u00c6': 'AE',  # Æ
    }
    
    # Other symbol normalizations
    SYMBOL_REPLACEMENTS = {
        '…': '...',     # Ellipsis
        '•': '*',       # Bullet
        '◦': 'o',       # White bullet
        '●': '*',       # Black circle
        '○': 'o',       # White circle
        '■': '*',       # Black square
        '□': 'o',       # White square
        '▪': '*',       # Small black square
        '→': '->',      # Right arrow
        '←': '<-',      # Left arrow
        '↔': '<->',     # Left-right arrow
        '⇒': '=>',      # Double right arrow
        '≥': '>=',      # Greater than or equal
        '≤': '<=',      # Less than or equal
        '≠': '!=',      # Not equal
        '×': 'x',       # Multiplication sign
        '÷': '/',       # Division sign
        '±': '+/-',     # Plus-minus
        '√': 'sqrt',    # Square root
        '∞': 'infinity', # Infinity
    }
    
    # Page number patterns
    PAGE_NUMBER_PATTERNS = [
        # Standalone page numbers
        r'^\s*\d{1,4}\s*$',
        # "Page N" format
        r'^\s*[Pp]age\s+\d{1,4}\s*$',
        # "- N -" format
        r'^\s*[-–—]\s*\d{1,4}\s*[-–—]\s*$',
        # "N of M" format
        r'^\s*\d{1,4}\s+of\s+\d{1,4}\s*$',
        # Headers with page numbers (common in PDFs)
        r'^\s*\d{1,4}\s+Chapter\s+\d+',
        # Footers with chapter info + page
        r'^\s*Chapter\s+\d+.*\|\s*\d{1,4}\s*$',
    ]
    
    # HTML/XML tag pattern
    HTML_TAG_PATTERN = re.compile(r'<[^>]+>')
    
    def __init__(
        self,
        normalize_unicode: bool = True,
        replace_smart_quotes: bool = True,
        normalize_dashes: bool = True,
        expand_ligatures: bool = True,
        normalize_symbols: bool = True,
        remove_page_numbers: bool = True,
        strip_html: bool = True,
        remove_control_chars: bool = True,
        normalize_whitespace: bool = True,
    ):
        """
        Initialize the enhanced text cleaner.
        
        Args:
            normalize_unicode: Apply NFKC normalization
            replace_smart_quotes: Convert curly quotes to straight
            normalize_dashes: Convert various dashes to standard hyphen
            expand_ligatures: Expand fi, fl, etc. ligatures
            normalize_symbols: Convert special symbols to ASCII equivalents
            remove_page_numbers: Remove detected page number lines
            strip_html: Remove HTML/XML tags
            remove_control_chars: Remove control characters (except newlines)
            normalize_whitespace: Collapse multiple spaces
        """
        self.normalize_unicode = normalize_unicode
        self.replace_smart_quotes = replace_smart_quotes
        self.normalize_dashes = normalize_dashes
        self.expand_ligatures = expand_ligatures
        self.normalize_symbols = normalize_symbols
        self.remove_page_numbers = remove_page_numbers
        self.strip_html = strip_html
        self.remove_control_chars = remove_control_chars
        self.normalize_whitespace = normalize_whitespace
        
        # Compile page number patterns
        self.page_patterns = [
            re.compile(p, re.MULTILINE) for p in self.PAGE_NUMBER_PATTERNS
        ]
    
    def clean(self, text: str, track_stats: bool = False) -> str | Tuple[str, CleaningStats]:
        """
        Clean text using LLM-optimized techniques.
        
        Args:
            text: Input text to clean
            track_stats: If True, return (cleaned_text, stats) tuple
            
        Returns:
            Cleaned text, or tuple of (cleaned_text, stats) if track_stats=True
        """
        if not text:
            if track_stats:
                return "", CleaningStats()
            return ""
        
        stats = CleaningStats(original_length=len(text))
        
        # 1. Unicode normalization (NFKC)
        # This handles compatibility characters and composed forms
        if self.normalize_unicode:
            original_len = len(text)
            text = unicodedata.normalize('NFKC', text)
            stats.unicode_normalizations = abs(len(text) - original_len)
        
        # 2. Strip HTML/XML tags
        if self.strip_html:
            count = len(self.HTML_TAG_PATTERN.findall(text))
            text = self.HTML_TAG_PATTERN.sub('', text)
            stats.html_tags_removed = count
        
        # 3. Expand ligatures
        if self.expand_ligatures:
            for ligature, expansion in self.LIGATURE_EXPANSIONS.items():
                if ligature in text:
                    stats.ligatures_expanded += text.count(ligature)
                    text = text.replace(ligature, expansion)
        
        # 4. Replace smart quotes
        if self.replace_smart_quotes:
            for smart, straight in self.QUOTE_REPLACEMENTS.items():
                if smart in text:
                    stats.smart_quotes_replaced += text.count(smart)
                    text = text.replace(smart, straight)
        
        # 5. Normalize dashes
        if self.normalize_dashes:
            for dash, replacement in self.DASH_REPLACEMENTS.items():
                text = text.replace(dash, replacement)
        
        # 6. Normalize symbols
        if self.normalize_symbols:
            for symbol, replacement in self.SYMBOL_REPLACEMENTS.items():
                text = text.replace(symbol, replacement)
        
        # 7. Remove control characters (except newlines and tabs)
        if self.remove_control_chars:
            original_len = len(text)
            # Keep newlines (\n), tabs (\t), and carriage returns (\r)
            text = ''.join(
                char for char in text
                if char in '\n\t\r' or not unicodedata.category(char).startswith('C')
            )
            stats.control_chars_removed = original_len - len(text)
        
        # 8. Remove page numbers (line by line)
        if self.remove_page_numbers:
            lines = text.split('\n')
            cleaned_lines = []
            removed = 0
            
            for line in lines:
                is_page_number = any(
                    pattern.match(line) for pattern in self.page_patterns
                )
                if not is_page_number:
                    cleaned_lines.append(line)
                else:
                    removed += 1
            
            text = '\n'.join(cleaned_lines)
            stats.page_numbers_removed = removed
        
        # 9. Normalize whitespace
        if self.normalize_whitespace:
            original_len = len(text)
            # Collapse multiple spaces (but preserve newlines)
            text = re.sub(r'[^\S\n]+', ' ', text)
            # Remove trailing whitespace from lines
            text = re.sub(r' +\n', '\n', text)
            # Collapse multiple newlines (max 2)
            text = re.sub(r'\n{3,}', '\n\n', text)
            # Strip leading/trailing whitespace
            text = text.strip()
            stats.whitespace_normalized = original_len - len(text)
        
        stats.cleaned_length = len(text)
        
        if track_stats:
            return text, stats
        return text
    
    def clean_for_embedding(self, text: str) -> str:
        """
        Clean text specifically for embedding generation.
        
        More aggressive cleaning for semantic search:
        - Removes all special formatting
        - Normalizes to plain ASCII where possible
        """
        # Apply full cleaning
        text = self.clean(text)
        
        # Additional embedding-specific cleaning
        # Remove markdown-style formatting
        text = re.sub(r'\*\*(.+?)\*\*', r'\1', text)  # Bold
        text = re.sub(r'\*(.+?)\*', r'\1', text)       # Italic
        text = re.sub(r'`(.+?)`', r'\1', text)         # Inline code
        text = re.sub(r'^#+\s*', '', text, flags=re.MULTILINE)  # Headers
        
        # Remove URLs
        text = re.sub(r'https?://\S+', '', text)
        
        # Remove email addresses
        text = re.sub(r'\S+@\S+\.\S+', '', text)
        
        return text.strip()
    
    def get_cleaning_report(self, stats: CleaningStats) -> str:
        """Generate a human-readable cleaning report"""
        return f"""Text Cleaning Report
====================
Original length: {stats.original_length:,} chars
Cleaned length:  {stats.cleaned_length:,} chars
Bytes saved:     {stats.bytes_saved:,} ({stats.reduction_percent:.1f}%)

Changes:
- Unicode normalizations: {stats.unicode_normalizations}
- Smart quotes replaced:  {stats.smart_quotes_replaced}
- HTML tags removed:      {stats.html_tags_removed}
- Control chars removed:  {stats.control_chars_removed}
- Ligatures expanded:     {stats.ligatures_expanded}
- Page numbers removed:   {stats.page_numbers_removed}
- Whitespace normalized:  {stats.whitespace_normalized}
"""


# Convenience function for quick cleaning
def clean_text_for_llm(text: str) -> str:
    """Quick function to clean text for LLM processing"""
    cleaner = EnhancedTextCleaner()
    return cleaner.clean(text)
