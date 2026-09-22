# From Small to Big — plan

A local web app that turns other people's small-talk advice into **rules you have
endorsed**, then drills you on them until they hold up in real conversations.

Package `smalltobig`, CLI `stb`, all inference on-device via MLX.

---

## 1. The problem worth solving

The obvious build is "scrape advice, generate lessons." That produces a pile of
undifferentiated tips, and it is the version that fails, for three reasons that
shape every decision below.

**Experts contradict each other.** Celeste Headlee says don't equate your
experience with theirs — it's not about you. Brooks & Yeomans (2025) found people
*prefer* partners who straightforwardly self-disclose over those who smuggle
disclosure in behind a question. Both are defensible. A system that averages them
into "share, but not too much" has destroyed the information.

**Evidence quality varies by orders of magnitude.** "Ask follow-up questions"
comes from a speed-dating study with 2,000+ conversations and a measured
second-date outcome. "Use their name" is one author's assertion, untested. Both
read like a tip. Only one should be at the front of your queue.

**Small local models confabulate attributions.** Ask a 7B model what Debra Fine
says about entering a room and it will tell you something plausible that Debra
Fine never wrote. In a system whose entire value is provenance, this is fatal
rather than annoying.

So the architecture is built around three commitments:

1. **Every claim is anchored to a verbatim span in a stored source**, verified by
   exact string match, not by trusting the model.
2. **Nothing becomes a rule you practice until you accept it.** The model
   proposes; you arbitrate. Conflicts are recorded, not resolved by fiat.
3. **Real-world evidence outweighs simulator scores.** The app must not train you
   to please a local model.

---

## 2. Pipeline

```
                 you paste / drop files
                          │
                    ┌─────▼─────┐
                    │  SOURCE   │  raw.txt + sha256, immutable
                    └─────┬─────┘
                  chunk + extract (LLM)
                          │
                    ┌─────▼─────┐
                    │   CLAIM   │  verbatim span + paraphrase
                    └─────┬─────┘  ◄── VERIFY GATE: span must match byte-for-byte
                 embed + cluster (mlx-embeddings)
                          │
                    ┌─────▼─────┐
                    │   RULE    │  candidate → you accept/reject → accepted
                    └─────┬─────┘  conflicts recorded as first-class objects
                          │
              ┌───────────┼───────────┐
        ┌─────▼────┐ ┌────▼─────┐ ┌───▼──────┐
        │  DRILL   │ │ ROLEPLAY │ │ PRE-BRIEF│
        └─────┬────┘ └────┬─────┘ └───┬──────┘
              │           │           │  real conversation happens
              │           │      ┌────▼─────┐
              │           │      │FIELD NOTE│  ◄── weighted highest
              └───────────┴──────┴────┬─────┘
                               ┌──────▼──────┐
                               │   MASTERY   │  per-rule, drives what's next
                               └─────────────┘
```

### Stage 1 — Sources

Three ingest paths, all of which avoid the fragile one:

- **Paste raw text** into a form. Always works, no network, no scraping.
- **Watched folder** `~/SmallToBig/inbox/`. Drop `.pdf`, `.txt`, `.md`, `.docx`,
  `.vtt`, `.srt`. A poller (or `stb ingest`) picks them up, moves them to
  `sources/<id>/`, and records the original filename.
- **Manual URL + text** — you record where it came from, you supply the body.

Deliberately **not** building an auto-fetcher. You didn't ask for one, and the
sources that matter most here (books, paywalled HBR, YouTube transcripts) are
exactly the ones a fetcher fails on. A URL field for provenance is not the same
as a crawler.

`Source` record: `id`, `title`, `author`, `kind`
(`paper|book_excerpt|article|talk_transcript|podcast_transcript|notes`), `url`,
`retrieved_at`, `sha256`, `license_note`. Raw bytes are never rewritten —
normalization (dehyphenation, whitespace, subtitle timestamp stripping) writes a
second file, and claim spans index into the **normalized** text.

On copyright: this stores extracts and your own paraphrases for personal study.
There is no export-the-source feature and no redistribution path. Worth being
deliberate about rather than discovering later.

### Stage 2 — Claims, and the verify gate

