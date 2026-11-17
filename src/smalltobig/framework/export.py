"""Export the framework as one JSON document for clients (be-better, FR-11).

Clients must not hard-code steps, domains or rubric text. They fetch this from
`GET /api/htmsw/framework`, or bundle a copy written by `stb export-framework` as
an offline fallback. `revision` is a hash of the content, so a client can tell
whether its bundled copy is stale without comparing field by field.

Partners' private instructions are deliberately left out: they are actor-only
(FR-42), and no client needs them.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from smalltobig.framework.loader import Framework

SCHEMA_VERSION = 1


def export(fw: Framework) -> dict[str, Any]:
    body: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "steps": [
            {
                "id": s.id, "order": s.order, "name": s.name, "definition": s.definition,
                "coaching": s.coaching, "antipattern": s.antipattern,
                "evidence_tier": s.evidence_tier, "rubric_item": s.rubric_item,
                "aliases": s.aliases,
            }
            for s in sorted(fw.steps, key=lambda s: s.order)
        ],
        "rubric": [r.model_dump() for r in fw.rubric],
        "domains": [
            {
                "id": d.id, "name": d.name, "context": d.context, "pacing": d.pacing,
                "initial_stakes": d.initial_stakes, "escalation_rule": d.escalation_rule,
                "evidence_tier": d.evidence_tier,
                "diagnostic_prompts": list(d.diagnostic_prompts),
                "principle": d.principle.model_dump() if d.principle else None,
                "aliases": d.aliases,
            }
            for d in fw.domains
        ],
        "questions": [q.model_dump() for q in fw.questions],
        "clusters": [c.model_dump() for c in fw.clusters],
        "phrasings": [
            p.model_dump(include={"id", "step", "clusters", "domains", "text", "layer",
                                  "calibration", "closing_pattern", "source"})
            for p in fw.phrasings
        ],
        "progress": fw.progress.model_dump(),
    }
    canonical = json.dumps(body, sort_keys=True, separators=(",", ":"))
    body["revision"] = hashlib.sha256(canonical.encode()).hexdigest()[:16]
    return body
