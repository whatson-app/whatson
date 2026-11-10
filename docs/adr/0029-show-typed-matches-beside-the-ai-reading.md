# 0029. Show matches for the words as typed beside the AI's reading

- **Status:** Proposed
- **Date:** 2026-11-10

## Context

With AI on, `/api/search` searched only the AI's reading of the question (ADR 0015, ADR 0016). A reading can be wrong in a
way the person can't see past: the prompt tells the model to expand team nicknames, so a search for an episode named "Duck
Duck Loon" became a search for an Oregon Ducks game, and the episode never showed. Removing chips couldn't bring it back,
because the person's own words were gone from the filters.

## Decision

When AI read the question, search also runs the keyword reading (`basic_filters`) of the words as typed, and shows those
matches first.

- `/api/search` returns them in `typed`, with `text` set to the words. Anything they found is taken out of the AI's
  results (`search.split_typed`), so nothing shows twice. `typed` is `null` when the words found nothing, and always
  `null` without an AI reading.
- Chips replayed from an AI reading send the question along, so the typed matches stay while the person edits the chips.
- The results page heads the two groups "Matches for “…”" and "More from the AI's reading". With no typed matches, it
  looks as it did before.
- `/api/answer` lists the typed matches first among the matches the AI answers from.

## Consequences

- What the person typed is always searched for, whatever the AI makes of it. The AI can add results, never hide them.
- Each AI search runs a second set of local queries. They're SQLite and FTS5 over the local copy, so the cost is small.
- Questions in ordinary words mostly find nothing as typed, because keyword search needs most of the words to match. When
  they do find something (a word that is also a title), it shows above the AI's reading, which can push the better answer
  down the page.
- Titles to get from Radarr and Sonarr still use the AI's reading.

## Alternatives

- **Skip the AI when the words name a title in the guide or library.** Fixes the reported case, but a title that isn't in
  the guide or library right now still goes to the AI, and a question that happens to match a title loses the AI's reading.
- **Give the AI candidate titles from the guide and library to read the question against.** Sends titles to the AI provider
  on every search, which needs its own decision, and the AI could still misread them. Not done.
- **Only tell the AI to keep titles as typed.** Depends on the model following it, and a test can't hold it to that.

## Where it lives

`search.split_typed` in `whatson/search.py`, `/api/search` in `whatson/app.py`, `/api/answer` in `whatson/routes.py`,
`whatson/static/js/results.js`, `whatson/static/js/search.js`, `tests/test_core.py`. Builds on ADR 0015 and ADR 0016.
