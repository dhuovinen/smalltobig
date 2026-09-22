# HTMSW — Requirements

**Status:** accepted 2026-09-22. Supersedes the product definition in earlier drafts of
`PLAN.md`. Execution sequence is in [IMPLEMENTATION.md](IMPLEMENTATION.md); the reasoning
behind individual choices is in [DECISIONS.md](DECISIONS.md).

Requirements are numbered for traceability. Implementation and tests should cite them.

---

## 1. Product definition

**HTMSW (How To Make Small Talk Work)** helps a user prepare for, rehearse, and debrief
**one specific upcoming conversation with one specific person**.

The premise: rapport is driven by shared commonalities and mutual openness, and most
people default to safe, surface-level exchanges that never reach it. The intervention is
**vulnerability-first disclosure** — the user volunteers something modestly vulnerable
first rather than waiting for the other person to risk it — sequenced in four steps and
calibrated to the domain of the interaction.

The unit of work is a **scenario**, not a lesson. The app is a preparation and rehearsal
tool, not a curriculum.

`smalltobig` remains the repository, package and CLI name. **HTMSW** names the framework
inside it, so "HTMSW step 2" is unambiguous.

---

## 2. The framework

### 2.1 The four-step sequence

| # | Step | Definition |
|---|---|---|
| 1 | **Initial disclosure** | A vulnerable, honest admission, sized to context — small and low-risk for a stranger, larger with an existing warm connection |
| 2 | **Build-on question** | A follow-up question engaging directly with what the other person revealed, rather than pivoting back to the user |
| 3 | **Connecting micro-disclosure** | A second, smaller disclosure linking to what they just shared — deepening the thread rather than resetting it |
| 4 | **Earned ask** | A bigger, more direct question or offer, appropriate *only* after the first three have built real exchange |

### 2.2 Domains

Pacing and stakes scale by domain. The sequence is constant; its calibration is not.

| Domain | Context | Pacing |
|---|---|---|
| `cold_networking` | Total stranger, no prior information | Slowest — small, low-risk disclosures, escalate only on reciprocity |
| `casual_acquaintance` | Known shallowly, want to deepen | Moderate — some shared context exists |
| `potential_collaborator` | Assessing fit, often a stated purpose | Faster — warm introduction and clear purpose allow earlier depth |
| `giving_back` | Offering expertise without expectation of return | Governed by the generosity principle (§2.4) |

### 2.3 The 101-icebreaker layer

Applies across all domains when the user has little or no information about the other
person. Low-stakes, broadly true admissions that cost nothing to say and signal the user
is not performing.

### 2.4 Generosity without reciprocity

For `giving_back`, offers of help carry **no expectation of reciprocity toward the user**.
Any benefit that follows is the other person's initiative, not something the user pursues.
The orientation is maximising societal rather than financial return, with the other
person's own expertise defining what impact means — they hold firsthand insight the user
does not.

Reusable closing patterns identified in testing: *"whatever you do with it from there is
entirely yours"* and *"give the thing a witness."*

### 2.5 Evidence tiers

Framework elements carry tiers on the same A–D scale as `seed/rules.yaml`. Two elements
have independent research support; the rest are hypotheses from two role-play transcripts.
See DECISIONS #20.

| Element | Tier | Basis |
|---|---|---|
| Step 2 | **A** | Independently corroborated by Huang et al. 2017 and Brooks & Yeomans 2025 |
| Step 1 | **C** | Partial support (Brooks & Yeomans); vulnerability-first framing novel |
| Step 3 | **C** | Resolves a logged literature conflict; mechanism untested |
| Step 4 | **D** | Two self-authored transcripts |
| Domain pacing | **D** | Two transcripts, differing on several variables at once |
| Generosity w/o reciprocity | **D** | Novel; no supporting literature located |

---

## 3. Functional requirements

### FR-10 · Framework as data

- **FR-11** The four steps, four domains, pacing parameters and generosity principle are
  declarative YAML under `framework/`. No step, domain or pacing rule may be hardcoded in
  Python or a template.
- **FR-12** Every framework element carries `evidence_tier` and `basis`.
- **FR-13** Elements are addressable by stable id (`step_1`…`step_4`, domain slugs) so
  rubrics, phrasings and counters reference them rather than duplicating text.
