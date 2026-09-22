"""Raw file -> normalized plain text, dispatched by extension.

Covers every format docs/PLAN.md §2 Stage 1 lists for the watched folder:
.pdf, .txt, .md, .docx, .vtt, .srt.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from docx import Document

from smalltobig.ingest.normalize import normalize_plain_text
from smalltobig.ingest.pdf import extract_pdf_text
from smalltobig.ingest.subtitles import strip_subtitle_markup

if TYPE_CHECKING:
    from pathlib import Path

SUPPORTED_SUFFIXES = {".txt", ".md", ".pdf", ".docx", ".vtt", ".srt"}


def extract_and_normalize(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in {".txt", ".md"}:
        return normalize_plain_text(path.read_text(encoding="utf-8"))
    if suffix == ".pdf":
        return normalize_plain_text(extract_pdf_text(path))
    if suffix == ".docx":
        return normalize_plain_text(_extract_docx_text(path))
    if suffix in {".vtt", ".srt"}:
        return strip_subtitle_markup(path.read_text(encoding="utf-8"))
    raise ValueError(f"unsupported file type {suffix!r} (supported: {sorted(SUPPORTED_SUFFIXES)})")


def _extract_docx_text(path: Path) -> str:
    document = Document(str(path))
    return "\n\n".join(paragraph.text for paragraph in document.paragraphs)
