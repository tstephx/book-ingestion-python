"""Text cleaning utilities"""

import re

class TextCleaner:
    def __init__(self, config):
        self.config = config.text_cleaning
    
    def clean(self, text):
        """Clean extracted text"""
        cleaned = text
        
        if self.config.get('remove_page_numbers'):
            # Remove standalone numbers (likely page numbers)
            cleaned = re.sub(r'^\s*\d+\s*$', '', cleaned, flags=re.MULTILINE)
        
        if self.config.get('normalize_whitespace'):
            # Replace multiple spaces with single space
            cleaned = re.sub(r'[^\S\n]+', ' ', cleaned)
            # Replace multiple newlines with max 2
            cleaned = re.sub(r'\n{3,}', '\n\n', cleaned)
            # Trim lines
            lines = [line.strip() for line in cleaned.split('\n')]
            cleaned = '\n'.join(lines)
            # Remove leading/trailing whitespace
            cleaned = cleaned.strip()
        
        return cleaned
