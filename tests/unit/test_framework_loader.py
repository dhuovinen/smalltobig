"""framework/loader.py: loads the real framework, fails loudly on a broken one."""

from __future__ import annotations

import shutil
from typing import TYPE_CHECKING

import pytest

from smalltobig.config import Settings
from smalltobig.framework.loader import FrameworkError, load_framework

if TYPE_CHECKING:
    from pathlib import Path

REAL = Settings(_env_file=None).framework_dir  # type: ignore[call-arg]


def test_real_framework_loads() -> None:
    fw = load_framework(REAL)
    assert [s.id for s in fw.steps] == ["step_1", "step_2", "step_3", "step_4"]
    assert fw.domain("giving_back").principle is not None
    assert fw.classification[-1].when == {}


@pytest.fixture
def copy(tmp_path: Path) -> Path:
    dest = tmp_path / "framework"
    shutil.copytree(REAL, dest)
    return dest


def _edit(path: Path, old: str, new: str) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"fixture text not found in {path.name}: {old!r}"
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def test_missing_file(copy: Path) -> None:
    (copy / "domains.yaml").unlink()
    with pytest.raises(FrameworkError, match="missing"):
        load_framework(copy)


def test_unquoted_yes_no_is_rejected(copy: Path) -> None:
    _edit(copy / "personas.yaml", 'options: ["yes", "no"]', "options: [yes, no]")
    with pytest.raises(FrameworkError, match="quote yes/no"):
        load_framework(copy)


def test_phrasing_presented_as_script_is_rejected(copy: Path) -> None:
    _edit(
        copy / "phrasings.yaml",
        "    adapt: true\n    source: {kind: transcript, ref: sarah}",
        "    adapt: false\n    source: {kind: transcript, ref: sarah}",
    )
    with pytest.raises(FrameworkError, match="validation"):
        load_framework(copy)


def test_unknown_cluster_reference(copy: Path) -> None:
    _edit(copy / "phrasings.yaml", "clusters: [family_rooted]", "clusters: [family_focused]")
    with pytest.raises(FrameworkError, match="unknown cluster"):
        load_framework(copy)


def test_classification_without_catch_all(copy: Path) -> None:
    _edit(
        copy / "personas.yaml",
        "  - when: {}\n    cluster: professional_independent",
        "  - when: {primary_focus: professional}\n    cluster: professional_independent",
    )
    with pytest.raises(FrameworkError, match="catch-all"):
        load_framework(copy)


def test_bad_tier(copy: Path) -> None:
    _edit(copy / "htmsw.yaml", "evidence_tier: A", "evidence_tier: A+")
    with pytest.raises(FrameworkError, match="validation"):
        load_framework(copy)
