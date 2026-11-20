# From Small to Big — project instructions

Local-first app. Everything runs on one machine for one user; all inference is
on-device via MLX. **Status: Phase 6 (pre-brief/debrief) — the core loop is
complete.** `stb doctor`, ingest, `stb extract`, `stb synthesize`, `stb
lessons`, drills, roleplay, and pre-brief/debrief are all implemented and
green — scenarios, the actor/judge separation, transcript scoring, session
history, and field notes from real conversations. Phase 7 (voice) is
explicitly optional per `docs/PLAN.md`; do not propose it unless asked. **Read
`docs/DECISIONS.md` #11, #12, #15, #16 and #17 before touching `synth/`,
`embed/cluster.py`, or `practice/`** — all live-tested against real models
(2026-09-22) and the findings (threshold recalibration, which model tier
actually works, and the judge's real failure modes — now four times, across
conflicts, drills, roleplay, and debrief, each a genuinely distinct shape:
fabrication, wrong-boolean-on-real-evidence, and wrong-rule-on-real-evidence)
are load-bearing, not speculative.

**Direction (merged 2026-11-16):** the HTMSW requirements and plan from
`origin/main` are now on this branch as the *target*, not a description of the
code. `docs/REQUIREMENTS.md` and `docs/IMPLEMENTATION.md` say "no application
code yet" because they were written before Phases 1–6 landed; read them as the
next direction, and read DECISIONS #18–#24 alongside #1–#17. Repo-wide plan:
this engine is being combined with the `be-better` macOS app and the
`cursor-htmsw` prototype.

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

### Planned (HTMSW target, not yet implemented)

These come from `docs/REQUIREMENTS.md`. They are not true of the current code;
treat them as constraints on *new* work toward that plan. #3 applies under the
`abstracted` privacy profile only; see #5.

1. **Framework content lives in YAML under `framework/`, never in Python or a
   template.** Adding a domain or changing pacing must be a data edit (FR-11, FR-14).
   *Status: implemented.* `framework/*.yaml` (htmsw, domains, personas, phrasings),
   guarded by `tests/test_framework.py`, loaded and cross-checked at startup by
   `framework/loader.py` (fails loudly, never at request time). Each file carries
   `aliases` / `htmsw_web` maps to the be-better and cursor-htmsw ids.
