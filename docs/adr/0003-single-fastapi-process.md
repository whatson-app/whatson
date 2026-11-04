# 0003. One FastAPI process with background tasks

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

The server waits on slow things most of the time: media servers, TVs, ESPN and AI providers. **Inferred:** one household
generates little traffic, and people self-hosting it shouldn't have to run a queue, a cache or a second container.

## Decision

Run one async FastAPI process under uvicorn. Background work runs as asyncio tasks started in `lifespan` in
`whatson/app.py`: the guide and library refresh, the Trakt sync, Plex sign-in renewal, and closing idle TV connections.
Shared objects live on the `state` singleton in `whatson/state.py`.

Keep dependencies to the short list that `tests/test_guards.py` checks. A new one needs an agreed issue.

## Consequences

- Install is one container, with no other services.
- Some state is memory-only: the route cache, Plex sign-ins in progress, the last channel tuned on each TV, the AI ranking
  cache. It's lost on restart, and **running more than one worker would break it**.
- Blocking work should stay off the event loop. Address checks in the settings routes and on each request run their DNS
  lookups in a thread. The check at start-up doesn't, since nothing is being served yet.
- A background task must survive its own failures. The refresh, Trakt and renewal loops catch errors, log and try again.

## Alternatives

**Inferred:** a task queue or separate worker. Neither is on record as having been weighed, and both add something to
run for no gain at this scale.

## Where it lives

`whatson/app.py`, `whatson/state.py`, `whatson/ingest.py`, [architecture.md](../architecture.md).
