"""Extracts text content from a PDF, page by page, using PyMuPDF."""

import fitz  # PyMuPDF
from typing import List, Tuple


def extract_pages(pdf_path: str) -> List[Tuple[int, str]]:
    """Returns a list of (page_number, text) tuples. page_number is 1-indexed.
    Pages with no extractable text (e.g. blank pages) are skipped.
    """
    pages = []
    doc = fitz.open(pdf_path)
    try:
        for i, page in enumerate(doc):
            text = page.get_text("text").strip()
            if text:
                pages.append((i + 1, text))
    finally:
        doc.close()
    return pages


def get_page_count(pdf_path: str) -> int:
    doc = fitz.open(pdf_path)
    try:
        return doc.page_count
    finally:
        doc.close()
