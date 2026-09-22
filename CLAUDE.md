# From Small to Big — project instructions

Local-first app built on the **HTMSW** framework: helps a user prepare for, rehearse and
debrief one specific upcoming conversation. **Status: planning, requirements accepted.**
No application code yet.

Read `docs/REQUIREMENTS.md` then `docs/IMPLEMENTATION.md` before proposing anything.
`docs/PLAN.md` is partly superseded — see its header.

## Non-negotiables

These come from `docs/DECISIONS.md` and are not style preferences. Changing one
is a decision to record there, not a refactor.

1. **Claims are anchored by byte-exact substring match.** Every extracted claim
   must contain a verbatim substring of the stored normalized source, verified
   with a plain string search. Never relax this to fuzzy or semantic matching —
   it is the only thing standing between the rule repository and fluent invented
   advice attributed to real named authors.
2. **Nothing becomes a practised rule without human acceptance.** The model
   proposes candidates; the user accepts, rejects or supersedes.
3. **Rubric items are boolean plus a quoted span.** Never 1–10 scales. Quantized
   local models rating qualities out of ten produce noise that looks like data.
4. **The roleplay actor never sees the rubric; the judge never sees the
   persona's private instructions.** Separate calls, separate contexts.
5. **Real-conversation outcomes outweigh roleplay 3:1 on the same counter, and no
   step reaches top confidence on roleplay alone** (FR-54). This is what stops the
   app certifying the user as good at talking to a language model. The weighting
   applies to the four booleans, not to stored prose — see #9.
6. **No source-text export path.** Extracts of copyrighted material are stored
   for personal study; there is no feature that redistributes them.
7. **Framework content lives in YAML under `framework/`, never in Python or a
   template.** Adding a domain or changing pacing must be a data edit (FR-11, FR-14).
8. **The prep card makes zero model calls and zero network calls.** Enforced by an
   offline CI test. This isolates all model risk in roleplay (DECISIONS #18).
9. **No free text about the user or any third party is ever written to disk.** Persist
   cluster flags and integer counters only; a sentinel-string sweep of every DB column
   enforces it (FR-51, DECISIONS #17).
10. **Backends are per-stage and default to local.** `intake`, `prebrief` and
   `debrief` require `STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand` before any
   cloud backend touches them, and refusing downgrades to local and continues
   rather than aborting. Never collapse this to a single global switch and never
   let a stage silently use a backend the user did not select for it — field
   notes contain the words of people who are not users of this app.

## How to run

Nothing to run yet. Phase 0 (`docs/PLAN.md` §5) delivers `stb doctor`, which
must go green before Phases 1–2 are built on top of it.

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
pip install -e ".[mlx]"        # Apple Silicon only
```

Model servers are run separately, not supervised by this app:

```bash
mlx_lm.server --model <model> --port 3140    # NOT its default 8000; see DECISIONS #2
```

Config is `STB_*` environment variables, with `.env` **auto-loaded** — env vars
override the file.

## Build / test / lint

```bash
ruff check src/ tests/
mypy src/
pytest tests/ -m "not mlx"     # fast, no model server needed
pytest tests/ -m mlx           # needs mlx_lm.server running and Apple Silicon
```

`tests/test_seed.py` guards the hand-edited YAML in `docs/seed/` — including
that every seed rule stays `status: candidate` and `verified: false`. If a
change there fails, the fix is almost never to loosen the test.

## Layout

Target structure is in `docs/PLAN.md` §6. MLX packages are an optional extra
(`[mlx]`) deliberately: they cannot build on Linux, and CI runs on Linux.
Anything importing `mlx_*` at module scope breaks CI — keep those imports behind
the backend boundary in `embed/` and `llm/`.