- **FR-14** Adding a fifth domain or revising pacing requires editing YAML only.

### FR-20 · Intake

- **FR-21** A **self-profile**, completed once and editable, symmetric with how the target
  person is captured.
- **FR-22** **Persona-cluster classification** via a short branching intake of flags —
  kids / no kids, kids' life stage, parents living, caregiving responsibilities, sense of
  purpose or community involvement.
- **FR-23** Classification is a **pure function of answered flags**, deterministic and
  unit-testable. Same flags always yield the same cluster.
- **FR-24** The app stores **cluster flags, never literal personal facts.** No field
  captures a child's name, a specific health situation, or an employer.
- **FR-25** The **target person** is captured as free text (primary input).
- **FR-26** An optional URL (LinkedIn, bio page) may be supplied as a secondary source.
  Fetching it is **opt-in per scenario with explicit consent at the point of use** — never
  a background fetch on paste. The consent text must state that the fetch discloses to
  that site who is being researched, from this user's IP (DECISIONS #19).
- **FR-27** Domain selection per scenario, from §2.2.
- **FR-28** The taxonomy in FR-22 is **provisional**, pending the interviews in §6. It is
  defined in YAML so findings change data, not code.

### FR-30 · Prep card

- **FR-31** Composed from **curated phrasings** for the (persona cluster × domain) pair.
  Per the framework: pre-built hypothetical example phrasings the user adapts into their
  own words — **not** freeform lines generated live.
- **FR-32** Renders all four steps with domain-appropriate pacing and stakes.
- **FR-33** Falls back to the 101-icebreaker layer (§2.3) when target information is thin.
- **FR-34** **Requires zero model calls and zero network access.** This is a hard
  constraint, not an optimisation — see NFR-13.
- **FR-35** Surfaces diagnostic prompts ("where are you actually stretched thin?") as
  guided suggestions attached to step 4, rather than relying on the user to arrive at them.
- **FR-36** Every phrasing is marked as an example to adapt, never as a script to read.

### FR-40 · Roleplay

- **FR-41** An actor persona per domain plays the other person. Sarah (cold networking)
  and Mike (potential collaborator) ship as fixtures, drawn from the worked examples.
