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

---

## Added after the initial design

### 15. Cloud models are supported, per stage, and never by accident

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
