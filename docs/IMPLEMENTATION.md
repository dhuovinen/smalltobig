# HTMSW — Phased implementation plan

**Status:** accepted 2026-09-22. Written to be executed from a cold start — a session
picking this up needs this file, [REQUIREMENTS.md](REQUIREMENTS.md) and
[DECISIONS.md](DECISIONS.md), and nothing else.

Requirement ids (FR-nn, NFR-nn) refer to REQUIREMENTS.md. Decision numbers (#n) refer to
DECISIONS.md.

---

## Before you start

Read in this order: REQUIREMENTS.md §1–2 (what the product is), DECISIONS.md #3, #4, #5,
#15, #16–#20 (the constraints you must not quietly relax), then this file.

**Five things that are not style preferences.** Each has a test enforcing it; if one
fails, the fix is essentially never to loosen the test.

1. Framework content lives in YAML, never in Python or templates (FR-11).
2. The prep card makes zero model calls and zero network calls (FR-34).
3. The roleplay actor never sees the rubric; the judge never sees the actor's persona (FR-42, FR-43).
4. No free text about the user or any third party is ever written to disk (FR-51).
5. Rubrics are boolean plus a verified quoted span. No numeric scoring anywhere (FR-46).

**MVP is Phases 0–4, shipped together.** Phases 5–6 are post-MVP.

The sequencing is deliberately arranged so **Phase 2 has no model dependency at all**. If
roleplay quality disappoints in Phase 3, the prep half still ships and is independently
useful. Do not reorder Phases 2 and 3 to "get the interesting part working first" — that
discards the only de-risking in the plan.

---

## Phase 0 — Foundations and a model-capability decision

**Goal:** prove the hardware and answer one question before anything is built on its
assumed answer.

### Build

- `src/smalltobig/config.py` — `STB_*` settings via pydantic-settings, `.env` auto-loaded (#9).
- `src/smalltobig/llm/client.py` — a `LlmClient` protocol plus an OpenAI-compatible
  implementation. Per-stage resolution: `STB_LLM_BACKEND`, `STB_LLM_BACKEND_<STAGE>` (#15,
  FR-61). Stages: `intake`, `prep`, `roleplay`, `judge`, `debrief`.
- `src/smalltobig/cli.py` — click entry point, `stb` (already declared in `pyproject.toml`).
- `stb doctor` — reaches `mlx_lm.server`, round-trips a generation, loads the embedding
  model, embeds two strings and reports cosine similarity.

### The capability fixture — do this before Phase 3 exists

`stb doctor --judge-fixture`. Supply three short hand-written transcripts with known
answers — one that clearly satisfies `built_on`, one that clearly fails it, one
borderline. Ask the configured model the FR-44 `built_on` question and check it returns
the right boolean **and** a span that actually appears in the transcript.

This is the retargeted version of the open risk in #11. If a 4-bit 8B model cannot do
this reliably, you need a larger model for the judge, and it is far cheaper to learn that
now than after Phase 3 is built. Record the result in DECISIONS.md.

### Done when

`stb doctor` is green and the judge fixture's outcome is written down.

---

## Phase 1 — Framework as data

**Goal:** the entire HTMSW framework exists as YAML, with tests, and no application code
reads it yet.

### Files to create

```
framework/
├── htmsw.yaml       # four steps: id, name, definition, evidence_tier, basis, antipattern
├── domains.yaml     # four domains: id, context, pacing, initial_stakes, escalation_rule
├── personas.yaml    # branching intake questions → cluster ids (provisional, FR-28)
└── phrasings.yaml   # (cluster × domain × step) → example phrasings
```

### Content sources

- `htmsw.yaml` — REQUIREMENTS.md §2.1, tiers from §2.5.
- `domains.yaml` — §2.2, plus the generosity principle (§2.4) attached to `giving_back`.
- `personas.yaml` — the flags in FR-22. Provisional; expect the interviews (§6) to
  rewrite it. Keep branching shallow, three to five questions.
- `phrasings.yaml` — seed from the two worked examples. The Sarah transcript gives
  `cold_networking` phrasings; the Mike transcript gives `potential_collaborator` and
  `giving_back`. `casual_acquaintance` will be thin — mark the gaps explicitly rather
  than inventing filler.

Also capture the reusable closing patterns from §2.4 (*"whatever you do with it from
there is entirely yours"*, *"give the thing a witness"*) as phrasings on step 4.

### Tests — `tests/test_framework.py`

Mirror the structure of the existing `tests/test_seed.py`, which is the house pattern.

- All four steps present, correctly ordered, each with a tier in `{A,B,C,D}`.
- All four domains present; `giving_back` carries the generosity principle.
- Every cluster in `personas.yaml` is reachable through the branching questions — no
  orphans.
- Every (cluster × domain) pair has at least one phrasing per step, **or** an explicit
  `gap: <reason>` marker. Silent absence fails.
- No phrasing is presented as a script — each carries `adapt: true` (FR-36).

### Done when

`pytest tests/test_framework.py` is green and the framework is fully expressed in YAML.
No Python reads it yet. This phase is data and tests only.

---

## Phase 2 — Intake and prep card (no model, no network)

**Goal:** a complete, useful product half that works with the machine offline.

### Build

- `src/smalltobig/framework/loader.py` — load and validate the YAML into Pydantic models.
  Fail loudly at startup on a malformed framework, never at request time.
- `src/smalltobig/intake/classify.py` — `classify(flags: dict) → PersonaCluster`. A pure
  function: no I/O, no model, no randomness (FR-23).
- `src/smalltobig/intake/profile.py` — self-profile persistence, **flags only** (FR-24).
- `src/smalltobig/prep/compose.py` — `compose(cluster, domain, has_target_info) → PrepCard`.
  Pure composition from `phrasings.yaml`. Falls back to the 101-icebreaker layer when
  target info is thin (FR-33). Attaches diagnostic prompts to step 4 (FR-35).
- `src/smalltobig/web/` — FastAPI + Jinja2 + HTMX. Routes: self-profile, new scenario,
  prep card view.
- `stb prep` — the same composition from the CLI.

### Watch for

The temptation to "improve" phrasings with a model call. Do not. FR-34 is a hard
constraint, and the framework's own design says pre-built examples the user adapts, not
freeform generation. A model-adapted variant is Phase 5, and it stays anchored to the
curated examples even then.

### Tests

- `classify()` unit tests across every branch; same flags always yield the same cluster.
- Prep composition for each (cluster × domain) returns all four steps.
- Thin-target-info path returns the icebreaker layer.
- **Acceptance (NFR-13):** with no network and no model server running, `stb prep`
  produces a complete card. Enforce in CI by running it with no `STB_LLM_BASE_URL` set
  and asserting no outbound socket is opened.

### Done when

`stb prep` and the web prep view both work offline, end to end. **This is shippable and
useful on its own.**

---

## Phase 3 — Roleplay

**Goal:** rehearse the sequence against a model partner, scored on the four steps.

### Build

- `src/smalltobig/practice/personas.py` — actor personas per domain. Sarah and Mike ship
  as fixtures (FR-41), each with warmth, verbosity, and a hidden interest revealed only if
  the user finds the thread.
- `src/smalltobig/practice/actor.py` — the conversation loop. **Constructs its messages
  from persona and transcript only.** The rubric and step names must never enter this
  context (FR-42).
- `src/smalltobig/practice/judge.py` — a separate call with a fresh context, receiving the
  finished transcript and the four rubric items. It never receives the actor's private
  persona instructions (FR-43).
- `src/smalltobig/practice/verify.py` — exact substring check of each returned span
  against the transcript (FR-45). Reuse the mechanism from #3; a judge that invents a
  quote fails deterministically.
- Web: roleplay session view, transcript, and the four verdicts with their spans.

### Structural test that matters most

Assert that no message sent to the actor contains any rubric text, any step id, or any
step name. Make it a loop over the actual outbound payloads, not a review of the prompt
template — a template refactor is exactly how this regresses silently.

### Done when

A full Sarah roleplay produces four verdicts, each with a span that verifiably appears in
the transcript.

---

## Phase 4 — Session lifecycle, counters and debrief

**Goal:** progress tracking that stores no prose.

### Build

- `src/smalltobig/session/store.py` — ephemeral scenario state, purged on close (FR-52).
  Prefer holding it in memory; if it must touch disk for crash recovery, it goes to a
  separate scratch database that is deleted on close, never the main one.
- `src/smalltobig/progress/counters.py` — `StepCounter` rows keyed
  `(step_id, domain)`. **Integers and enums only; no TEXT column** (FR-51).
- `src/smalltobig/practice/debrief.py` — the user writes freely about a real
  conversation; the model extracts **only** the four booleans; the prose is discarded
  without ever being written (FR-53).
- Weighting: a real-conversation outcome counts 3× a roleplay outcome on the same counter
  (FR-54).
- `stb purge` and an equivalent web action clearing all stored state (FR-55).

### Tests — `tests/test_privacy.py`

The most important tests in the suite. Write them first, then make them pass.

- **Sentinel sweep:** write a unique string into every free-text intake field, run a full
  scenario, close it, then read every column of every table in the database and assert
  the sentinel appears nowhere.
- **Schema assertion:** counter tables have no column of type TEXT.
- **Routing:** with `STB_LLM_BACKEND=openai` and no `STB_SEND_FIELD_NOTES_TO_CLOUD`,
  assert intake, prebrief and debrief are routed local and the refusal text is emitted
  (FR-63, FR-64).
- **Purge:** after `stb purge`, no user-derived row remains.

### Done when

The sentinel sweep passes and counters accumulate across sessions while the database
contains no prose.

**MVP complete. Ship here.**

---

## Phase 5 — Enrichment (post-MVP)

- Opt-in URL fetch with consent at point of use, stating that the fetch discloses to that
  site who is being researched, from this user's IP (FR-26, #19).
- Model-adapted phrasings that remain anchored to the curated examples rather than
  replacing them.
- Additional domains beyond the four — a YAML-only change if FR-14 held.
- Voice: `mlx-whisper` for spoken roleplay.

## Phase 6 — The ingestion pipeline returns (post-MVP)

Build `sources → claims → rules` with the verify gate (#3), evidence tiers and conflict
records, as designed in PLAN.md §2. Its purpose is no longer to *produce* the content but
to **validate and extend** it — particularly the D-tier elements in REQUIREMENTS.md §2.5,
which currently rest on two self-authored transcripts.

The existing seed corpus (`docs/seed/`) is the starting evidence base. It has already
earned its place once: it independently corroborates step 2 (see DECISIONS #20).

---

## Verification — the whole system

1. `pytest tests/ -m "not mlx"` green. CI runs this on `main` already.
2. `ruff check src/ tests/` and `mypy src/` clean.
3. **Offline proof:** network down, no model server, `stb prep` emits a complete card.
4. **Privacy sweep:** `tests/test_privacy.py` green, sentinel found nowhere.
5. **Actor/judge isolation:** no rubric text in any actor payload.
6. **By hand, against ground truth:** run `stb serve --port 3041`. Work the Sarah
   cold-networking scenario and the Mike collaborator scenario. Confirm the prep cards
   differ in pacing between them — cold networking should stage smaller initial
   disclosures. Then roleplay one and check the judge's four verdicts against the debrief
   call-outs in the original worked examples, which act as ground truth for what a correct
   reading looks like.

---

## Risks carried into implementation

| Risk | Mitigation |
|---|---|
| The judge model is not good enough for FR-44 | Phase 0 fixture answers this before Phase 3 is built. Escalate model size for the judge stage only — the per-stage routing seam exists for this |
| The provisional taxonomy does not predict useful phrasings | FR-28 keeps it in YAML; interviews change data, not code |
| D-tier framework elements turn out to be wrong | Counters across domains are the instrument for detecting it. Phase 6 brings the literature to bear |
| Prep quietly acquires a model dependency | The offline CI test fails the build |
| A refactor leaks the rubric into the actor context | The isolation test inspects outbound payloads, not templates |
| Persistence creeps back toward storing prose | The sentinel sweep fails the build |
