# From Small to Big — open decisions and risks

Each entry records the choice made so planning could continue, and what changing
it would cost. Entries are amended rather than deleted, so the reasoning stays
auditable even after a decision is reversed.

---

## Needs your call before Phase 0

### 1. Port allocation

**Assumed:** the web UI binds **3041**, via `STB_PORT`.

Pick the port and record it wherever you track local services *before* writing
code, not after. An app that starts life on whatever port was free ends up with
that number in shell history, browser bookmarks, and half-remembered notes, and
moving it later costs more than the two minutes it saves now.

**Cost of changing:** one config default. Trivial — but only while it is still
trivial.

### 2. Don't run `mlx_lm.server` on its default port

Its default is 8000, which is the most contended port on any development
machine — every other FastAPI app, every `python -m http.server`, every tutorial
wants it. The commonly cited `--port 8080` is no better for the same reason.

**Assumed:** run `mlx_lm.server --port 3140` and point
`STB_LLM_BASE_URL=http://127.0.0.1:3140/v1` at it. Keeping model servers in an
adjacent block to the app itself makes "which of these is the model" answerable
from `lsof` alone.

Worth deciding the block rather than the single port: MLX will likely grow to
two or three servers — chat, a larger model for synthesis, possibly a
reranker.

---

## Decided, with the reasoning recorded

### 3. The verify gate is non-negotiable

Every extracted claim must contain a byte-exact substring of the stored
normalized source, checked with `str.find`, or it is rejected. See PLAN.md §2
Stage 2.

**Why it is load-bearing:** the app's only real value over reading the books
yourself is that a rule can be traced to who actually said it. A 4-bit local
model asked "what does Debra Fine say about entering a room" will produce
fluent, plausible, invented text. Without the gate, the rule repository silently
fills with advice attributed to people who never gave it, and there is no way to
tell which entries are real. The gate costs one string search per claim.

**What it costs:** a 20–40% first-pass rejection rate, and claims whose useful
content spans a chunk boundary get dropped. Mitigated by 100-token chunk
overlap; not eliminated. Accepted.

### 4. Actor and judge are separate model calls

The roleplay partner never sees the rules being scored; the scorer never sees the
persona's private instructions. PLAN.md §2 Stage 5.

**Why:** an actor that knows you're being graded on follow-up questions feeds you
openings a real stranger wouldn't, and you learn to hit a pitch nobody throws.
A judge that just spent twenty turns playing your conversational partner is
anchored on its own performance.

**Cost:** two model calls instead of one, and a second context to manage. On
local inference this roughly doubles roleplay latency. Worth it.

### 5. Rubrics are boolean plus a quoted span — never 1–10 scales

**Why:** a 4-bit 8B model asked to rate warmth out of ten clusters on 7, drifts
with prompt phrasing, and produces a number that moves without meaning — the
worst kind of metric, because it looks like data. The same model asked "did the
user ask a question referencing the partner's previous turn — yes or no, and
quote it" is reliable. Quoted spans get the same exact-match check as Stage 2.

**Cost:** rubrics take longer to write and can't express gradations. Some real
qualities (was that funny? was that warm?) genuinely resist boolean treatment and
will be under-measured. Accepted — an honest gap beats a fake gradient.

### 6. Field notes outweigh simulator scores 3:1, and a rule can't master on drills alone

**Why:** the obvious failure of an app like this is that you get good at talking
to a language model. The weighting and the box cap are structural defenses, not
tuning knobs — a rule reaching top mastery must have real-world evidence behind
it.

**Cost:** progress feels slow if you're only drilling. That is the intended
signal.

### 7. No auto-fetcher for URLs

You didn't pick it, and the sources that matter most here (books, paywalled HBR,
YouTube transcripts) are precisely the ones a fetcher fails on — so it would be
maintenance burden buying coverage of the easy 20%. A URL field for provenance is
kept; a crawler is not built.

**Cost:** you paste text by hand for web sources. Note this makes
`src_headlee_ted_2015` the cheapest real ingest to start with — TED publishes a
full transcript, it's short, and it contains exactly ten enumerated prescriptive
claims, which makes it the ideal Phase 2 test case.

### 8. Copyright posture

Extracts and paraphrases stored locally for personal study. No full-text
retention of purchased books, no export feature, no redistribution path, no
"share this rule set with the source text attached."

**Why decided now:** it is a constraint on the data model, not a policy note. If
an export feature gets built in Phase 6 it is expensive to retrofit this.

### 9. `.env` auto-loads

Config that must be `source`d by hand fails silently when you forget — the file
is present, looks right, and is ignored, which is the worst way for config to
break because nothing errors. `STB_*` environment variables still override the
file when set.

### 10. Embeddings run in-process, chat over HTTP

