# WhatsOn documentation

Start with the [README](../README.md) to install and use WhatsOn, and [CONTRIBUTING.md](../CONTRIBUTING.md) to work on it.

| Document | What it covers |
|---|---|
| [Architecture](architecture.md) | How the pieces fit, every module, and the main flows |
| [Decisions (ADRs)](adr/README.md) | Why it's built this way, and when to write a new ADR |
| [API](api.md) | Every HTTP route and the conventions they share |
| [Data model](data-model.md) | The SQLite tables and saved settings |
| [Configuration](configuration.md) | Every environment variable |
| [Integrations](integrations.md) | What WhatsOn uses from each outside service, and what it needs |
| [Front end](frontend.md) | The modules, routes and conventions in `whatson/static/` |
| [Testing](testing.md) | What each test file covers and what the tests can't tell you |

## Keeping these up to date

These pages describe how things work now, so they change in the same pull request as the code. ADRs explain why, and an
accepted ADR isn't rewritten. See [When an ADR is needed](adr/README.md#when-an-adr-is-needed).

`tests/test_docs.py` fails when a route, module, table, setting or environment variable isn't documented, or when a link
or path is broken.
