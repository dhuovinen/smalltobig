# From Small to Big — project instructions

Local-first app. Everything runs on one machine for one user; all inference is
on-device via MLX. **Status: Phase 4 (lessons and drills).** `stb doctor`,
ingest, `stb extract`, `stb synthesize` and `stb lessons` are implemented and
green — the drill loop, Leitner mastery boxes, and lesson sequencing with
YAML export to `lessons/`. See `docs/PLAN.md` before proposing anything past
Phase 4 (Roleplay). **Read `docs/DECISIONS.md` #11, #12 and #15 before
touching `synth/`, `embed/cluster.py`, or `practice/drills.py`** — all
live-tested against real models (2026-09-22) and the findings (threshold
recalibration, which model tier actually works, the judge's real failure
mode — twice now, rule conflicts and drill rubrics both) are load-bearing,
not speculative.

This branch stays on the original `docs/PLAN.md` direction rather than the
HTMSW pivot on `origin/main` (see the Phase 0+1 commit message) — check
`git log --oneline main..origin/main` before assuming the two have converged.

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

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev,web]"
pip install -e ".[mlx]"        # Apple Silicon only
```

Model servers are run separately, not supervised by this app:

```bash
mlx_lm.server --model <model> --port 3140    # NOT its default 8000; see DECISIONS #2
```

Then:

```bash
stb doctor      # reaches the chat server, round-trips a generation,
                # loads the embedding model, reports cosine similarity
stb ingest      # picks up files dropped in STB_DATA_DIR/inbox (default
                # ~/SmallToBig/inbox/), moves them to sources/<id>/
stb extract <source_id>   # chunk, ask the model for claims, verify each by
                # exact substring match, report the rejection rate
stb synthesize  # cluster accepted claims into candidate rules, propose
                # conflicts — needs a bigger model than doctor/extract;
                # see DECISIONS.md #11 before assuming your model can do this
stb lessons     # sequence not-yet-lessoned accepted rules into lessons/*.yaml
                # (prerequisite DAG, then tier, then weakest mastery)
stb serve       # web UI at http://127.0.0.1:3041 — sources, claims review,
                # rules (accept/reject/supersede), conflicts (resolve),
                # lessons, the drill loop, and a mastery dashboard
```

Config is `STB_*` environment variables, with `.env` **auto-loaded** — env vars
override the file. Accepting a rule writes `rules/<id>.yaml` in `STB_REPO_ROOT`
(default: cwd) — git-tracked, one-way sync from the database, never the other
way (see store/yaml_sync.py). `lessons/<id>.yaml` is different: no DB copy at
all, no sync direction to reason about — the web UI reads the YAML files
directly, so a hand-edit shows up immediately (see store/repo_lessons.py).
Phase 4 stops at lessons/drills/mastery; nothing in Phase 5 (roleplay,
actor/judge separation, scenarios) exists yet.

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