Chunk normalized text at ~800 tokens with ~100 token overlap. For each chunk the
model returns a JSON array of atomic claims:

```json
{ "verbatim": "<exact substring of the chunk>",
  "paraphrase": "<your words, one sentence>",
  "claim_type": "prescriptive|descriptive|empirical_finding|anecdote" }
```

Then the gate, which is the cheapest high-value thing in the whole system:

```python
start = normalized.find(claim.verbatim)
if start == -1:
    reject(claim, reason="span not found in source")
```

A model that invents a quote fails here deterministically. A model that
paraphrases when told to quote fails here. No judgment call, no second model, no
cost. Claims that survive carry `(source_id, start, end)` and every downstream
rule can be traced back to bytes on disk.

Expect to reject 20–40% on the first pass with a small model. That is the gate
working, not a bug. Log rejections with reasons so prompt changes can be measured
against them.

### Stage 3 — Rules

Embed each surviving claim's paraphrase with `mlx-embeddings`, cluster by cosine
similarity (agglomerative, threshold tuned by hand on the seed set). Each cluster
of claims — ideally from *different* sources — becomes one candidate rule.

```yaml
id: ask-follow-up-questions
name: Ask follow-up questions, not new ones
imperative: When they finish answering, ask about what they just said before introducing a new topic.
rationale: Follow-ups signal responsiveness — listening, understanding, care — which is what actually drives liking.
when_to_apply: Any exchange past the opening two turns.
antipattern: Answering their answer with an unrelated question of your own.
evidence_tier: A
status: candidate        # candidate | accepted | rejected | superseded
claims: [clm_0031, clm_0044, clm_0102]
prerequisites: []
rubric:                  # see §4 on why these are boolean
  - id: asked_followup
    check: Did you ask at least one question that referenced content from their previous turn?
  - id: no_topic_jump
    check: Did you avoid introducing an unrelated topic immediately after their answer?
```

**Evidence tiers** are assigned from the source kind and the claim type, not from
how confident the advice sounds:

| Tier | Means |
|---|---|
| A | Peer-reviewed experiment with a measured behavioral outcome |
| B | Peer-reviewed observational or large field study |
| C | Practitioner consensus — same claim from ≥2 independent non-academic sources |
| D | Single-source assertion, untested |

Tier drives queue order. D-tier rules are not excluded — some are probably true
and all are cheap to try — they just don't get taught before A-tier ones.

**Conflicts are first-class.** After clustering, the model compares rules whose
embeddings are close but whose imperatives diverge, and proposes `Conflict`
records. You resolve each one with a note, and the resolution is itself stored:

```yaml
- between: [dont-equate-experiences, straightforward-self-disclosure]
  note: >
    Headlee says redirecting to your own experience makes it about you.
    Brooks & Yeomans found straightforward disclosure beats disclosure hidden
    behind a question. These conflict only if disclosure must be a redirect.
  resolution: Keep both. Disclose openly and briefly, then return the floor.
    The failure mode is the disguise, not the disclosure.
  resolved_at: 2026-09-19
```

That conflict log is, plausibly, the most valuable artifact the app produces.

### Stage 4 — Lessons

A `Lesson` sequences 1–3 accepted rules plus drills plus one roleplay scenario.
Ordering comes from the prerequisite DAG, then evidence tier, then your weakest
mastery scores. Generated by the model from accepted rules, then hand-edited —
stored as YAML on disk so it is diffable and editable without the app running.

### Stage 5 — Practice

**Drills** — one rule, one stimulus, ~30 seconds. "Here's their answer. Write a
follow-up." Scored against that rule's rubric only. Cheap enough to do twenty in
a sitting, which is the point: Sandstrom et al. (2022) found that what lowered
fear was *repetition volume* of low-stakes attempts.

**Roleplay** — and here the one non-obvious structural decision:

> **The actor and the judge are separate model calls with separate contexts.**

The actor gets scenario + persona + your turns. It does **not** get the target
rules. An actor that knows it is testing your follow-up questions will hand you
openings a stranger never would, and you will learn to hit a pitch that doesn't
get thrown in real life. The judge gets the finished transcript and the rubrics,
and never sees the persona's private instructions. Two calls, one clean signal.

