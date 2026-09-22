from __future__ import annotations

from pathlib import Path

import pytest
from docx import Document
from pypdf import PdfWriter

from smalltobig.ingest.extract_text import extract_and_normalize


def test_extracts_and_normalizes_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "notes.txt"
    path.write_text("Hello   world.\n\n\n\nSecond para.", encoding="utf-8")
    assert extract_and_normalize(path) == "Hello world.\n\nSecond para."


def test_extracts_markdown_as_plain_text(tmp_path: Path) -> None:
    path = tmp_path / "notes.md"
    path.write_text("# Title\n\nBody text.", encoding="utf-8")
    assert extract_and_normalize(path) == "# Title\n\nBody text."


def test_extracts_docx_paragraphs(tmp_path: Path) -> None:
    path = tmp_path / "excerpt.docx"
    document = Document()
    document.add_paragraph("First paragraph.")
    document.add_paragraph("Second   paragraph.")
    document.save(str(path))

    assert extract_and_normalize(path) == "First paragraph.\n\nSecond paragraph."


def test_extracts_vtt_as_stripped_prose(tmp_path: Path) -> None:
    path = tmp_path / "talk.vtt"
    path.write_text(
        "WEBVTT\n\n1\n00:00:01.000 --> 00:00:04.000\nHello there.\n", encoding="utf-8"
    )
    assert extract_and_normalize(path) == "Hello there."


def test_pdf_extraction_runs_on_a_real_pdf(tmp_path: Path) -> None:
    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=200, height=200)
    with path.open("wb") as fh:
        writer.write(fh)

    # A blank page has no text; this just proves the pypdf path executes
    # end-to-end without raising, not that it extracts anything.
    assert extract_and_normalize(path) == ""


def test_unsupported_extension_raises() -> None:
    with pytest.raises(ValueError, match="unsupported file type"):
        extract_and_normalize(Path("audio.mp3"))
