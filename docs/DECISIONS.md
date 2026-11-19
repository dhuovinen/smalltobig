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

**Amended (2026-09-23):** this assumption was made without checking the local
port registry at `~/Projects/app-registry`, which is exactly the mistake the
entry above warns against — "pick the port... before writing code, not after."
3041 turned out to already be registered to an unrelated project
(`chs-milena`). Registering `smalltobig` there via `npm run reserve` assigned
**8028** instead (`backend-only`, single FastAPI process serving both the API
and the server-rendered UI, following the `lang-tutor` entry's precedent). The
web UI now binds **8028**, via `STB_PORT`. Moving it cost exactly what the
entry above predicted: one config default, plus the two docs and one test
that had hardcoded the old number.

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

### 16. Phase 5 roleplay, live: the actor is solid, the judge needed two real fixes and still has a ceiling

**Tested live (2026-09-22)**, `Qwen2.5-3B-Instruct-4bit`, against real
multi-turn conversations — not scripted fixtures.

- **The actor (practice/roleplay.py) worked well with no changes needed.**
  Across several conversations it stayed in character, gave plausible
  specific detail (conference sessions, an elevator ride, a moving box),
  and — genuinely encouraging — let a persona's hidden interest surface
  *implicitly* ("just a bit of a changeover here... stick around for now")
  without ever stating it outright, exactly the behavior docs/PLAN.md §2
  Stage 5 asks for ("a hidden interest the model reveals only if you find
  the thread"). Generation held up here the same way it did for rule
  drafting and drill stimuli in earlier phases — this model tier is fine
  at playing a character.
- **The judge (practice/judge.py) needed two real fixes before it produced
  usable output at all.** First: with a compound `(rule_id, rubric_id)` key
  asked of the model, a single-rule session came back with both fields
  blended into one garbled token (`"ask_followup"` for a rule id of
  `"ask-follow-up-questions"` and a rubric id of `"asked_followup"`) —
  even though the model had found a genuinely valid, verifiable quote for
  the judgment. Rewrote matching to use a plain 1-based position number
  instead of asking the model to echo any id string back at all — the
  model only has to say *which numbered item* it's judging, never
  reproduce an identifier. Second: with the id-based prompt gone, the
  model started dropping the JSON object braces entirely — replies like
  `["passed": true, "quote": "..."]`, syntactically invalid and
  deterministic (same malformed shape on 3 repeated calls at
  `temperature=0`) rather than occasional. Adding one concrete worked
  example of the exact array-of-objects shape to the system prompt fixed
  it completely, verified against the same transcripts that had failed.
- **Post-fix, a plain false positive surfaced that neither fix (nor the
  verify gate) can catch.** Given a response that ignored the partner's
  travel story and pivoted to "did you catch the game last night?", the
  judge marked the follow-up-question rubric item passed, quoting that
  literal question. `verify_claim` correctly confirmed the quote is real
  text from the response — and that's *all* it confirms. The judge had
  treated "the user's turn contains a question mark" as satisfying "asked
  a question referencing content from their previous turn," which is a
  semantic misread, not a fabrication. This is the sharpest statement yet
  of what the gate actually guarantees (docs/DECISIONS.md #3): it proves a
  quote is real, never that the reasoning attached to it is correct. A
  model confident and specific enough to cite real supporting text can
  still be wrong about what that text shows.
- **Net effect on mastery**: because `end_roleplay_session` is the first
  signal type other than drills, this phase is also the first time the
  box-5 ceiling in models/mastery.py actually mattered in a live run — a
  roleplay signal (success or failure) sets `has_non_drill_evidence=True`
  and drill successes can reach box 5 afterward, confirmed against real
  data end to end through the web UI (start → turn → end → session detail
  → mastery dashboard), not just the unit tests that first proved the
  mechanism.

### 17. Phase 6 pre-brief/debrief, live: prep-card generation was clean; debrief extraction needed a real fix for a new failure mode the verify gate cannot see

**Tested live (2026-09-22)**, `Qwen2.5-3B-Instruct-4bit`, against real
free-text accounts of conversations, with two accepted rules
(`ask-follow-up-questions`, tier A; `dont-multitask`, tier C).

- **`generate_prep_card` (practice/debrief.py) worked with no changes
  needed.** Given `"a coworker's farewell happy hour at a bar after work
  on Friday"` it proposed two specific, on-topic conversation starters
  and a natural exit line on the first try. Consistent with every prior
  phase's finding: free generation is this model tier's strength: the
  recurring weak point is judgment, classification, and extraction.
- **`extract_field_notes` found a new, third category of judge failure:
  correct evidence, correctly verified, attached to the wrong rule.**
  The initial prompt asked the model to freely pick which rules an
  account addressed. Given an account with genuine evidence for *both*
  rules — a follow-up question about a marathon, and phone-in-pocket
  behavior — it returned exactly one field note:
  `[{"rule": 1, "success": true, "quote": "I kept my phone in my pocket
  the entire time and just focused on the conversation."}]`. Rule 1 is
  `ask-follow-up-questions`; the quoted text is textbook evidence for
  `dont-multitask` (rule 2). The follow-up-question evidence in the same
  account was not extracted at all. The JSON was syntactically clean —
  this is not the nested-array or dropped-brace bug from #14/#16.
  `verify_claim` correctly confirmed the quote is real text from the
  account, and that is *all* it confirms: the gate has no way to check
  that a real, verified quote was matched to the *correct* rule number,
  only that it exists in the source. This sharpens #16's finding further:
  fabrication, wrong-boolean-on-correct-evidence, and now
  wrong-rule-on-correct-evidence are three distinct failure shapes the
  gate stops, doesn't stop, and can't stop, respectively — none of them
  interchangeable, and only the first is fully covered by exact-match
  verification.
- **Fix: replaced free selection with a one-rule-at-a-time walk.** The
  prompt now lists every rule and requires exactly one JSON element per
  rule, each with an explicit `"addressed": true|false` flag, rather than
  letting the model choose which rules to report on. Retested against the
  same account: `dont-multitask` correctly matched to the phone quote,
  and `ask-follow-up-questions` correctly marked `"addressed": false`
  instead of stealing the phone quote — misattribution did not recur
  across repeated retests. Verified again end to end through the real
  `/debrief` web route (not just the unit-tested function): the note
  landed on `dont-multitask`, mastery updated to box 2 / score 3.0 (the
  field-note weight from docs/PLAN.md §2 Stage 6, distinct from a drill's
  0.5 or a roleplay's 1.0), and the quote appeared correctly on
  `/field-notes`, `/rules/dont-multitask`, and `/mastery`.
- **The fix traded a wrong answer for a safe non-answer, not for a
  complete one.** Isolating the follow-up-question evidence alone (no
  phone mention in the account at all), the one-at-a-time prompt still
  did not recognize `"I asked her what got her into running in the first
  place"` as follow-up-question evidence — it returned `"addressed":
  false` rather than misattributing it. A more explicit paraphrase of the
  same evidence (`"tell me more about that, what was the best part?"`)
  *was* recognized correctly. So the fix closes the dangerous failure
  mode (wrong rule, silently accepted) but does not close the safe one
  (real evidence missed on subtler phrasing) — consistent with #14 and
  #16's pattern that this model tier under-credits before it
  over-credits, which is the failure direction the design can tolerate:
  a missed field note costs nothing, since nothing became a practised
  rule without it (docs/DECISIONS.md non-negotiable #2 in CLAUDE.md); a
  misattributed one would have quietly corrupted mastery for the wrong
  rule.

---

## Added after the initial design

> Renumbered on merge (2026-11-16): these were #15–#20 on `origin/main`, which
> collided with the Phase 4–6 findings above. References in REQUIREMENTS.md,
> IMPLEMENTATION.md, PLAN.md, README.md and CLAUDE.md were updated to match.

### 18. Cloud models are supported, per stage, and never by accident

Both local and cloud backends are first-class. The choice is made **per
pipeline stage**, not once globally, because the stages do not carry remotely
comparable risk.

| Stage | What would be sent to the provider | Whose words are they |
|---|---|---|
| `extract` | Chunks of ingested sources | Published authors |
| `synthesize` | Claim paraphrases, for clustering and rule drafting | Published authors |
| `conflicts` | Rule imperatives | Published authors |
| `drill` | Your written answer to a prompt | Yours |
| `roleplay` | Your turns in a simulated conversation | Yours |
| `judge` | A roleplay transcript | Yours |
| `prebrief` | Who you are about to meet and what you plan to say | Yours **and theirs** |
| `debrief` | Your account of a real conversation that happened | Yours **and theirs** |

The top three rows process published books and papers. Sending those to a
hosted model is an ordinary API call over material that is already public, and
it is exactly where a larger model earns its cost (see #11 — rule synthesis is
the hardest reasoning in the project and the step most likely to defeat a 4-bit
8B model).

The bottom two rows are categorically different, and not because they are
embarrassing. **They contain information about people who are not users of this
app.** A debrief saying who you spoke to at an offsite, what they told you about
their job, their divorce, their health — that is third-party personal data,
disclosed to you in confidence in a social setting, by someone with no idea this
software exists and no opportunity to object. Your own notes are yours to route
wherever you like. Their words are not.

**Decision:**

- Default is `local` for every stage. A fresh install sends nothing anywhere.
- `STB_LLM_BACKEND` sets a global default; `STB_LLM_BACKEND_<STAGE>` overrides
  one stage.
- Routing `prebrief` or `debrief` to a cloud backend requires a **second,
  separate acknowledgement** — `STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand`.
  Without it the app refuses and runs those two stages locally rather than
  silently doing what was asked.
- Any cloud-routed stage prints what leaves and what does not, at startup, every
  time. Not a first-run dialog that gets dismissed and forgotten.

**Why a second acknowledgement rather than one more env var:** setting
`STB_LLM_BACKEND=openai` is a plausible thing to do while debugging synthesis
quality, and it is a reasonable thing to want. It should not, as a side effect,
begin shipping other people's disclosed confidences to a third party. The two
settings guard different decisions, so they are two settings, and the second one
states what it is consenting to in the value itself.

**Cost:** more configuration surface than a single switch, and a user who
genuinely wants everything in the cloud has to say so twice. Accepted. The
asymmetry is deliberate — the cheap path is the safe one.

**Warning text, startup, any cloud-routed stage:**

```
!  Cloud backend active

   synthesize, extract  ->  openai:gpt-5  (api.openai.com)
   everything else      ->  local  (mlx, 127.0.0.1:3140)

   Sent to api.openai.com: extracts of the sources you have ingested.
   Published material, not your notes.

   Staying on this machine: your drill answers, roleplay transcripts,
   pre-briefs and field notes.
```

**Refusal text, `prebrief`/`debrief` routed to cloud without the acknowledgement:**

```
!  Refusing to send field notes to a cloud model. Running these locally instead.

   Field notes and pre-briefs describe real conversations with real, named
   people. Those people are not users of this app. They have not agreed to
   have what they told you sent to a third-party API, and they cannot be
   asked after the fact.

   This is the most sensitive data From Small to Big holds. It is the one
   thing that stays on your machine unless you say otherwise in as many words.

   To route them to the cloud anyway:
       STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand

   Usually the better answer: leave these local and put only `synthesize` in
   the cloud. That is the stage a bigger model actually helps, and it reads
   published books rather than your notes.
```

The refusal **downgrades to local and continues**. It does not abort the run —
an error that blocks a debrief teaches you to stop writing debriefs, and the
debrief is the one part of this app that touches reality (#14).

---

### 19. HTMSW is the content; the ingestion pipeline is deferred

The original design derived its rules from ingested books because there was no authored
methodology. HTMSW supplies one, tested through role-play rather than literature review.

**Decision:** the framework ships authored, as YAML. `sources → claims → rules` moves to
Phase 6, where its job is to **validate and extend** the framework rather than produce it.

**Kept, not discarded:** the verify gate (#3), evidence tiers, and conflict records. The
seed corpus becomes the evidence base — see #23.

**Discarded:** lessons as the unit of work (replaced by scenarios), the generic scenario
list (replaced by the four domains), Leitner boxes (replaced by per-step counters), and
the TALK taxonomy as the organising spine (replaced by the four-step sequence).

---

### 20. Abstracted-only persistence

HTMSW requires that scenario data not be persisted. The earlier design required field
notes stored and weighted 3:1 for mastery. Directly incompatible.

**Decision:** persist the abstraction, discard the prose.

- **Persisted:** persona-cluster flags, domain, per-step attempt/success counters.
- **Never persisted:** any free text written by the user or describing a third party.

The 3:1 weighting of real conversations over roleplay survives (FR-54) — it was always a
weighting on *outcomes*, and outcomes are four booleans. Storing the words was never what
made it work.

**Cost:** you cannot re-read your own debriefs, and a counter cannot be audited back to
the conversation that moved it. Accepted. **Enforced by test**, not by intention: a
sentinel string written into intake must appear in no database column after close.

---

### 21. Prep is deterministic; roleplay is the only AI surface

The framework specifies pre-built example phrasings the user adapts, not freeform lines
generated live. Taken literally, that makes the prep card pure composition from curated
data.

**Decision:** the prep card makes zero model calls and zero network calls (FR-34).

**Why it is load-bearing:** the MVP ships prep and roleplay together, which doubles the
scope and the risk. Making prep deterministic isolates *all* model risk in roleplay. If
the judge disappoints, the prep half still ships and is independently useful. It also
means the most privacy-sensitive path — target-person intake to prep card — never sends
anything anywhere.

**Cost:** phrasings must be written by hand, and coverage gaps are real rather than
papered over by generation. `phrasings.yaml` marks gaps explicitly.

---

### 22. Target-person intake joins the field-note guard; URL fetch is opt-in

#18 guarded `prebrief` and `debrief`. HTMSW introduces something more identifying than
either: free text about a **named** third party, plus an optional link to their profile —
a name, an employer, a bio, about someone who has no idea this app exists.

**Decision:** `intake` joins `prebrief` and `debrief` behind
`STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand`.

**Second, separate issue.** Fetching a supplied LinkedIn URL discloses *to LinkedIn* that
someone is researching that person, from this user's IP, at this time — a disclosure the
user did not ask for by pasting a link. The fetch is therefore **opt-in per scenario with
consent at the point of use**, never a background fetch on paste, and the consent text
says what the fetch reveals and to whom.

---

### 23. Framework elements carry evidence tiers, including the weak ones

Reviewing HTMSW against the seed corpus produced two findings worth recording.

**Step 2 is independently corroborated by two A-tier studies.** Its definition —
*"engages directly with what the other person revealed, rather than pivoting back to the
user"* — splits into two separate findings already in `seed/rules.yaml`:
`ask-follow-up-questions` (Huang et al. 2017) and `no-boomerasking` (Brooks & Yeomans
2025). Two research groups, different methods, landing on the two clauses of one
hand-written step. Step 2 is the highest-confidence element of the framework.

**Step 3 resolves seed conflict #1.** Headlee's `dont-equate-experiences` against Brooks's
`straightforward-self-disclosure` was logged unresolved. The connecting micro-disclosure
is the resolution, demonstrated in the Sarah transcript: match a small vulnerability with
a **comparable, smaller** one that connects rather than one-ups, and keep it off heavy
topics. That conflict record is updated to `resolved`.

**But the rest of the framework rests on two self-authored transcripts.** Step 4, the
domain-pacing calibration, and generosity-without-reciprocity have no independent support.
Two role-plays, written by one person, un-blinded, outcome known in advance. That is a
starting hypothesis, not a validation.

**Decision:** tier framework elements honestly (REQUIREMENTS.md §2.5) — A for step 2, C
for steps 1 and 3, **D for step 4, domain pacing, and the generosity principle**. Build
the app to test them: per-step counters across domains are precisely the instrument, and
Phase 6 brings the literature to bear.

Tiering your own framework's weakest parts as D is uncomfortable and correct. The
alternative is an app that cannot tell you when it is wrong.

---

### 24. Privacy profiles: full-fidelity capture alongside abstracted-only

#18, #20 and #22 define the privacy design the product ships with. They say nothing
about how we find out what that design costs. To know whether abstracted-only
persistence is a good trade, we need to see what the app could do with **no loss of
information** (verbatim text, full attribution of who said what, detailed history) and
compare that with how it behaves under the restricted design.

**Decision:** the app runs under one of two **privacy profiles**, chosen per data
directory:

| | `full` | `abstracted` |
|---|---|---|
| Purpose | Baseline and research: capture everything, lose nothing | The product privacy model (#20, #22) |
| Persisted | Verbatim intake, target-person details and URLs, roleplay and real-conversation transcripts, debrief prose, field-note text, audio and transcripts from the macOS app, speaker attribution, timestamps, model request/response logs | Cluster flags, domain, per-step counters (FR-51) |
| Scenario data on close | Kept | Purged (FR-52) |
| Debrief | Prose stored, plus extracted outcomes | Outcomes only (FR-53) |

- **Setting:** `STB_PRIVACY_PROFILE=full|abstracted`, one setting per data directory.
  Choosing `full` needs **no further confirmations or per-session prompts**. Friction in
  the baseline would bias the very data it exists to collect.
- **Default:** `abstracted` for a fresh install, so the shipped behaviour is unchanged.
  Development and baseline installs set `full` once.
- **Separate stores:** each profile has its own data directory and database. Records
  carry the profile they were captured under. Nothing ever moves from an `abstracted`
  store into a `full` one. There is no "upgrade", because the information was never
  kept.
- **Abstraction is a projection, not a second code path.** `abstracted` stores exactly
  what `project(full_record)` returns, and the same function runs at write time in
  abstracted mode. A full-fidelity store can therefore be re-read through the projection
  at any time. Comparing "full" with "what abstracted would have kept" then needs no
  second run, and the difference is precisely what the privacy design discards. A test
  asserts that the projection of a full record equals what abstracted mode persists for
  the same input.
- **Always visible:** the active profile shows in the UI (nav bar, macOS app header) and
  in `stb doctor` output. A user is never unsure which model their data is under.

**Unchanged across both profiles:**

- **Egress.** Persistence and egress are separate axes. The cloud guard in #18/#22
  applies in both profiles: `full` decides what stays on disk, not what leaves the
  machine.
- The verify gate (#3), actor/judge separation (#4), boolean-plus-span rubrics (#5),
  the 3:1 weighting (FR-54), no telemetry (FR-56) and "purge everything" (FR-55, which
  purges the active profile's store).

**What this resolves:** the conflict between FR-51 and the Phase 6 code, which stores
field-note text. Phase 6 behaviour is effectively the `full` profile. The abstracted
profile is built as the projection on top of it, rather than by deleting what exists.

**Risks and costs:**

- **Recording other people depends on where the conversation happens.** A `full` store
  holds third parties' words with attribution, and with the macOS app, possibly audio.
  Consent rules vary by jurisdiction, so the app does not hard-code one:
  - **Florida (US):** every party must consent to a recording. Real conversations
    captured in `full` need that consent, or capture only your own side.
  - **Haiti:** per the project owner (2026-11-16), all-party consent is not required
    there. This is recorded as the owner's determination and was not independently
    verified here.
  - **Cross-border calls:** a call with someone located in Florida can bring
    Florida's rule into play even when you are recording from Haiti. The stricter
    location is the safe assumption.
  - **Roleplay and simulated baselines** involve no third party and are unaffected
    everywhere.
  If this becomes an app feature rather than a note, it should be a per-capture
  "consent obtained / not required here" flag stored with the record, not a global
  switch.
- **A `full` store is the most sensitive file the app produces.** It lives outside the
  repository (never under `STB_REPO_ROOT`), with owner-only permissions, and relies on
  disk encryption (FileVault) at rest.
- **Two profiles mean two test matrices.** The privacy tests (FR-50s) run under
  `abstracted`. The projection-equivalence test covers the relationship between the
  two profiles.

---

### 25. HTMSW rehearsal, live: what the judge got right, two bugs found, and thinking models

**Tested live (2026-11-16)** against Ollama on the Mac mini, with two scripted
conversations with Sarah. GOOD follows the four steps. BAD pitches, pivots to "did
you catch the game", then asks for an intro.

| Run | GOOD | BAD |
|---|---|---|
| 1, as first built | 3 of 4 passed | disclosure **wrongly passed** on "I'm a consultant… here's my card"; other 3 correctly missed |
| 3, after the fixes below | 3 of 4 passed (build-on, with a real partner quote) | 0 of 4, all correctly missed |

**What held up.** The structural checks in `htmsw.yaml` did their job. The
DECISIONS #16 failure, where a question mark was accepted as a build-on, cannot
recur: a build-on now needs a verbatim partner line, earlier in the transcript,
that it responds to. "Did you catch the game" fails that.

**The cost is false negatives.** The 8B judge sometimes leaves `partner_quote`
empty even when the user's line does respond to the partner, and the strict check
then records a miss. A concrete filled-in example in the prompt fixed this for
build-on but not reliably for step 3. A miss shows the reason ("no earlier line from
your partner was quoted") and is not a score, so this direction is the tolerable
one, as in #16.

**Bug 1, existing since Phase 5: the actor never received `private_instructions`.**
`practice/roleplay.py` built its system prompt from setting, warmth, verbosity and
hidden interest only, though `models/scenario.py` says the private instructions are
"fed to the roleplay actor". Live, Sarah invented a job as a magazine editor. Fixed,
with an assertion in `tests/unit/test_roleplay_actor.py`. This also changes the
older lesson roleplay, which now gets each scenario's backstory as intended.

**Bug 2: the disclosure check accepted credentials.** The FR-44 wording ("disclose
something about themselves") let a pitch count. Reworded in `htmsw.yaml` to ask for
an honest, modestly vulnerable admission and to exclude pitches, titles and
credentials. REQUIREMENTS.md FR-44 keeps the short form; the YAML is the source of
truth.

**Also: the actor writes stage directions** ("*leans slightly forward*") despite
being told not to. `htmsw_roleplay.clean()` strips multi-word spans in asterisks or
brackets and keeps single-word *emphasis*.

**Thinking models do not work with this client yet.** `qwen3.5:9b` and `gemma4:26b`
spend the whole `max_tokens` budget on hidden reasoning and return an empty answer
(Ollama puts the reasoning in a separate field). The actor allows 120 tokens, so every
partner line would be blank. `ministral-3:8b` (about 10 s a rehearsal turn, 10 s to
judge) answers directly and is what was tested. Until the client asks for reasoning
to be off, or budgets for it, use a non-thinking model for `STB_LLM_MODEL`.

---

### 26. Phase 4 built: profiles, projection, counters; per-stage routing deferred

**Built (2026-11-16):** DECISIONS #24 as code. `STB_PRIVACY_PROFILE` selects one of two
stores, `data_dir/htmsw-abstracted.db` and `data_dir/htmsw-full.db`. Both are created
0600, and a store refuses to open under the other profile. `record/projection.py` is
the single `project(record) → outcomes`. `abstracted` writes only that.
`full` writes it **and** the session (transcript, debrief account, consent, verdict
quotes, model request and raw reply). Counters are derived from the integer outcome
log rather than stored, so there is one table to purge and nothing to keep in sync.
Weights and levels are data (`htmsw.yaml` `progress`): a real conversation counts 3×,
and "Confident" needs two real successes, so rehearsals alone cannot reach it (FR-54).

**Live check (Ollama, `ministral-3:8b`):** one real debrief recorded under both
profiles produced identical `step_outcomes` rows in each store. The abstracted store
held four integer rows and no trace of the name in the account; the full store held
the account, the consent flag and the model's reply. The model once answered "yes"
with an empty quote; the gate refused it, and the reason now says so plainly rather
than "quote not in your account".

**Deferred: per-stage backend routing (#18, #22, FR-61..FR-64).** IMPLEMENTATION.md
lists a routing test under Phase 4, but no per-stage routing exists anywhere: one
`STB_LLM_BASE_URL` serves every stage, and everything defaults to local. It is a
separate feature with its own risk, so it gets its own change. `tests/test_privacy.py`
carries a skipped placeholder so it stays visible.

**Not changed:** the older Phase 6 `/prep`, `/debrief` and field notes. They predate the
profiles and still store text in `smalltobig.db`. Folding them into the profile model,
or retiring them in favour of the HTMSW versions, is an open decision.

---

### 27. Model provider is configuration; Qwen-AgentWorld 35B-A3B via omlx-serve tested live

**Change (2026-11-18):** provider URL, model, API key, thinking switch and timeout
are all `STB_LLM_*` settings, assembled in one place (`Settings.llm_options()`) for
every client. `STB_LLM_API_KEY` is sent as a Bearer header and held as a `SecretStr`,
so it never appears in printed or logged settings. Motivated by omlx-serve, which is
local but requires a key.

**Live check, same scripts as #25** (`Qwen-AgentWorld-35B-A3B-oQ4` on omlx-serve,
Mac mini, `STB_LLM_ENABLE_THINKING=false`):

| Run | ministral-3:8b (#25) | Qwen-AgentWorld 35B-A3B |
|---|---|---|
| GOOD rehearsal | 3 of 4 (step 3 missed: no partner quote) | **4 of 4**, partner quotes on build-on and connect |
| BAD rehearsal | 0 of 4 | 0 of 4 |
| Debrief (Priya account) | 3 of 4 (step 4: empty-quote "yes") | 3 of 4 (step 4: "account doesn't show this step") |
| Speed | ~10 s per turn, ~10 s to judge | ~1 s per turn, ~5 s to judge |

The partner-quote false negatives from #25 did not recur. With thinking off, no reply
came back empty. The debrief's step-4 miss looks like a false negative: the account
says "offered to check in with her next week, no strings". The debrief has no
structural checks to lean on, so it is the more model-sensitive surface. Worth
another look if it repeats.

omlx also answers on the Tailscale and LAN addresses (100.103.52.82, 192.168.1.112),
key-enforced, so be-better on the MacBook Air can use the same model for its live
suggestions.

---

### 28. Judge reference set and its baseline; step 4 does not recognise offers

**Change (2026-11-19, docs/FOCUS.md Step 0):** `evals/htmsw_reference.yaml` holds
10 hand-labelled Sarah rehearsals and 6 debrief accounts, with the expected verdict
for every step. `stb reference-check` runs them through the same judge and debrief
code the app uses and records nothing. `tests/unit/test_reference_set.py` checks
that the labels obey the rubric's structural rules, and its `mlx` test fails if any
step drops below the baseline below. The scripts behind #25 and #27 were never
committed; this set replaces them and includes their GOOD/BAD shapes and the
step-4 wording that #27 saw missed.

**Baseline** (`Qwen-AgentWorld-35B-A3B-oQ4`, thinking off; five runs). Temperature 0
is not fully deterministic on this server: the first two runs matched exactly, then
two rehearsal steps moved by one case. The test floor is the lowest score seen.

| Step | Rehearsals (range) | Debriefs | Floor |
|---|---|---|---|
| 1. Initial disclosure | 10/10 | 6/6 | 10, 6 |
| 2. Build-on question | 9–10/10 (wrong not yet) | 6/6 | 9, 6 |
| 3. Connecting micro-disclosure | 8–9/10 (wrong yes) | 6/6 | 8, 6 |
| 4. Earned ask | 9/10 (1 wrong yes) | **4/6 (2 wrong not yet)** | 9, 4 |

Every step-4 failure below occurred in all five runs.

**Findings.**

- **Debrief step 4 misses every offer.** Both accounts that end in a no-strings
  offer ("offered to check in with her next week, no strings"; "I could send her the
  physio's name") were scored "doesn't show this step". The step 4 check asks only
  whether "the ask" came after two exchanges. The framework's own coaching counts a
  specific, pressure-free offer, so the check wording is the likely cause, not the
  model. This is the #27 miss, now reproduced and explained.
- **An oversized disclosure passed step 3, and step 4 passed with no ask at all**
  (`oversized_connect`): a second disclosure about divorce and depression, after the
  partner mentioned not having time to run, was judged "connected and no larger".
  The same case passed step 4 although the user made no ask or offer.
- **One build-on is missed in some runs** (`question_before_disclosure`, 2 of 5):
  "What made you come anyway?" after "I nearly skipped tonight myself". Low priority.
- **Step 3's size check is weak.** Besides `oversized_connect` (every run), one run
  passed a second step-3 case that should have failed; that run's case list was not
  kept. `stb reference-check` prints the cases, so the next run will show if it recurs.

**Not changed yet.** Rewording step 4 in `htmsw.yaml` to name offers ("an ask, or a
specific no-strings offer") is the obvious fix. It is a framework change, so it gets
its own commit and must clear this baseline. The trial in FOCUS.md should not start
until that decision is made: real debriefs are where step 4 is judged most, and a
judge that never credits an offer would make the trial's step-4 numbers meaningless.

---

### 29. Step 3 and step 4 checks reworded; reference set now 16/16

**Change (2026-11-19):** the `ask_was_earned` and `connected_not_reset` checks in
`framework/htmsw.yaml` were reworded to fix the #28 findings. REQUIREMENTS.md FR
tables keep the short forms; the YAML is the source of truth, as in #25.

- **Step 4** now names both kinds of move: "a direct ask or a specific, no-strings
  offer", after two rounds of reciprocal exchange "in which both people shared
  something personal". It says that an ask after a pitch, a change of topic or no
  real exchange is not earned, and that making neither an ask nor an offer fails.
- **Step 3** now spells out "no larger": a personal share on the theme the partner
  raised, of similar weight. A brag, a credential, an unrelated topic or something
  much heavier does not pass.

**How it got there.** The first step-4 rewording (offers named, "reciprocal" left
implicit) credited both offers but let three cold asks pass: 8/10 and 5/6. It also
pushed step 3 to 7/10, below its floor, though step 3's text had not changed. All
four checks go to the judge in one prompt, so rewording one shifts how the model
reads the others. The "earned" wording fixed step 4. Rewording step 3 fixed the
three step-3 false passes.

**Result:** 10/10 on every rehearsal step and 6/6 on every debrief step, identical
across five runs. The `mlx` test floor is raised to that.

**Caveat: tuned on the cases that measure it.** Both wordings were written while
looking at these 16 cases, so 16/16 overstates how well the judge will do on new
conversations. The trial's per-step "was the judge right?" feedback is the real
held-out test. Add new cases from real disagreements as they come in, without
relabelling old ones, and expect the floor to come down.

**Knock-on:** the framework export's revision hash changes. be-better reads the
framework from the engine when connected; its bundled snapshot is stale until
`stb export-framework` (via its `scripts/update-htmsw-framework.sh`) is re-run.
