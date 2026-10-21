# Need for automation: go-ethereum issue triage metrics

**Measured:** every issue (not PR) opened in `ethereum/go-ethereum` from 2025-10-15 to
2026-10-14 (12 months), collected 2026-10-20T17:10Z through the GitHub GraphQL search
API with each issue's comments, label, assignment and close events.

```sh
python3 evals/metrics/fetch_issues.py --since 2025-10-15 --until 2026-10-14   # writes evals/metrics/data/
python3 evals/metrics/compute_metrics.py                                     # prints the table below
```

## Results (222 issues by non-maintainers, out of 245)

| Metric | Value |
|---|---|
| Issues per week | mean 4.7, busiest week 13 |
| Time to first maintainer response (responded issues, n=158) | median **44.8 h**, p75 172 h, p90 752 h |
| Got any maintainer response within 24 h / 72 h / 7 d | 29% / 43% / **53%** |
| Within 30 d (issues at least 30 days old, n=191) | 65% |
| Never got a maintainer response (as of collection) | **64 (29%)**, of which 40 are still open and 26 are older than 30 days |
| First maintainer action was a close, with no comment before it | 76 of 158 (48%) |
| Arrived without a template label | 99 (45%); 39% of these never got a response, versus 20% of labelled issues |
| Issues that ever got a maintainer-applied label | **7** (`status:triage` ×6, `website` ×1) |
| PRs opened in the same window (for scale) | 2,169 |

**Reading:** volume is modest, but first responses are slow and uneven. Half of the
external issues wait more than a week for any maintainer action, labels are effectively
only the ones templates apply, and many first "responses" are silent closes (spam, support
questions and duplicates that a first pass could have flagged on day 0). Core maintainers
spend their attention on 2,000+ PRs a year, so the first pass on issues falls through.

## Definitions

- **Maintainer**: a login with MEMBER/OWNER/COLLABORATOR association on any issue or
  comment in the window, any upstream CODEOWNERS handle, or anyone who labelled, assigned
  or closed someone else's issue (which requires triage permission). That gives 14 people.
- **First response**: the earliest comment, label, assignment, close or duplicate-marking
  by a maintainer who is not the author. Labels applied by the template, by the author,
  do not count.

## Limitations

- **Survivorship**: issues GitHub deleted as spam are missing, so spam volume is understated.
- **Right-censoring**: young issues have had less time to receive a response. The 30-day
  row only counts issues at least 30 days old; the others use all 222.
- **Maintainer identity is inferred.** Private org members show up as CONTRIBUTOR; the
  closer/labeller rule recovers most of them, but a helpful non-maintainer comment does not
  count as a response.
- **A close is not always triage.** A close caused by a merged fix PR counts as the first
  response, so the time to *triage* (as opposed to *resolution*) may be longer than shown.
- **Out-of-band contact is not seen**: replies on Discord and work done in linked PRs without
  an issue comment are invisible here.
- **One repository, one year**: the numbers describe go-ethereum's tracker, not open source
  in general, and the year includes two hard-fork cycles (Fusaka, Amsterdam).