`mlx-embeddings` ships no server — it is a library. So the embedding model loads
inside the FastAPI worker while chat goes out over an OpenAI-compatible HTTP
endpoint. Asymmetric and slightly odd-looking; it is what the tools are.

**Cost:** first-use model load latency, resident memory in the web process, and
embeddings can't be scaled or restarted separately. Fine for one user on one Mac.
**Benefit:** one less service to have running before the app works.

---

## Risks I can't design away

### 11. Small local models may not be good enough at rule synthesis

Stage 3 asks a model to cluster claims, write a general imperative from several
specific ones, and spot logical conflicts between imperatives. That is the
hardest reasoning in the project, and it's the step where a 4-bit 8B model is
most likely to disappoint — producing rules that are vague ("be a good
listener") or that merge two genuinely distinct ideas.

**Mitigation, in order:** the human accept/reject gate means bad candidates cost
you review time, not correctness. If quality is still poor, Stage 3 is a batch
job run rarely on a handful of sources, so it's the one place a larger model —
30B-class at 4-bit, slow, or a one-off hosted call — is affordable. The `LlmClient`
seam exists to make that a config change. Keeping synthesis a separate CLI verb
(`stb synthesize`) rather than a web action is partly for this reason.

**This is the main thing I'd want to test in Phase 0**, before building Phases
1–2 on the assumption it works. Suggest extending `stb doctor` with a fixture:
five hand-written claims that should cluster into two rules, and check whether
your chosen model gets it. Cheap, and it tells you early which model tier you
need.

**Tested live in Phase 3 (2026-09-22), against `mlx_lm.server` and
`mlx-community/all-MiniLM-L6-v2-bf16` embeddings, on real ingested/extracted
claims — not synthetic fixtures:**

- **Clustering threshold needed real recalibration, not just "tuned by hand on
  the seed set" as an abstract instruction.** The code shipped with a guessed
  default of 0.75. Measured cosine similarity between paraphrases of genuinely
  related claims (two independent phrasings of "ask follow-up questions") came
  back 0.40–0.56 with this embedding model — nothing came close to 0.75.
  `embed/cluster.py`'s default is now 0.5, `stb synthesize --threshold` exposes
  it, and even at 0.5 some true near-duplicates (0.498) still land in separate
  clusters, producing redundant candidate rules rather than one merged rule.
  Small general-purpose embedding models compress semantic distance more than
  intuition suggests — don't trust a threshold you haven't measured against
  your actual model.
- **A 0.5B model (Qwen2.5-0.5B-Instruct-4bit) failed at rule synthesis exactly
  as predicted** — not by being vague, but by returning structurally broken
  output (`"evidence_tier": ["A", "B", "C"]`, a list instead of one letter;
  placeholder-like imperatives such as `"write one rule"`). Pydantic validation
  caught every instance and `draft_rule_from_cluster` returned `None`, so
  nothing bad got written — the pipeline degraded to "0 rules drafted," not
  garbage rules. This is the gate working, not a bug, but it means the 0.5B
  tier is unusable for this stage.
- **A 3B model (Qwen2.5-3B-Instruct-4bit) drafted seven coherent, plausible
  candidate rules** from the same claims — correct JSON, sensible imperatives
  and rubrics, valid single-letter tiers. Quality was good enough to be worth a
  human's review time, not obviously wrong. This is the cheapest working
  configuration found so far; it's plausible something between 0.5B and 3B
  also works, but that wasn't tested.

Net: the mitigation in the paragraph above is confirmed correct, not just
theoretically reasonable — synthesis needs a model a full tier above what
`stb doctor`'s basic round-trip needs, and the threshold guess needed real
measurement, not just a reasonable-sounding number.

### 12. The conflict detector is the least certain component

Detecting that two imperatives are incompatible requires the model to reason
about logical compatibility of prescriptions — harder than clustering by
similarity. The three hand-written conflicts in `seed/rules.yaml` are deliberate
test fixtures for exactly this, including one that is a *tier* conflict rather
than a logical one (`use-their-name` vs `no-boomerasking`), which similarity
search will not find at all.

**Fallback if the model can't do it:** surface near-neighbour rule pairs with
diverging imperatives and let you judge. Lower ambition, still useful, and the
conflict log stays the app's best artifact either way.

**Tested live in Phase 3 (2026-09-22), with the 3B model above:** this is the
component that disappointed. The default similarity band (0.55–0.92) also
needed recalibrating down to 0.4–0.85 for the same reason as #11's clustering
threshold — measured similarity between genuinely related rule imperatives
topped out around 0.51. Once candidates were actually being found, though, the
judge itself was unreliable: **all 9 candidate pairs from the live run were
judged `"conflict": true`**, including pairs with no real tension at all
("follow Celeste Headlee's tips" vs "start questions with who/what/when") —
each with a fluent but confabulated note explaining a contradiction that isn't
there. Rewriting the prompt with an explicit contrastive example (one
worked "not a conflict" case, one worked "genuine conflict" case) did not fix
it — same 3B model, same false positive, on a pair a human would reject in two
seconds. This looks like a harder failure mode than #11's: the model isn't
short of information the way it was for evidence tiers, it's just bad at the
specific judgment call, and a clearer prompt didn't move it.

This validates the fallback above rather than requiring a new one — the
proposed resolution is never auto-applied, `resolution` is only ever written
by a human (see the non-negotiable in CLAUDE.md), and a false "conflict: true"
costs a few seconds of review, not a corrupted rule set. But budget more
review time here than for rule candidates, and don't assume a bigger-than-3B
model fixes this without testing it — #11's 3B result doesn't transfer to #12.

### 13. Fifteen seed rules is not enough, and three of the ten sources are paywalled

`src_sandstrom_2022_intervention` (Elsevier), `src_brooks_talk_book` and
`src_fine_small_talk` (books), `src_hbr_keys_great_conversation` (HBR) may all
resist ingestion. The five A-tier rules currently rest on four papers, two of
which are freely available.

**Not blocking:** six of ten sources are open-access PDFs or free web pages, and
that's enough to validate the pipeline. But the rule set stays thin until you
supply the practitioner material — which is also the material you originally
described wanting (the masters and self-proclaimed experts). **Sending me
specific links, transcripts, or people you want covered is the highest-value
thing you can do next.**

### 14. Whether you'll use it

The Sandstrom result says the active ingredient is volume of low-stakes real
attempts. An app can schedule and score those; it cannot make them happen. The
pre-brief/debrief loop is the part that touches reality, which is an argument for
not leaving it until Phase 6 — if Phases 4–5 turn out to be pleasant and Phase 6
never ships, you will have built a very well-sourced way to avoid talking to
anyone.

**Worth considering:** pulling the debrief log forward to Phase 4, before drills.
It is the cheapest piece in the whole project (a text box and an LLM extraction
call) and the only one that measures the thing you actually want.

### 15. The judge/generate split from #11–#12 held up again in Phase 4

**Tested live (2026-09-22)**, same 3B model (`Qwen2.5-3B-Instruct-4bit`) that
drafted good rules in Phase 3. Drills split cleanly along the same fault line
#11 and #12 already found: *generating* a stimulus was fine once prompted
correctly; *judging* a response against the rubric was shakier — the same
model that writes well doesn't reliably grade well.

- **Stimulus generation needed one prompt fix.** The first version asked for
  "a line a conversation partner might say" and got back things like *"So,
  what's the rule you're practicing today?"* — a meta-comment, not something
  to react to. The rule this drill tests ("ask about what they just said")
  only makes sense against an answer-shaped stimulus, so the prompt now says
  so explicitly ("their own statement... never a question aimed back at the
  practicer"). Fixed it in every subsequent sample.
- **The judge sometimes nests its own output**: asked for one flat JSON array
  with one element per rubric item, it returned `[[item1], [item2]]` —
  each item correctly formed but wrapped in its own single-element array.
  `practice/drills.py` now flattens one level defensively rather than
  dropping every item (which is what happened before the fix — the whole
  drill silently graded "failed" regardless of the actual response).
- **The verify gate caught a real hallucinated "yes" post-fix**: the judge
  marked `no_topic_jump` passed but supplied `quote: ">"` — a single
  character that isn't in the response at all. `verify_claim` correctly
  rejected it and the item was scored failed. This is the same mechanism as
  #12's conflict-judge finding: the model's boolean verdict is not
  trustworthy on its own, and here the gate is what makes that safe rather
  than just noted as a risk.
- **Net effect on a real drill**: a clearly good response ("what trails have
  you been exploring?") sometimes scored one rubric item genuinely passed and
  the other correctly rejected for a bad quote — an honest partial credit,
  not a clean pass. Expect drills to under-credit good responses more often
  than they over-credit bad ones; that's the intended failure direction.
- **Lesson naming is the roughest edge, and the lowest-stakes one.** At
  `temperature=0.3`, about 1 in 4 calls returned a name mixing English and
  garbled other-language characters (e.g. `"Question接力跟进"`). No fix
  applied — lessons have no accept/reject gate (docs/PLAN.md §2 Stage 4:
  "generated... then hand-edited"), so a bad name is exactly what that
  hand-edit step is for. Verified live: editing `lessons/<id>.yaml` directly
  while `stb serve` was running changed what the web UI showed on the next
  request, no restart or sync step needed — the YAML-only design in
  store/repo_lessons.py delivers on that promise for real, not just in
  theory.
