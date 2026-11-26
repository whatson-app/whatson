# 0031. Search tries the words as typed, then without their endings, then most of them

- **Status:** Proposed
- **Date:** 2026-11-26

## Context

A search for "I killed the bear" didn't surface the show "I Kill the Bear". Each search word is matched as the start of
a word, and "killed" isn't the start of "Kill". When no listing had every word, the guide and the library each fell back
on their own to any listing with all but one of the words, which for a two-word search means either word. So "bear"
filled On TV with Chicago Bears games and the library with every bear film, and the show sat third in its row under
them.

## Decision

`search.run` tries three levels in order, on the guide, library and episodes together, and stops at the first level that
finds anything in any of them:

1. **exact:** every word as typed.
2. **stem:** every word without a common ending (`search.stem`: -ing, -ed, -es, -s, kept to a stem of at least four
   letters before an undoubled consonant), so "killed" finds "Kill". Skipped when it's the same as the exact query.
3. **loose:** all but one of the words, the any-word fallback that was already there. Never for episode titles.

Games keep their own matching. A library title equal to the whole search comes first in the library. The library page's
own search box retries with endings dropped when the words as typed find nothing.

## Consequences

- A word with a different ending still finds the title, and the exact words always win: "wicked" finds *Wicked*, and
  never *John Wick*, because the stem level only runs when the exact words find nothing.
- One section's real match now stops the other sections from showing near misses. A search whose only real answer is in
  the library shows nothing on TV, where before it showed one-word matches.
- The stemming is a handful of English rules, not a real stemmer. Irregular forms ("ran" for "run") and other languages
  aren't covered.
- Up to three rounds of queries for a search that finds nothing. They're local FTS5 queries, so the cost is small.

## Alternatives

- **FTS5's `porter` tokenizer.** Stems properly, but changes how every table is indexed, and stems as typed too, so
  "wicked" would also find "Wick". Not done.
- **Keep the fallback per section, only add stemming.** Fixes the reported case, but leaves near misses filling one
  section while another has the real answer.

## Where it lives

`stem`, `LEVELS`, `run`, `search_guide`, `search_library` and `search_episodes` in `whatson/search.py`; `/api/library`
in `whatson/routes.py`; `tests/test_core.py`. Builds on ADR 0015 and ADR 0030.