Scenarios (`scenarios/*.yaml`): conference reception, elevator, waiting for a
delayed flight, new-team lunch, neighbor in the hallway. Personas carry warmth,
verbosity, and a hidden interest the model reveals only if you find the thread.

**Pre-brief / debrief** — before a real event, a prep card: your three weakest
rules, two prepared topics for this specific event, one exit line. After, you log
what happened in free text; the model extracts `FieldNote` records tied to rules.

### Stage 6 — Mastery

Leitner boxes per rule (5 boxes, promote on success, demote to box 1 on failure)
rather than full SM-2 — you need "what should I work on" not calendar-optimal
review intervals. Inputs, weighted:

| Signal | Weight |
|---|---|
| Field note from a real conversation | 3.0 |
| Roleplay rubric hit | 1.0 |
| Drill score | 0.5 |

A rule cannot reach the top box on drills alone. That asymmetry is what stops the
app from certifying you as good at talking to a language model.

---

## 3. About the seed corpus

[seed/sources.yaml](seed/sources.yaml) and [seed/rules.yaml](seed/rules.yaml) hold
ten real sources and fifteen candidate rules from the initial research pass.

**Every seed claim is marked `verified: false`.** They were drawn from search
result summaries and abstracts, not from primary text I read in full. I have not
seen the inside of Debra Fine's book or the full Huang et al. PDF, so I will not
write quote marks around words and attribute them. The seed gives you a populated
rule list on day one and something to arbitrate — it does not give you sourced
rules. Those arrive when the real PDFs and transcripts go through Stage 2 and the
verify gate anchors each claim to bytes.

The distribution is itself informative: 5 A-tier rules, 1 B, 4 C, 5 D. The
academic literature on conversation is narrow and solid; the popular advice is
broad and untested. Your queue should reflect that.

---

## 4. Stack

A deliberately boring stack: server-rendered, single process, no build step, no
JavaScript framework. Everything runs on one machine for one user.

| Concern | Choice |
|---|---|
| Runtime | Python ≥3.11, single process |
| Web | FastAPI + Jinja2 + HTMX, server-rendered |
| Models | Pydantic v2 |
| Persistence | SQLite for records; YAML on disk for rules/lessons/scenarios, two-way synced |
| CLI | click — `stb ingest/extract/synthesize/drill/serve/doctor` |
| Logging | structlog |
| Quality | ruff + mypy strict + pytest |
| Config | `STB_*` env vars, `.env` **auto-loaded** |

That last row is deliberate. Config that requires you to remember to `source` a
file fails silently the moment you forget: the file is sitting right there,
looks correct, and is ignored. Auto-loading deletes that failure mode outright.

### Local models

```
chat        mlx_lm.server → http://127.0.0.1:3140/v1   (OpenAI-compatible)
embeddings  mlx-embeddings, in-process (it is a library, not a server)
stt         mlx-whisper, in-process, Phase 7 only
```

Two things to know about this split:

Chat goes over HTTP through an OpenAI-compatible client, so the same code runs
against Ollama (`:11434/v1`) or LM Studio (`:1234/v1`) by changing
`STB_LLM_BASE_URL`. The port is pinned off `mlx_lm.server`'s default of 8000,
which is the most contended port on a dev machine — see DECISIONS.md #2. Worth keeping that seam clean — you will want a bigger model
for rule synthesis than for drill scoring, and possibly a hosted one for a
one-off backfill.

Embeddings do **not** go over HTTP, because `mlx-embeddings` ships no server.
They load in-process in the FastAPI worker. That means model load time on first
use and resident memory in the web process — real but acceptable for a
single-user local tool, and it removes a whole failure mode.

Suggested starting models, all swappable by env var:

- Extraction / synthesis: an 8B-class instruct model at 4-bit. Needs to follow
  JSON schema reliably; this is the job worth spending quality on.
- Roleplay actor: same or smaller. Personality matters more than precision.
- Judge: same as extraction. Scoring is the accuracy-critical path.
- Embeddings: `nomic-embed-text-v2` (137M, fast). `bge-m3` if you want
  multilingual.

