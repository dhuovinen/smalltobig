"""Integrity checks for the HTMSW framework in framework/ (IMPLEMENTATION.md Phase 1).

The framework is hand-edited YAML that every later phase reads instead of hard-coding
steps, domains or phrasings (FR-11). Nothing fails at import time if a phrasing points
at a misspelled cluster, a domain loses its tier, or a (cluster x domain) pair silently
has no step-1 phrasing. These tests are that failure.

Same pattern as tests/test_seed.py. If one of these fails after a YAML edit, the fix is
almost never to loosen the test.
"""

from __future__ import annotations

import itertools
from pathlib import Path
from typing import Any

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
FRAMEWORK = ROOT / "framework"
SEED = ROOT / "docs" / "seed"
VALID_TIERS = {"A", "B", "C", "D"}
STEP_IDS = ["step_1", "step_2", "step_3", "step_4"]
DOMAIN_IDS = {"cold_networking", "casual_acquaintance", "potential_collaborator", "giving_back"}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh)
    assert isinstance(data, dict), f"{path.name} must be a mapping"
    return data


@pytest.fixture(scope="module")
def htmsw() -> dict[str, Any]:
    return _load(FRAMEWORK / "htmsw.yaml")


@pytest.fixture(scope="module")
def domains() -> list[dict[str, Any]]:
    return _load(FRAMEWORK / "domains.yaml")["domains"]


@pytest.fixture(scope="module")
def personas() -> dict[str, Any]:
    return _load(FRAMEWORK / "personas.yaml")


@pytest.fixture(scope="module")
def phrasings_doc() -> dict[str, Any]:
    return _load(FRAMEWORK / "phrasings.yaml")


def _cluster_ids(personas: dict[str, Any]) -> set[str]:
    return {c["id"] for c in personas["clusters"]}


# ----------------------------------------------------------------------------- steps


def test_four_steps_in_order(htmsw: dict[str, Any]) -> None:
    steps = htmsw["steps"]
    assert [s["id"] for s in steps] == STEP_IDS
    assert [s["order"] for s in steps] == [1, 2, 3, 4]


def test_every_step_is_tiered_with_a_basis(htmsw: dict[str, Any]) -> None:
    for step in htmsw["steps"]:
        assert step["evidence_tier"] in VALID_TIERS, step["id"]
        assert step["basis"].strip(), f"{step['id']} has no basis (FR-12)"
        assert step["definition"].strip(), step["id"]
        assert step["antipattern"].strip(), step["id"]


def test_step_tiers_match_requirements(htmsw: dict[str, Any]) -> None:
    # REQUIREMENTS.md §2.5 / DECISIONS #23. Raising a tier needs evidence and a
    # decision record, not a YAML edit.
    tiers = {s["id"]: s["evidence_tier"] for s in htmsw["steps"]}
    assert tiers == {"step_1": "C", "step_2": "A", "step_3": "C", "step_4": "D"}


def test_rubric_has_one_item_per_step(htmsw: dict[str, Any]) -> None:
    rubric = htmsw["rubric"]
    assert sorted(r["step"] for r in rubric) == STEP_IDS
    rubric_ids = {r["id"] for r in rubric}
    assert rubric_ids == {"disclosed_first", "built_on", "connected_not_reset", "ask_was_earned"}
    for step in htmsw["steps"]:
        assert step["rubric_item"] in rubric_ids, step["id"]
    by_item = {r["id"]: r["step"] for r in rubric}
    for step in htmsw["steps"]:
        assert by_item[step["rubric_item"]] == step["id"], step["id"]


def test_step_seed_rules_exist(htmsw: dict[str, Any]) -> None:
    known = {r["id"] for r in _load(SEED / "rules.yaml")["rules"]}
    for step in htmsw["steps"]:
        missing = set(step.get("seed_rules", [])) - known
        assert not missing, f"{step['id']} cites unknown seed rule(s): {sorted(missing)}"


def test_step_aliases_are_unique_per_client(htmsw: dict[str, Any]) -> None:
    for client in ("htmsw_web", "be_better"):
        values = [s["aliases"][client] for s in htmsw["steps"]]
        assert len(values) == len(set(values)), client


def test_icebreaker_layer_targets_a_real_step(htmsw: dict[str, Any]) -> None:
    layer = htmsw["icebreaker_layer"]
    assert layer["applies_to"] in STEP_IDS
    assert layer["evidence_tier"] in VALID_TIERS


# --------------------------------------------------------------------------- domains


def test_four_domains(domains: list[dict[str, Any]]) -> None:
    ids = [d["id"] for d in domains]
    assert len(ids) == len(set(ids))
    assert set(ids) == DOMAIN_IDS


