# Real-user usability study

**Status:** Recruitment-ready; no participant sessions completed yet

**Prepared:** 2026-07-25

**Owner:** Project maintainer

This plan replaces synthetic personas with a small, consent-based usability
study. Until a real person completes a session, this document is a protocol—not
research evidence. Results must never be backfilled from automated tests or an
AI review.

## Questions

1. Can a reader sign in and answer “What should I read now?” without help?
2. Do freshness, privacy, and outbound-catalog controls match what readers think
   they do?
3. Can a reader explain why a recommendation appeared and where its metadata
   came from?
4. Can keyboard, magnification, and screen-reader users complete the same core
   flow?
5. Does the interface describe books without implying an identity for an author
   or reader?

## Method and participants

Run five moderated usability sessions, 35–45 minutes each:

- the primary reader/self-hoster;
- a queer or trans reader who cares about anti-essentialist discovery;
- a keyboard, magnification, or screen-reader user;
- a privacy-conscious self-hoster;
- a catalog stakeholder such as a BookWyrm administrator, librarian, or
  small-press reader.

Recruit for relevant experience, not identity disclosure. Nobody needs to share
their real reading history: use the built-in demo library unless a participant
explicitly chooses otherwise.

## Privacy and consent

- Explain the purpose, voluntary nature, and note-taking before beginning.
- Do not record audio, video, names, account handles, or book histories by
  default.
- Store only pseudonymous task observations and participant-approved short
  quotes.
- Never commit raw session notes to this repository.
- Let participants skip any question and stop at any time.
- Delete working notes after synthesis and participant quote approval.

Suggested consent script:

> We are testing the dashboard, not you. Participation is voluntary. I will take
> brief pseudonymous notes about where the interface helps or gets in the way.
> You may skip a task or stop at any time. We will use the demo library unless
> you explicitly choose to use your own data. Is that okay?

## Session guide

### Warm-up — 5 minutes

1. How do you currently keep track of reading across devices?
2. When you want a next book, what information helps you decide?
3. What would make a private reading dashboard feel unsafe or untrustworthy?

### Tasks — 25 minutes

Ask participants to think aloud. Do not teach the interface unless they are
blocked for more than two minutes.

1. Sign in and tell me what you would continue reading tonight.
2. Explain how current the displayed information is.
3. Choose one recommendation and explain why it appeared.
4. Find the source of that recommendation’s descriptors.
5. Hide sensitive descriptors, then confirm what changed.
6. Find a particular title or author in the library.
7. Find whether catalog networking is off, current, stale, or degraded.
8. Sign out.

For an assistive-technology session, repeat tasks 1–8 using the participant’s
normal keyboard, zoom, contrast, and screen-reader setup.

### Reaction and wrap-up — 10 minutes

1. What felt trustworthy? What felt performative?
2. Was anything about the recommendation or diversity language uncomfortable?
3. What would make this useful weekly?
4. What is the one reason you would not use it?
5. What did I fail to ask?

## Measures and release thresholds

| Measure | Release threshold |
|---|---:|
| Sign-in completion | 5/5 without a blocker |
| Identify a current book | 5/5 within 30 seconds |
| Explain one recommendation and source | at least 4/5 without coaching |
| Find and use the privacy control | 5/5, with no stale/unredacted response |
| Find catalog network status | at least 4/5 within 60 seconds |
| Keyboard/assistive-tech core flow | 0 blocking defects |
| Privacy comprehension | 5/5 correctly state what can leave the instance |

Any privacy leak, inaccessible core task, or mistaken author-identity inference
is release-blocking regardless of aggregate task success.

## Observation template

Keep working notes outside the repository.

```text
Participant code:
Date / build:
Assistive technology (optional):

Task | Completed? | Time | Observed friction | Assistance given

Trust/privacy interpretation:
Recommendation explanation in participant's words:
Participant-approved quote, if any:
Release-blocking issue:
Other observations:
```

## Synthesis

After all five sessions:

1. Group observations by task and underlying need, not by participant identity.
2. Separate observed behavior from interpretation.
3. Count task outcomes; do not present five sessions as population statistics.
4. Rank fixes by severity and frequency.
5. Publish a dated, de-identified synthesis and mark this study complete only
   when every participant has reviewed any attributed quote.
