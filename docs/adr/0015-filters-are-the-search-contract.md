# 0015. Filters are the search contract, whoever fills them in

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

Search has to work with plain keywords and, when AI is on, with questions in ordinary words. People also need to see and
correct how a question was read.

## Decision

Search takes one `Filters` object (`whatson/search.py`), and always runs as SQL and FTS5 queries over the local data.

- `basic_filters` fills it from keywords.
- `Interpreter.interpret` fills it from a question (ADR 0016).
- The browser sends it back when someone edits the chips. That replays the search without asking the AI again, and
  `parse_filters` treats it as untrusted: strictly typed and bounded.

## Consequences

- AI can't add a result: it only shapes a query, and the results always come from the database.
- With AI off or failing, search behaves the same way, just with a simpler reading of the words.
- A new kind of filter has to be added in several places: `Filters`, `FILTER_FIELDS`, `parse_filters`, the AI schema and
  prompt, and the chips.
- Some reading is rules on purpose. Plex's Live TV guide has no ratings or genres, so "kids" and "family" go by channel name
  on live TV. A decade in the text moves to the year filter, because "90s" never appears in a title.

## Alternatives

**Inferred:** letting AI write queries or answer directly would break ADR 0016's rule. Not on record as having been
weighed.

## Where it lives

`whatson/search.py`, `/api/search` in `whatson/app.py`, `whatson/static/js/search.js`, `tests/test_core.py`.
