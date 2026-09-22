"""PDF text extraction, via pypdf."""

from __future__ import annotations

from typing import TYPE_CHECKING

from pypdf import PdfReader

if TYPE_CHECKING:
    from pathlib import Path


def extract_pdf_text(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(pages)
