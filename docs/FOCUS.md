# Focus plan: prove one loop in smalltobig

As of 2026-11-19 · Status: proposed

## Why

The combined system went wide (live audio, transcription, Q&A, goal tracking,
spoken practice, suggestions, scoring, debriefs) before any of it was shown to help
someone have a better conversation. The judge has only been checked against a few
scripted transcripts. This plan narrows the work to one workflow in smalltobig's web
UI, measures it with real use, and expands only from evidence.

## The one loop

**Meeting strangers at an event (`cold_networking`), rehearsed with Sarah.** Sarah
covers this domain, and its phrasings come from the original tested transcripts.

1. **Prepare.** Fill in the profile once, then open a prep card for the event
   (`/htmsw/prep/new`).
2. **Rehearse.** Rehearse once with Sarah and read the yes/not-yet for each step
   (`/htmsw/rehearse/new`).
3. **Real conversation.** Go to the event and use the card.
4. **Debrief within 24 hours** (`/htmsw/debrief/new`).
5. **Give feedback** on every rehearsal, debrief and prep card, using the form at
   the end of each page (PR #8).

## Scope

**In:**
- The HTMSW web pages above.
- `/htmsw/progress` and its feedback summary.
- Fixes to the judge, the debrief extractor, Sarah and the prep card that the
  feedback calls for.

**Paused until the go/no-go decision:**
- be-better feature work. The app stays as it is: bug fixes only, no new screens.
- New kinds of conversation and new partners, including a casual-acquaintance
  partner.
- The older evidence pipeline (sources, claims, rules, drills, `/prep`, `/debrief`).
  It is left alone, not removed.
- Per-stage cloud routing, voice, and any change of model.

**Fixed for the whole trial:**
- Model: Qwen-AgentWorld-35B-A3B-oQ4 with thinking off.
- The framework YAML, unless a fix is needed.

Change either one mid-trial and the feedback from before and after can't be
compared.

## Step 0: set up (about 2 days)

1. Merge PR #8 (tester feedback).
2. **Build a reference set of transcripts for the judge.**
   - Collect 10 or more labelled Sarah rehearsals and 6 or more debrief accounts,
     with the expected yes/not-yet for each step. Include a debrief where an offer
     was made, which the judge has missed before.
   - Run the set as an `mlx`-marked test.
   - Record the baseline agreement before the trial starts.
3. **Give each tester their own server.**
   - Each tester gets their own `STB_DATA_DIR` and port on the Mac mini, served on
     the Tailscale address only. The web UI has no login, so a shared server would
     mix testers' data.
   - Use `full` only with a tester's explicit agreement; otherwise use `abstracted`.
4. Write a one-page tester guide: the loop above, the time it takes, and what is
   stored.

## Step 1: run the trial (2 weeks)

- **Testers:** you plus 2 to 4 trusted people.
- **Each tester:**
  - at least 3 rehearsals;
  - at least 2 real conversations, each debriefed within 24 hours;
  - the feedback form every time.
- **Weekly review:** read the feedback summary on each tester's `/htmsw/progress`.
  Fix only what blocks the loop. A fix to the judge must pass the reference set
  before it ships.

## Go/no-go criteria

| Measure | Go if |
| --- | --- |
| Judge agreement, rehearsals | ≥ 85% of judged steps marked "right" |
| Judge agreement, real debriefs | ≥ 80%, and step 4 has no more than one "wrong not yet" across all testers |
| Reference set | No step below its baseline |
| Usefulness | ≥ 70% of sessions rated yes or somewhat |
| Completion | ≥ 60% of testers finish 2 real debriefs without being chased |
| Real-world use | At least half the testers say they used a line or step from the prep card in a real conversation |

## After the trial

- **Go:** pick one expansion, the one the most-ticked issue points to. For example,
  if writing the debrief is the main friction, a lighter way to debrief comes next,
  possibly from be-better. Write it up as a decision in `docs/DECISIONS.md` before
  building it.
- **No-go:** fix the piece that failed (the judge's instructions, Sarah, or the prep
  card), re-check it against the reference set, and run the trial again for one week.
  Nothing else is added in the meantime.

## Done means

- The go/no-go table has been filled in from real feedback.
- The decision is recorded in `docs/DECISIONS.md`.
- The next expansion, or the fix, is named.
