# From Small to Big — project instructions

Local-first app. Everything runs on one machine for one user; all inference is
on-device via MLX. **Status: planning.** Design is complete, no application code
written yet — see `docs/PLAN.md` before proposing anything.

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
5. **Field notes outweigh simulator scores 3:1, and no rule reaches top mastery
   on drills alone.** This is what stops the app certifying the user as good at
   talking to a language model.
6. **No source-text export path.** Extracts of copyrighted material are stored
   for personal study; there is no feature that redistributes them.

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
