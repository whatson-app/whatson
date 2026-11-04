# 0001. Record design decisions as ADRs, and make them part of every change

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

WhatsOn's design was spread across `AGENTS.md`, code comments, guard tests and pull request text. The rules were
written down, but the reasons mostly weren't. A contributor, human or AI, could see what they mustn't do without
seeing why, or which trade-offs had already been weighed.

## Decision

Keep Architecture Decision Records in `docs/adr/`, one decision per file, numbered in order, using
`docs/adr/template.md`.

A change must **write an ADR** when it makes or reverses a design decision, as listed in
[When an ADR is needed](README.md#when-an-adr-is-needed). A change must **review the ADRs** for the area it touches, and
the pull request says which ones it read. Code that goes against an accepted ADR must either change, or supersede that
ADR in the same pull request.

An accepted ADR is not edited except for its status and links to later ADRs. To change a decision, write a new ADR and
mark the old one superseded.

The reference docs in `docs/` describe how things work now, and change in the same pull request as the code.

ADRs 0002 to 0024 were written after the fact, on one date, from the code, comments, docs and commit history. They
record what the project does and the reasons on record. Anything marked **Inferred** is a reason or alternative that
isn't written down anywhere and was worked out from the code, so a maintainer may want to correct it.

## Consequences

- Every design change costs a little more writing, and reviews have one more thing to check.
- Reasons survive after the people and conversations behind them are gone.
- Rejected ideas stay rejected for a stated reason, or get reopened on purpose.
- `tests/test_docs.py` checks the format, the index, links and that the reference docs cover the code. No test can tell
  whether a change needed an ADR, so that part rests on the pull request template and the reviewer.

## Alternatives

- **Keep reasons in pull request text.** Hard to find, and tied to the hosting site.
- **One long design document.** Decisions lose their dates and it's unclear what replaced what.

## Where it lives

`docs/adr/README.md`, `docs/adr/template.md`, `AGENTS.md`, `CONTRIBUTING.md`, `.github/pull_request_template.md`,
`tests/test_docs.py`.