- **FR-42** **The actor never receives the rubric or step names.** An actor that knows it
  is testing build-on questions supplies openings a real person would not (DECISIONS #4).
- **FR-43** A **separate judge call, with a separate context**, scores the finished
  transcript. The judge never sees the actor's private persona instructions.
- **FR-44** The rubric is four boolean items, one per step, each requiring a quoted span
  from the transcript:

  | Item | Check |
  |---|---|
  | `disclosed_first` | Did the user disclose something about themselves before asking anything substantive? |
  | `built_on` | Did their follow-up question reference specific content the partner had just revealed? |
  | `connected_not_reset` | Was their second disclosure connected to the partner's, and no larger than it? |
  | `ask_was_earned` | Did the ask come after at least two rounds of reciprocal exchange? |

- **FR-45** Quoted spans are verified by exact substring match against the transcript.
  A judge that invents a quote fails deterministically (same mechanism as DECISIONS #3).
- **FR-46** No numeric or scalar scoring anywhere. Boolean plus span only (DECISIONS #5).

### FR-50 · Session, persistence and progress

- **FR-51** **Persistence invariant.** Persisted: persona-cluster flags, domain, per-step
  attempt and success counters. **Never persisted:** any free text written by the user or
  describing a third party — intake text, transcripts, debrief prose, URLs, names.
- **FR-52** Scenario data is session-scoped and purged when the scenario closes.
- **FR-53** Debrief extracts **only step outcomes** (four booleans plus the domain). The
  prose the user writes is processed and discarded, never stored.
- **FR-54** Real-conversation outcomes weight **3× a roleplay outcome** on the same
  counter. A step cannot reach top confidence on roleplay alone.
- **FR-55** A single, obvious **"purge everything"** action clearing all stored state.
- **FR-56** No telemetry, no analytics, no training use of any input.

### FR-60 · Backend routing

- **FR-61** Extends DECISIONS #15 with two stages: `intake` and `prep`.
- **FR-62** `prep` never calls a model at all (FR-34), so it has no backend to route.
- **FR-63** **`intake` joins `prebrief` and `debrief` behind the field-note
  acknowledgement** (`STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand`). Target-person intake
  is the most identifying input in the app — a name, an employer, a bio — and is currently
  outside the guard. This closes that gap (DECISIONS #19).
- **FR-64** Refusal downgrades the stage to local and continues; it never aborts.

---

## 4. Non-functional requirements

- **NFR-11** Privacy invariants are **executable tests**, not documentation. See §7.
- **NFR-12** The app functions fully offline for prep. Roleplay requires a local model
  server but no internet.
- **NFR-13** With the network down and no model server running, `stb prep` produces a
  complete prep card. This is the acceptance test for FR-34.
- **NFR-14** Single process, single user, one machine.
- **NFR-15** Prep card renders in under one second — it is data composition, not inference.
- **NFR-16** Python ≥3.11, `ruff` clean, `mypy --strict` clean, tests green on CI.

---

## 5. Data model

| Entity | Persisted? | Notes |
|---|---|---|
| `SelfProfile` | Flags only | Cluster flags; no literal facts (FR-24) |
| `PersonaCluster` | Yes | Derived, deterministic (FR-23) |
| `Domain` | Reference data | From `framework/domains.yaml` |
| `FrameworkStep` | Reference data | From `framework/htmsw.yaml`, carries tier |
| `Phrasing` | Reference data | Keyed (cluster × domain × step) |
| `Scenario` | **No — ephemeral** | Target text, URL, notes. Purged on close (FR-52) |
| `PrepCard` | **No — ephemeral** | Regenerable from cluster + domain |
| `RoleplaySession` | **No — ephemeral** | Transcript discarded after scoring (FR-53) |
| `StepCounter` | Yes | `(step_id, domain, attempts, successes, source_weight)` — integers and enums only, no TEXT column |

---

## 6. Open research

Carried forward from the framework document. None blocks implementation, because FR-28
makes the taxonomy data rather than code.

- Determine the number, order and branching logic of intake questions for cluster
  classification.
- Conduct person-on-the-street interviews to identify which metadata attributes actually
  predict useful, resonant phrasings — before locking the MVP question set.
- Test scenarios beyond the two documented to see whether the four-step sequence and the
  domain-pacing model generalise.
- Validate the D-tier elements in §2.5. The app is the instrument for this: per-step
  counters across domains are exactly the data needed.

### Parked note — boolean rubrics and the Jev model

Recorded at the user's request; **no action taken and none planned in this scope.**

> Boolean rubrics may be a good use case for the Jev model.

The four rubric items in FR-44 are unusually well-formed for a small, specialised
evaluator: each is a single closed question over a short transcript, requiring a
supporting span rather than a judgement of degree. That shape is what makes FR-44
cheap to evaluate and would plausibly suit a purpose-built model.

"Jev model" is recorded verbatim as the user's term; it has not been expanded or
researched here. Anyone picking this up should ask what it refers to before acting.

---

## 7. Out of scope for the MVP

- The `sources → claims → rules` ingestion pipeline (deferred to Phase 6)
- Multi-user, accounts, or any server deployment
- Mobile or native clients
- Voice input or output
- Domains beyond the four in §2.2
- Any export path for ingested source text (DECISIONS #8)

---

## 8. Traceability — how each requirement is verified

| Requirement group | Verified by |
|---|---|
| FR-10s | `tests/test_framework.py` — referential integrity, every step tiered, every (cluster × domain) has ≥1 phrasing |
| FR-20s | Unit tests on `classify(flags) → cluster`; a test asserting no model field accepts a literal personal fact |
| FR-30s, NFR-13 | Offline acceptance test: network down, no model server, `stb prep` still emits a full card |
| FR-40s | Actor/judge isolation test asserting rubric text and step names appear in no actor message; span-verification test |
| FR-50s | `tests/test_privacy.py` — sentinel-string sweep of every DB column after scenario close; schema assertion that counter tables have no TEXT column |
| FR-60s | Routing test: `STB_LLM_BACKEND=openai` without the acknowledgement routes intake local and emits the refusal |
