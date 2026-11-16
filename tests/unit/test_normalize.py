from __future__ import annotations

from smalltobig.ingest.normalize import collapse_whitespace, dehyphenate, normalize_plain_text
from smalltobig.ingest.subtitles import strip_subtitle_markup


def test_dehyphenate_joins_line_wrapped_word() -> None:
    assert dehyphenate("This is an exam-\nple sentence.") == "This is an example sentence."


def test_dehyphenate_leaves_real_hyphenated_words_alone() -> None:
    # No line break after the hyphen — a genuine compound, not a wrap artifact.
    assert dehyphenate("state-of-the-art") == "state-of-the-art"


def test_collapse_whitespace_trims_runs_and_blank_line_pileups() -> None:
    text = "Para one.   \n\n\n\n  Para  two.  "
    assert collapse_whitespace(text) == "Para one.\n\nPara two."


def test_normalize_plain_text_end_to_end() -> None:
    text = "Line one is long-\nwinded.\n\n\n\nLine two.   "
    assert normalize_plain_text(text) == "Line one is longwinded.\n\nLine two."


def test_strip_subtitle_markup_drops_vtt_structure() -> None:
    vtt = (
        "WEBVTT\n\n"
        "1\n"
        "00:00:01.000 --> 00:00:04.000\n"
        "Hello there.\n\n"
        "2\n"
        "00:00:04.500 --> 00:00:07.000\n"
        "How are you?\n"
    )
    assert strip_subtitle_markup(vtt) == "Hello there.\nHow are you?"


def test_strip_subtitle_markup_drops_srt_structure() -> None:
    srt = (
        "1\n00:00:01,000 --> 00:00:03,000\nFirst line.\n\n"
        "2\n00:00:03,500 --> 00:00:05,000\nSecond line.\n"
    )
    assert strip_subtitle_markup(srt) == "First line.\nSecond line."
