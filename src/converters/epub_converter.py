"""EPUB Converter using ebooklib"""

from ebooklib import epub
from bs4 import BeautifulSoup

class EPUBConverter:
    def convert(self, file_path):
        """Convert EPUB to text"""
        try:
            book = epub.read_epub(file_path)
            
            text_parts = []
            
            # Extract text from all document items
            for item in book.get_items():
                if item.get_type() == 9:  # DOCUMENT type
                    soup = BeautifulSoup(item.get_content(), 'html.parser')
                    text_parts.append(soup.get_text())
            
            text = '\n\n'.join(text_parts)
            
            metadata = {
                'title': book.get_metadata('DC', 'title')[0][0] if book.get_metadata('DC', 'title') else '',
                'author': book.get_metadata('DC', 'creator')[0][0] if book.get_metadata('DC', 'creator') else '',
                'language': book.get_metadata('DC', 'language')[0][0] if book.get_metadata('DC', 'language') else 'en'
            }
            
            return {
                'success': True,
                'text': text,
                'metadata': metadata
            }
        
        except Exception as e:
            return {
                'success': False,
                'text': '',
                'metadata': {},
                'error': str(e)
            }