2. **The prep card makes zero model calls and zero network calls.** Enforced by an
   offline CI test. This isolates all model risk in roleplay (DECISIONS #21).
   *Status: implemented* for the HTMSW card (`prep/compose.py`, `/htmsw/prep`,
   `stb prep`), enforced by `tests/unit/test_prep_offline.py`. The older Phase 6
   pre-brief at `/prep` still calls a model; it is a separate feature.
3. **No free text about the user or any third party is ever written to disk.** Persist
   cluster flags and integer counters only; a sentinel-string sweep of every DB column
   enforces it (FR-51, DECISIONS #20).
   *Status: implemented for HTMSW under the `abstracted` profile* (`record/`,
   `tests/test_privacy.py`). The older Phase 6 debrief and field notes are separate
   and still store text.
4. **Backends are per-stage and default to local.** `intake`, `prebrief` and
   `debrief` require `STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand` before any
   cloud backend touches them, and refusing downgrades to local and continues
   rather than aborting. *Not built yet:* one `STB_LLM_BASE_URL` serves every stage;
   `tests/test_privacy.py` carries a skipped placeholder. Never collapse this to a
   single global switch and never
   let a stage silently use a backend the user did not select for it — field
   notes contain the words of people who are not users of this app.
5. **Two privacy profiles, `full` and `abstracted` (DECISIONS #24).** `full` persists
   everything verbatim with attribution, for baseline comparison, and needs no extra
   confirmations. `abstracted` stores only `project(full_record)`, the same projection
   function. Separate stores per profile, and the active profile is always shown.
   Egress rules (#4 above) are identical under both: the profile governs what stays
   on disk, not what leaves the machine. *Status: implemented.*
   `STB_PRIVACY_PROFILE=abstracted|full` (default abstracted); each has its own
   `data_dir/htmsw-<profile>.db` (0600), and opening one under the other profile
   fails. `record/projection.py` is the projection; `record/store.py` writes
   `sessions`/`verdicts` only under `full`. The older Phase 6 features (prep,
   debrief, field notes at `/prep`, `/debrief`) predate profiles and store text.

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
stb seed        # load docs/seed's starter rules + disagreements as UNVERIFIED
                # candidates (no claims); safe to re-run, never overwrites a decision
stb serve       # web UI at http://127.0.0.1:8028 — sources, claims review,
                # rules (accept/reject/supersede), conflicts (resolve),
                # lessons, drills, roleplay, sessions, prep/debrief, field
                # notes, and a mastery dashboard. --host 0.0.0.0 (or
                # STB_HOST=0.0.0.0 in .env) for LAN; no login, trusted network only.
                # HTMSW intake + prep card: /htmsw/profile, /htmsw/prep/new
stb profile set has_kids=yes kids_stage=teen caregiving=no primary_focus=family
stb profile show   # stored flags and the cluster they classify to
stb prep --domain cold_networking [--cluster ID] [--target "what you know"]
                # HTMSW prep card, offline: no model server needed
stb rehearse --partner sarah [--domain giving_back]   # /end to finish and score
stb debrief --domain cold_networking < account.txt   # or type it, then Ctrl-D
stb progress    # per step x domain; real conversations count 3x
stb purge       # active profile's HTMSW store + self-profile (FR-55)
stb reference-check   # judge + debrief vs evals/htmsw_reference.yaml; needs the model.
                # Run before/after any judge, prompt, htmsw.yaml or model change and
                # compare with the baseline in DECISIONS #28 (enforced by the mlx test)
                # Rehearse and debrief need the model server and record under
                # STB_PRIVACY_PROFILE (abstracted: integer outcomes only; full: everything).
                # Web: /htmsw/{rehearse,debrief,progress,purge}
```

**Model configuration, all in `.env` (git-ignored) or `STB_*` env vars, read by
`config.py` and passed to every client through `Settings.llm_options()`:**
`STB_LLM_BASE_URL` (provider), `STB_LLM_MODEL`, `STB_LLM_API_KEY` (Bearer, a
`SecretStr`, never printed), `STB_LLM_ENABLE_THINKING` (`false` to suppress hidden
reasoning), `STB_LLM_TIMEOUT` (seconds). See `examples/config/smalltobig.env.example`.

**Current model (DECISIONS #27):** `Qwen-AgentWorld-35B-A3B-oQ4` on omlx-serve
(`http://127.0.0.1:8090/v1`, key in `.env`, `STB_LLM_ENABLE_THINKING=false`). It judged
the reference rehearsals 4/4 and 0/4 at about 5 s per judgement.

**Model choice for rehearsal (DECISIONS #25).** Thinking models (`qwen3.5`,
`gemma4` under Ollama) return empty answers with this client, because the reasoning
eats the token budget. Use a model that answers directly, e.g. with Ollama:
`STB_LLM_BASE_URL=http://127.0.0.1:11434/v1 STB_LLM_MODEL=ministral-3:8b`.

**JSON API for clients (be-better):** `GET /api/htmsw/framework`, `POST /api/htmsw/judge`,
`POST /api/htmsw/debrief`, `GET /api/htmsw/progress`, `POST|GET /api/htmsw/feedback`
(`web/routes/htmsw_api.py`). Judge and debrief replies carry `outcome_ids` to send back
with feedback. Tester feedback (`record/feedback.py`: right/wrong per step, useful
yes/somewhat/no, fixed issue codes) is integers in both profiles; the free-text comment
is kept only under `full`. It shows on `/htmsw/progress`. Results
record under the engine's privacy profile; clients cannot widen it. No auth, like the rest
of the UI: for the MacBook Air, serve on Tailscale only, e.g.
`stb serve --host 100.103.52.82`. `stb export-framework` writes the framework JSON that
be-better bundles (its `scripts/update-htmsw-framework.sh` calls it).

**Focus trial (docs/FOCUS.md):** `scripts/serve-tester.sh NAME PORT [abstracted|full]`
serves one tester from `~/SmallToBig/testers/NAME` on the Tailscale address; testers
get `docs/TESTER_GUIDE.md`.

`.claude/launch.json` has `stb-web` (port 8028, real data) and `stb-web-demo`
(port 8029, throwaway data in /tmp/smalltobig-demo) for previews.

Config is `STB_*` environment variables, with `.env` **auto-loaded** — env vars
override the file. Accepting a rule writes `rules/<id>.yaml` in `STB_REPO_ROOT`
(default: cwd) — git-tracked, one-way sync from the database, never the other
way (see store/yaml_sync.py). `lessons/<id>.yaml` and `scenarios/*.yaml` are
different: no DB copy at all, no sync direction to reason about — the web UI
reads the YAML files directly, so a hand-edit shows up immediately (see
store/repo_lessons.py and store/repo_scenarios.py). Scenarios are hand-authored
seed content, not generated — the app never writes to `scenarios/`. Roleplay
sessions themselves (the transcript + rubric results) live in SQLite, an
append-only log like drills. Debriefs and the field notes extracted from them
are SQLite too (`debriefs`, `field_notes`). `/home` is an alternative front
door (pipeline ladder + computed next move); `/` still redirects to
`/sources`. Rules with no claims are unverified starter rules (see `seed.py`) and
are labelled as such in the UI and the exported YAML. Model-server failures are
handled centrally (`web/llm_errors.py`), and the nav shows a live model status.

The web UI has no authentication and is meant for a trusted LAN only — see
`docs/BACKLOG.md` before exposing it anywhere else.

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