**Rubrics must be boolean.** A 4-bit 8B model asked to "rate warmth 1–10"
produces noise dressed as a number — it will cluster on 7, drift with phrasing,
and give you a metric that moves without meaning. Asked "did the user ask a
question that referenced the partner's previous turn — yes or no, and quote the
span" it is reliable. Every rubric item is a yes/no plus a supporting quote from
the transcript, and the quote gets the same exact-match treatment as Stage 2.
Mastery scores are counts of checkable facts, never model vibes.

---

## 5. Phases

Each phase ends with something runnable. No phase depends on a later one.

**Phase 0 — Scaffold and prove the hardware.** Repo, packaging, ruff/mypy/pytest,
CI, registry entry. Then `stb doctor`: reaches `mlx_lm.server`, round-trips a
generation, loads the embedding model, embeds two strings and reports their cosine
similarity. Nothing else gets built until that is green — every later phase
assumes it.

**Phase 1 — Source repository.** Ingest all three paths, normalize, store, list
and read in the web UI. Zero inference. Shippable on its own as a reading pile.

**Phase 2 — Claims and the verify gate.** `stb extract <source>`, chunking, the
JSON contract, the exact-match gate, a rejection log. Review queue in the UI.
Measure the rejection rate here — it is your extraction-prompt regression metric
for the rest of the project.

**Phase 3 — Rules.** Embedding, clustering, candidate synthesis, conflict
proposal, accept/reject/supersede workflow, YAML sync. **This is the deliverable
you actually described** — the rule set, with provenance. If the project stops
here it has already paid for itself.

**Phase 4 — Lessons and drills.** Generation, hand-editing, the drill loop,
boolean rubric scoring, Leitner boxes.

**Phase 5 — Roleplay.** Scenarios, personas, actor/judge separation, transcript
scoring, session history.

**Phase 6 — Pre-brief and debrief.** Prep cards, field-note logging and
extraction, the 3.0 weighting, progress views.

**Phase 7 (optional) — Voice.** `mlx-whisper` STT so roleplay is spoken, TTS for
the partner. Genuinely closer to real practice than typing — but it is polish on
a working loop, not part of one.

---

## 6. Repo shape

```
smalltobig/
├── CLAUDE.md
├── pyproject.toml
├── docs/{PLAN,DECISIONS,ENHANCEMENTS}.md
├── src/smalltobig/
│   ├── cli.py  config.py
│   ├── models/          # Source, Claim, Rule, Conflict, Lesson, Drill,
│   │                    # Scenario, Persona, Session, FieldNote, Mastery
│   ├── ingest/          # watchfolder.py paste.py pdf.py subtitles.py normalize.py
│   ├── llm/             # client.py (protocol) openai_compat.py prompts/ schemas.py
│   ├── embed/           # mlx_backend.py cluster.py
│   ├── extract/         # chunker.py claims.py verify.py      ← the gate
│   ├── synth/           # rules.py conflicts.py lessons.py
│   ├── practice/        # drills.py roleplay.py judge.py debrief.py
│   ├── progress/        # leitner.py scoring.py
│   ├── store/           # db.py rows.py yaml_sync.py repo_*.py
│   └── web/             # app.py routes/ templates/ static/
├── rules/               # accepted rules, YAML, git-tracked — the real output
├── lessons/
├── scenarios/
└── tests/{unit,integration}/
```

`rules/` being plain git-tracked YAML matters more than it looks. The rule set is
the thing you are building; it should survive the app, be greppable, be diffable,
and be readable on a machine with no Python on it.

---

## 7. Open questions

All tracked in [DECISIONS.md](DECISIONS.md), each with the assumption being
worked under so nothing is blocked on an answer.

The one that most deserves an early answer is #11 — whether a small local model
is actually good enough at rule synthesis, which is the hardest reasoning in the
project and the step most likely to disappoint. It is worth testing in Phase 0,
before Phases 1–2 get built on the assumption that it works.

The largest gap is #13: the rule set stays thin until real practitioner
material is ingested. Six of the ten seed sources are open-access and enough to
validate the pipeline; the other four are books and paywalled articles, and they
are the ones carrying the tactical advice.
