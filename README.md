# From Small to Big

A local-first app for getting better at small talk.

It takes the advice of people who are good at conversation — researchers,
practitioners, self-proclaimed experts — and turns it into a set of rules **you
have endorsed**, each traceable to the exact sentence it came from. Then it
drills you on them, and tracks which ones survive contact with a real
conversation.

Runs on your machine by default, with on-device inference via
[MLX](https://github.com/ml-explore/mlx). Cloud models are supported too — chosen
per pipeline stage, so you can put a large model on the batch work that reads
published books without putting your conversation notes anywhere.

> **Status: planning.** The design is complete and the seed corpus is real; no
> application code is written yet. Start with [docs/PLAN.md](docs/PLAN.md).

## Why not just read the books

Three problems make "collect tips, generate lessons" produce a useless pile:

**The experts contradict each other.** Celeste Headlee says don't redirect to
your own comparable experience. Brooks & Yeomans (2025) found people *prefer*
partners who straightforwardly self-disclose over those who disguise disclosure
as a question. Both are defensible. Averaging them into "share, but not too
much" destroys the information. So conflicts are first-class records here, with
an arbitration log you write yourself.

**Evidence quality spans orders of magnitude.** "Ask follow-up questions" comes
from 2,000+ speed-dating conversations with a measured behavioral outcome. "Use
their name" is one author's untested assertion — presented as the single most
important rule of conversation. Both read like a tip. Every rule carries an
evidence tier (A–D) assigned from its source, and tier drives what you learn
first, rather than how confident the advice sounds.

**Local models confabulate attributions.** Ask a small quantized model what a
named author says and it will produce fluent, plausible, invented text. In a
system whose entire value is provenance, that is fatal rather than annoying. So
every extracted claim must contain a byte-exact substring of the stored source,
verified by string search rather than trust. A model that invents a quote fails
deterministically.

## How it works

```
sources → claims → rules → lessons → practice → field notes → mastery
           ↑         ↑                              ↑
     verbatim    you accept                  weighted 3× over
      anchor     or reject               anything the simulator says
```

Practice comes in three forms: **drills** on a single rule, **roleplay** against
a local model playing a stranger, and **pre-brief / debrief** around real events
you actually attend.

Two design choices worth calling out:

- **The roleplay actor and the scoring judge are separate model calls with
  separate contexts.** An actor that knows it is testing your follow-up
  questions hands you openings a real stranger never would, and you learn to hit
  a pitch nobody throws.
- **Rubrics are boolean plus a quoted span, never 1–10 scales.** A 4-bit model
  asked to rate warmth out of ten clusters on 7 and drifts with phrasing — noise
  that looks like data.

And one structural defense: a rule cannot reach top mastery on drills alone. The
obvious failure of an app like this is that you get very good at talking to a
language model.

## Where your data goes

A fresh install sends nothing anywhere. Every stage runs locally until you
change it, and you change it one stage at a time:

```bash
STB_LLM_BACKEND=local                  # default for everything
STB_LLM_BACKEND_SYNTHESIZE=openai      # this stage only
```

That granularity exists because the stages are not comparable. Extraction and
synthesis read the books and papers you ingested — published material, and the
place where a larger model genuinely helps. Drills and roleplay involve your own
practice text. Pre-briefs and debriefs are different in kind:

> Field notes describe real conversations with real, named people. Those people
> are not users of this app. They did not agree to have what they told you sent
> to a third-party API, and they cannot be asked afterwards.

So those two stages take a second, separate acknowledgement before they will use
a cloud backend — `STB_SEND_FIELD_NOTES_TO_CLOUD=i-understand`. Without it the
app runs them locally and tells you it did, rather than quietly obeying. Setting
a cloud backend to debug synthesis quality is a reasonable thing to do; it
should not, as a side effect, start shipping other people's confidences
offsite.

Any cloud-routed stage prints what leaves and what stays at startup, every run
— not a first-run dialog you dismiss once and forget.

Full reasoning: [docs/DECISIONS.md #15](docs/DECISIONS.md).

## Documentation

| Document | Contents |
|---|---|
| [docs/PLAN.md](docs/PLAN.md) | Architecture, data model, phasing. Start here. |
| [docs/DECISIONS.md](docs/DECISIONS.md) | Decisions taken, with costs; risks that can't be designed away. |
| [docs/seed/sources.yaml](docs/seed/sources.yaml) | Ten real sources, with acquisition notes. |
| [docs/seed/rules.yaml](docs/seed/rules.yaml) | Fifteen candidate rules with provenance, tiers, and three conflicts. |

**The seed rules are marked `verified: false`, and that is not a placeholder.**
They were derived from abstracts and secondary summaries, not from primary text
read in full. They exist to exercise the pipeline and give you something to
arbitrate on day one. Sourced rules arrive when real documents go through the
verify gate.

## Requirements

- Python ≥ 3.11
- **For local inference:** macOS on Apple Silicon, plus `mlx-lm` for chat and
  `mlx-embeddings` for embeddings. Installed via the `[mlx]` extra.
- **For cloud inference:** an API key for any OpenAI-compatible endpoint. Works
  on any platform.

Local and cloud are not exclusive — the common setup is local for everything
with one stage pointed at a larger hosted model.

## Licence

Apache-2.0. See [LICENSE](LICENSE).

The rules, lessons and notes you produce are yours. This project stores extracts
and paraphrases of copyrighted sources for personal study only — it has no
export or redistribution path for source text, by design.