def test_every_domain_is_tiered_and_calibrated(domains: list[dict[str, Any]]) -> None:
    for domain in domains:
        assert domain["evidence_tier"] in VALID_TIERS, domain["id"]
        assert domain["basis"].strip(), domain["id"]
        for field in ("context", "pacing", "initial_stakes", "escalation_rule"):
            assert str(domain[field]).strip(), f"{domain['id']} missing {field}"
        # FR-35: diagnostic prompts attach to step 4 and must exist per domain.
        assert domain["diagnostic_prompts"], domain["id"]


def test_domain_pacing_is_tier_d(domains: list[dict[str, Any]]) -> None:
    # DECISIONS #23: two transcripts differing on several variables at once.
    assert {d["evidence_tier"] for d in domains} == {"D"}


def test_giving_back_carries_the_generosity_principle(domains: list[dict[str, Any]]) -> None:
    by_id = {d["id"]: d for d in domains}
    principle = by_id["giving_back"]["principle"]
    assert principle["id"] == "generosity_without_reciprocity"
    assert principle["evidence_tier"] == "D"
    assert len(principle["closing_patterns"]) >= 2
    others = [d["id"] for d in domains if d["id"] != "giving_back" and "principle" in d]
    assert not others, f"principle attached to the wrong domain(s): {others}"


def test_domain_aliases_are_unique_per_client(domains: list[dict[str, Any]]) -> None:
    for client in ("htmsw_web", "be_better"):
        values = [d["aliases"][client] for d in domains]
        assert len(values) == len(set(values)), client


# -------------------------------------------------------------------------- personas


def _answer_space(personas: dict[str, Any]) -> list[dict[str, str]]:
    """Every complete set of answers, honouring `ask_if` (FR-23 needs this finite)."""
    questions = personas["questions"]
    combos: list[dict[str, str]] = [{}]
    for q in questions:
        nxt: list[dict[str, str]] = []
        for answers in combos:
            cond = q.get("ask_if", {})
            if all(answers.get(k) == v for k, v in cond.items()):
                nxt.extend({**answers, q["id"]: opt} for opt in q["options"])
            else:
                nxt.append(answers)
        combos = nxt
    return combos


def _matches(when: dict[str, Any], answers: dict[str, str]) -> bool:
    for key, expected in when.items():
        allowed = expected if isinstance(expected, list) else [expected]
        if answers.get(key) not in allowed:
            return False
    return True


def _classify(personas: dict[str, Any], answers: dict[str, str]) -> str:
    for rule in personas["classification"]:
        if _matches(rule["when"], answers):
            return str(rule["cluster"])
    raise AssertionError(f"no classification rule matched {answers}")


def test_question_options_are_strings(personas: dict[str, Any]) -> None:
    # Unquoted yes/no in YAML parse as booleans; that would silently break matching.
    for q in personas["questions"]:
        for opt in q["options"]:
            assert isinstance(opt, str), f"{q['id']} option {opt!r} is not a string"


def test_classification_references_real_questions_and_options(personas: dict[str, Any]) -> None:
    options = {q["id"]: set(q["options"]) for q in personas["questions"]}
    clusters = _cluster_ids(personas)
    for rule in personas["classification"]:
        assert rule["cluster"] in clusters, rule
        for key, expected in rule["when"].items():
            assert key in options, f"unknown question {key!r} in {rule}"
            allowed = expected if isinstance(expected, list) else [expected]
            assert set(allowed) <= options[key], f"unknown option in {rule}"


def test_last_rule_is_a_catch_all(personas: dict[str, Any]) -> None:
    assert personas["classification"][-1]["when"] == {}


def test_every_answer_set_classifies(personas: dict[str, Any]) -> None:
    clusters = _cluster_ids(personas)
    for answers in _answer_space(personas):
        assert _classify(personas, answers) in clusters


def test_every_cluster_is_reachable(personas: dict[str, Any]) -> None:
    reached = {_classify(personas, a) for a in _answer_space(personas)}
    orphans = _cluster_ids(personas) - reached
    assert not orphans, f"unreachable cluster(s): {sorted(orphans)}"


def test_classification_is_deterministic(personas: dict[str, Any]) -> None:
    for answers in _answer_space(personas):
        assert _classify(personas, answers) == _classify(personas, dict(answers))


