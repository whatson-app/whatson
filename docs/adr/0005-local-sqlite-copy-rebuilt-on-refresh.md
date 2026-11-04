# 0005. A local SQLite copy of the guide and library, rebuilt on each refresh

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The point of WhatsOn is searching across things a media server's guide can't search, such as finding a game by team when
the listing only names the sport. That needs guide, library and game data joined and indexed in one place. **Inferred:**
search also shouldn't have to wait on a server.

## Decision

Keep one SQLite file in the data folder, in WAL mode, with FTS5 indexes over airings and the library. A background
refresher pulls from the media server and ESPN on a timer. See [data-model.md](../data-model.md) for the tables.

Treat the tables in two groups:

- **Rebuilt:** `channels`, `airings`, `library`, `games` and the FTS tables are thrown away and rewritten on each refresh.
  There are no migrations for `library` and `games`: if the column named in `want` in `whatson/db.py` is missing, the
  tables are dropped and the next refresh fills them.
- **Long-lived:** `devices`, `follows`, `fav_channels`, `arr_adds`, `tv_apps` and `meta` hold what people set up. A new
  column on one of these needs an `ALTER TABLE` in `connect()`, or existing installs break.

Settings and saved keys go in the `meta` key-value table, not in new tables.

## Consequences

- Search is fast and keeps working while a server is down, using the last good copy.
- There's no migration framework to maintain.
- The guide can be up to a refresh old. Scores stay current between guide refreshes because airings keep a `game_id` and
  search joins `games`.
- `channels` and `airings` have no entry in `want`, so a new column on those needs one added, or an existing install keeps
  the old table.
- The database holds keys (ADR 0007), so its files are set to mode 600.
- One writer at a time, which is fine for one process (ADR 0003).

## Alternatives

**Inferred:** asking the media server on each search (can't search what it doesn't hold, and doesn't join games), or a
separate database server (one more thing to run). Neither is on record as having been weighed.

## Where it lives

`whatson/db.py`, `whatson/ingest.py`, `whatson/search.py`.
