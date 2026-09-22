"""Strip WebVTT/SRT structure — headers, cue numbers, timestamp lines — and
return the spoken text as plain prose. See docs/PLAN.md §2 Stage 1.
"""

from __future__ import annotations

import re

from smalltobig.ingest.normalize import normalize_plain_text

_TIMESTAMP_LINE = re.compile(r"^\d{2}:\d{2}:\d{2}[.,]\d{3}\s*-->\s*\d{2}:\d{2}:\d{2}[.,]\d{3}")
_CUE_NUMBER_LINE = re.compile(r"^\d+$")
_STRUCTURAL_PREFIXES = ("WEBVTT", "NOTE", "STYLE", "REGION")


def strip_subtitle_markup(text: str) -> str:
    kept_lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(_STRUCTURAL_PREFIXES):
            continue
        if _CUE_NUMBER_LINE.fullmatch(line):
            continue
        if _TIMESTAMP_LINE.match(line):
            continue
        kept_lines.append(line)
    return normalize_plain_text("\n".join(kept_lines))
