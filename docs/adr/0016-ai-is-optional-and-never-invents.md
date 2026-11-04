# 0016. AI is optional, and only reads what it's given

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

AI makes questions like "something funny for the kids, under 2 hours" work. But it costs money or a local server, it can
be slow or down, and a model can make things up. An app that names a channel that doesn't exist is worse than no answer.

## Decision

**Everything works with AI off.** Each AI feature has a fallback:

| Feature | What it does | Without AI |
|---|---|---|
| `interpret` | Question into search filters | Keyword reading |
| `answer` | One line from the matches found | No line |
| `rank` | Re-orders candidates, with a reason each | Rule order |
| `recap` | Three sentences from ESPN's play-by-play | The last plays |

**AI never invents results.** It only reads the question or the candidates it's given. `rank` drops any id it wasn't
given, and replies must fit a JSON schema.

- **Providers:** Claude, OpenAI, OpenRouter, or a local OpenAI-compatible server. The SDKs are optional extras, imported
  inside functions.
- **Failing fast:** calls have a timeout (30 seconds by default) and no retries, because search waits on them and a retry
  doubles the wait.
- **Off by default:** a provider with no key, or no model where one is required, stays off instead of failing.

## Consequences

- AI can't be required by any new feature, so each one needs a fallback designed from the start.
- Questions and candidates go to the chosen provider, and a local server is available for anyone who'd rather they didn't.
- Two SDK shapes to support behind `_json`.
- `tests/test_guards.py` fails on a top-level import of either SDK.

## Alternatives

**Inferred:** one provider only would be simpler, but self-hosters often want a local model. Not on record as having been
weighed.

## Where it lives

`whatson/ai.py`, `whatson/ai_settings.py`, `whatson/suggest.py`, `tests/test_suggest.py`.
