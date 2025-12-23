"""Text cleaning utilities"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Optional

# Try to import BeautifulSoup, but make it optional
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False


@dataclass
class CleaningStats:
    """Statistics from text cleaning process"""
    original_length: int = 0
    final_length: int = 0
    markup_removed: int = 0
    quotes_normalized: int = 0
    dashes_normalized: int = 0
    control_chars_removed: int = 0
    encoding_issues: int = 0

    @property
    def chars_removed(self) -> int:
        return self.original_length - self.final_length


class TextCleaner:
    """Enhanced text cleaner with comprehensive normalization"""

    # Smart quote replacements (using Unicode escapes for reliability)
    QUOTE_REPLACEMENTS = {
        '\u201c': '"',  # Left double quotation mark
        '\u201d': '"',  # Right double quotation mark
        '\u2018': "'",  # Left single quotation mark
        '\u2019': "'",  # Right single quotation mark
        '\u201e': '"',  # Double low-9 quotation mark (German)
        '\u201f': '"',  # Double high-reversed-9 quotation mark
        '\u00ab': '"',  # Left-pointing double angle quotation mark
        '\u00bb': '"',  # Right-pointing double angle quotation mark
        '\u2039': "'",  # Single left-pointing angle quotation mark
        '\u203a': "'",  # Single right-pointing angle quotation mark
    }

    # Dash/hyphen replacements (using Unicode escapes for reliability)
    DASH_REPLACEMENTS = {
        '\u2013': '-',   # En dash
        '\u2014': '--',  # Em dash
        '\u2010': '-',   # Hyphen
        '\u2011': '-',   # Non-breaking hyphen
        '\u2012': '-',   # Figure dash
        '\u2015': '--',  # Horizontal bar
    }

    def __init__(self, config):
        self.config = config.text_cleaning

    def clean(self, text: str) -> str:
        """Clean extracted text (backwards compatible API)"""
        result = self.clean_with_stats(text)
        return result['text']

    def clean_with_stats(self, text: str) -> dict:
        """Clean text and return statistics"""
        stats = CleaningStats(original_length=len(text))
        cleaned = text

        # 1. HTML/XML tag removal
        if self.config.get('strip_markup', True):
            before = len(cleaned)
            cleaned = self._strip_markup(cleaned)
            stats.markup_removed = before - len(cleaned)

        # 2. Unicode normalization (NFKC - compatibility decomposition + canonical composition)
        if self.config.get('normalize_unicode', True):
            cleaned = unicodedata.normalize('NFKC', cleaned)

        # 3. Smart quote normalization
        if self.config.get('normalize_quotes', True):
            cleaned, count = self._normalize_quotes(cleaned)
            stats.quotes_normalized = count

        # 4. Hyphen/dash normalization
        if self.config.get('normalize_dashes', True):
            cleaned, count = self._normalize_dashes(cleaned)
            stats.dashes_normalized = count

        # 5. Control character removal
        if self.config.get('remove_control_chars', True):
            cleaned, count = self._remove_control_chars(cleaned)
            stats.control_chars_removed = count

        # 6. Page number removal (existing)
        if self.config.get('remove_page_numbers'):
            cleaned = re.sub(r'^\s*\d+\s*$', '', cleaned, flags=re.MULTILINE)

        # 7. Whitespace normalization (existing, enhanced)
        if self.config.get('normalize_whitespace'):
            cleaned = self._normalize_whitespace(cleaned)

        stats.final_length = len(cleaned)

        return {
            'text': cleaned,
            'stats': stats
        }

    def _strip_markup(self, text: str) -> str:
        """Remove HTML/XML tags from text"""
        if HAS_BS4:
            # Use BeautifulSoup for robust HTML parsing
            soup = BeautifulSoup(text, 'html.parser')
            return soup.get_text(separator=' ')
        else:
            # Fallback: simple regex-based tag removal
            # Remove HTML tags
            text = re.sub(r'<[^>]+>', ' ', text)
            # Clean up entities
            text = re.sub(r'&nbsp;', ' ', text)
            text = re.sub(r'&amp;', '&', text)
            text = re.sub(r'&lt;', '<', text)
            text = re.sub(r'&gt;', '>', text)
            text = re.sub(r'&quot;', '"', text)
            text = re.sub(r'&#\d+;', '', text)
            return text

    def _normalize_quotes(self, text: str) -> tuple:
        """Normalize smart quotes to ASCII equivalents"""
        count = 0
        for old, new in self.QUOTE_REPLACEMENTS.items():
            occurrences = text.count(old)
            if occurrences > 0:
                text = text.replace(old, new)
                count += occurrences
        return text, count

    def _normalize_dashes(self, text: str) -> tuple:
        """Normalize various dash characters to standard hyphens"""
        count = 0
        for old, new in self.DASH_REPLACEMENTS.items():
            occurrences = text.count(old)
            if occurrences > 0:
                text = text.replace(old, new)
                count += occurrences
        return text, count

    def _remove_control_chars(self, text: str) -> tuple:
        """Remove non-printable control characters (except newlines/tabs)"""
        # Keep: newline (\n=10), carriage return (\r=13), tab (\t=9)
        # Remove: other control characters (0-8, 11-12, 14-31, 127)
        count = 0
        chars = []
        for char in text:
            code = ord(char)
            if code < 32 and code not in (9, 10, 13):
                count += 1
            elif code == 127:  # DEL character
                count += 1
            else:
                chars.append(char)
        return ''.join(chars), count

    def _normalize_whitespace(self, text: str) -> str:
        """Normalize whitespace while preserving paragraph structure"""
        # Replace multiple spaces with single space (preserve newlines)
        text = re.sub(r'[^\S\n]+', ' ', text)
        # Replace multiple newlines with max 2 (paragraph break)
        text = re.sub(r'\n{3,}', '\n\n', text)
        # Trim each line
        lines = [line.strip() for line in text.split('\n')]
        text = '\n'.join(lines)
        # Remove leading/trailing whitespace
        return text.strip()
