"""PDF Converter using PyMuPDF with optional pikepdf bookmark extraction."""

import logging

import fitz  # PyMuPDF

logger = logging.getLogger(__name__)


def _extract_bookmarks(file_path: str) -> list[str]:
    """Extract TOC titles from PDF bookmarks using pikepdf.

    Returns a list of bookmark title strings, or empty list if pikepdf
    is not installed or the PDF has no bookmarks.
    """
    try:
        import pikepdf
    except ImportError:
        return []

    try:
        with pikepdf.open(file_path) as pdf:
            with pdf.open_outline() as outline:
                titles = []
                for item in outline.root:
                    if hasattr(item, "title") and item.title:
                        titles.append(item.title.strip())
                    if hasattr(item, "children"):
                        for child in item.children:
                            if hasattr(child, "title") and child.title:
                                titles.append(child.title.strip())
                return titles
    except Exception as e:
        logger.debug("Could not extract PDF bookmarks: %s", e)
        return []


class PDFConverter:
    def convert(self, file_path):
        """Convert PDF to text, extracting bookmarks as toc_titles when available."""
        try:
            doc = fitz.open(file_path)

            text = ""
            for page in doc:
                text += page.get_text()

            metadata = {
                "title": doc.metadata.get("title", ""),
                "author": doc.metadata.get("author", ""),
                "page_count": len(doc),
            }

            doc.close()

            # Extract bookmarks for chapter splitting
            toc_titles = _extract_bookmarks(file_path)

            result = {
                "success": True,
                "text": text,
                "metadata": metadata,
            }

            if toc_titles:
                result["toc_titles"] = toc_titles
                logger.info(
                    "Extracted %d bookmark titles from PDF: %s",
                    len(toc_titles),
                    file_path,
                )

            return result

        except Exception as e:
            return {
                "success": False,
                "text": "",
                "metadata": {},
                "error": str(e),
            }
