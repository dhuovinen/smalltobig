"""Best-effort JSON extraction from a chat reply.

Small local models often wrap structured output in markdown fences or
surround it with prose despite being told not to — common enough across
every place this app asks a model for JSON (claim extraction, rule
synthesis, conflict judging) to share one tolerant parser rather than
trusting the model's formatting.
"""

from __future__ import annotations

import json
import re

_JSON_ARRAY = re.compile(r"\[.*\]", re.DOTALL)
_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


def extract_json_array(reply: str) -> list[object]:
    match = _JSON_ARRAY.search(reply)
    data = json.loads(match.group(0) if match else reply)
    if not isinstance(data, list):
        raise ValueError("reply was not a JSON array")
    return data


def extract_json_object(reply: str) -> dict[str, object]:
    match = _JSON_OBJECT.search(reply)
    data = json.loads(match.group(0) if match else reply)
    if not isinstance(data, dict):
        raise ValueError("reply was not a JSON object")
    return data
