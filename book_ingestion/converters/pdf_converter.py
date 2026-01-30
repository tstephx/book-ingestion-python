"""PDF Converter using PyMuPDF"""

import fitz  # PyMuPDF

class PDFConverter:
    def convert(self, file_path):
        """Convert PDF to text"""
        try:
            doc = fitz.open(file_path)
            
            text = ""
            for page in doc:
                text += page.get_text()
            
            metadata = {
                'title': doc.metadata.get('title', ''),
                'author': doc.metadata.get('author', ''),
                'page_count': len(doc)
            }
            
            doc.close()
            
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