# Ported from cursor-htmsw app.test.js "cluster priority uses yes flags, not any filled
# answer". Prototype values are translated through the htmsw_web maps in personas.yaml.
@pytest.mark.parametrize(
    ("proto", "expected"),
    [
        ({"hasKids": "yes", "kidsStage": "adult", "hasCaregiving": "no",
          "primaryFocus": "professional"}, "empty-nester"),
        ({"hasKids": "yes", "kidsStage": "teen", "hasCaregiving": "no",
          "primaryFocus": "family"}, "family-rooted"),
        ({"hasKids": "yes", "kidsStage": "independent", "hasCaregiving": "yes",
          "primaryFocus": "professional"}, "sandwich-caregiver"),
        ({"hasKids": "no", "kidsStage": None, "hasCaregiving": "no",
          "primaryFocus": "giving_back"}, "purpose-driven"),
        ({"hasKids": "no", "kidsStage": None, "hasCaregiving": "no",
          "primaryFocus": "professional"}, "professional-independent"),
    ],
)
def test_matches_htmsw_prototype_classification(
    personas: dict[str, Any], proto: dict[str, Any], expected: str
) -> None:
    stage_q = next(q for q in personas["questions"] if q["id"] == "kids_stage")
    stage_from_proto = {v: k for k, v in stage_q["htmsw_web"].items()}
    answers = {
        "has_kids": proto["hasKids"],
        "caregiving": proto["hasCaregiving"],
        "primary_focus": proto["primaryFocus"],
    }
    if proto["kidsStage"] is not None:
        answers["kids_stage"] = stage_from_proto[proto["kidsStage"]]
    cluster = _classify(personas, answers)
    proto_ids = {c["id"]: c["htmsw_web"] for c in personas["clusters"]}
    assert proto_ids[cluster] == expected


# ------------------------------------------------------------------------- phrasings


def _expand(value: Any, universe: set[str]) -> set[str]:
    return set(universe) if value == "all" else set(value)


def test_phrasing_ids_unique(phrasings_doc: dict[str, Any]) -> None:
    ids = [p["id"] for p in phrasings_doc["phrasings"]]
    assert len(ids) == len(set(ids))


def test_every_phrasing_is_an_example_to_adapt(phrasings_doc: dict[str, Any]) -> None:
    # FR-36: never a script.
    for p in phrasings_doc["phrasings"]:
        assert p.get("adapt") is True, f"{p['id']} must carry adapt: true"
        assert p["text"].strip(), p["id"]


def test_every_phrasing_has_provenance(phrasings_doc: dict[str, Any]) -> None:
    for p in phrasings_doc["phrasings"]:
        assert p["source"]["kind"] in {"transcript", "prototype"}, p["id"]
        assert p["source"]["ref"], p["id"]


def test_phrasings_reference_known_ids(
    phrasings_doc: dict[str, Any], personas: dict[str, Any]
) -> None:
    clusters = _cluster_ids(personas)
    for p in phrasings_doc["phrasings"]:
        assert p["step"] in STEP_IDS, p["id"]
        assert p["clusters"] == "all" or set(p["clusters"]) <= clusters, p["id"]
        assert p["domains"] == "all" or set(p["domains"]) <= DOMAIN_IDS, p["id"]
    for g in phrasings_doc["gaps"]:
        assert g["step"] in STEP_IDS
        assert set(g["clusters"]) <= clusters
        assert set(g["domains"]) <= DOMAIN_IDS
        assert g["gap"].strip(), "a gap needs a reason"


def _covered(phrasings_doc: dict[str, Any], clusters: set[str]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for p in phrasings_doc["phrasings"]:
        for c, d in itertools.product(
            _expand(p["clusters"], clusters), _expand(p["domains"], DOMAIN_IDS)
        ):
            out.add((c, d, p["step"]))
    return out


def _declared_gaps(phrasings_doc: dict[str, Any]) -> set[tuple[str, str, str]]:
    out: set[tuple[str, str, str]] = set()
    for g in phrasings_doc["gaps"]:
        for c, d in itertools.product(g["clusters"], g["domains"]):
            out.add((c, d, g["step"]))
    return out


def test_every_combination_has_a_phrasing_or_a_declared_gap(
    phrasings_doc: dict[str, Any], personas: dict[str, Any]
) -> None:
    clusters = _cluster_ids(personas)
    covered = _covered(phrasings_doc, clusters)
    gaps = _declared_gaps(phrasings_doc)
    missing = sorted(
        combo
        for combo in itertools.product(sorted(clusters), sorted(DOMAIN_IDS), STEP_IDS)
        if combo not in covered and combo not in gaps
    )
    assert not missing, f"silent absence (add a phrasing or a gap): {missing}"


def test_no_stale_gaps(phrasings_doc: dict[str, Any], personas: dict[str, Any]) -> None:
    # A gap that a phrasing now covers is misleading; remove it.
    stale = _declared_gaps(phrasings_doc) & _covered(phrasings_doc, _cluster_ids(personas))
    assert not stale, f"gap(s) now covered by a phrasing: {sorted(stale)}"


def test_closing_patterns_appear_as_step_4_phrasings(
    phrasings_doc: dict[str, Any], domains: list[dict[str, Any]]
) -> None:
    giving_back = next(d for d in domains if d["id"] == "giving_back")
    step4_text = " ".join(
        p["text"].lower() for p in phrasings_doc["phrasings"] if p["step"] == "step_4"
    )
    for pattern in giving_back["principle"]["closing_patterns"]:
        core = pattern.lower().rstrip(".")
        assert core in step4_text, f"closing pattern not offered on step 4: {pattern!r}"
