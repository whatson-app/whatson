# Architecture Decision Records

Each file here records one design decision: the situation, what was decided, and what it costs. They explain *why*. For
how things work now, see the [reference docs](../README.md).

## When an ADR is needed

Write one in the same pull request when a change does any of these:

- Adds, removes or replaces a dependency, outside service, build step or data store.
- Changes a rule in `AGENTS.md`, a guard in `tests/test_guards.py` or anything in its allowlists.
- Changes how keys, typed addresses, request checks or the busy check work.
- Changes a contract other code builds on: `Source`, `TVDriver`, `Filters`, or how storage is laid out.
- Adds a new kind of TV or media server.
- Sets a policy people will notice: what WhatsOn will or won't do, who can do it, or what it requires of them.
- Goes against, or replaces, an accepted ADR.
- Picks between real options, and the next person would reasonably ask why.

You don't need one for a bug fix that restores intended behaviour, wording, a new league or app in an existing list, tests,
or a change that follows an existing ADR. If you're unsure, ask in the issue, or write a short one.

## How to write one

1. Copy `template.md` to `NNNN-short-title.md`, using the next free number.
2. Set the status to **Proposed** and fill it in. A page is plenty. Say what it costs, not only what it gains.
3. Add it to the table below, and link it from the code it governs if that helps the next reader.
4. If it replaces an older ADR, set the old one's status to `Superseded by ADR NNNN`.
5. Set the status to **Accepted** once a maintainer agrees, before merging. If two pull requests pick the same number, the
   later one takes the next free number.

Never rewrite an accepted ADR's reasoning. Fix a typo or add a link, but change a decision with a new ADR.

**Status** is one of `Proposed`, `Accepted`, `Rejected`, `Deprecated` or `Superseded by ADR NNNN`.

## How to review them

**Contributors,** before you start and again before you open a pull request:

1. Read the ADRs for the area you're changing. The table below is sorted by number, and each ADR's last section lists its
   files.
2. If your change goes against one, change the code or supersede the ADR. Don't quietly do neither.
3. Name the ADRs you read in the pull request template.

**Reviewers:**

1. Does this change need an ADR that it doesn't have?
2. Does the code do what the ADR says, and does the ADR say what the code does?
3. Are the costs honest, and were real alternatives weighed?
4. Do the reference docs in `docs/` still match?

## Decisions

| ADR | Decision | Status |
|---|---|---|
| [0001](0001-record-decisions-as-adrs.md) | Record design decisions as ADRs, and make them part of every change | Accepted |
| [0002](0002-self-hosted-home-network-no-login.md) | Self-hosted on a home network, with no login | Accepted |
| [0003](0003-single-fastapi-process.md) | One FastAPI process with background tasks | Accepted |
| [0004](0004-plain-javascript-no-build-step.md) | Plain JavaScript modules, no build step and nothing from the web | Accepted |
| [0005](0005-local-sqlite-copy-rebuilt-on-refresh.md) | A local SQLite copy of the guide and library, rebuilt on each refresh | Accepted |
| [0006](0006-header-and-host-checks.md) | Stop other web pages with a required header and a host check | Accepted |
| [0007](0007-keys-stay-on-the-server.md) | Keys stay on the server and only go to the address they were saved with | Accepted |
| [0008](0008-check-typed-addresses-on-every-request.md) | Check typed addresses when saved and on every request | Accepted |
| [0009](0009-tv-driver-protocol-android-tv-first.md) | A TV driver protocol, with Android TV's remote protocol first | Accepted |
| [0010](0010-start-playback-with-plezy-links.md) | Start playback by sending Plezy an app link | Accepted |
| [0011](0011-ask-before-interrupting-a-tv.md) | Ask before interrupting a TV | Accepted |
| [0012](0012-one-media-server-at-a-time.md) | A source protocol, and one media server at a time | Accepted |
| [0013](0013-plex-sign-in-and-server-token.md) | Plex sign-in with JWTs, and the server token for the server | Accepted |
| [0014](0014-match-espn-games-to-listings.md) | Match ESPN games to guide listings by network and kickoff | Accepted |
| [0015](0015-filters-are-the-search-contract.md) | Filters are the search contract, whoever fills them in | Accepted |
| [0016](0016-ai-is-optional-and-never-invents.md) | AI is optional, and only reads what it's given | Accepted |
| [0017](0017-radarr-sonarr-add-and-search-only.md) | Radarr and Sonarr: add and search only, with no Seerr mode | Accepted |
| [0018](0018-trakt-stays-out-of-the-interface.md) | Trakt stays in the code but out of the interface | Superseded by ADR 0027 |
| [0019](0019-one-household-shared-settings.md) | One household, with shared settings | Accepted |
| [0020](0020-learn-each-tvs-apps.md) | Learn each TV's apps, and open them by link | Accepted |
| [0021](0021-rules-enforced-by-guard-tests.md) | Enforce the rules with guard tests and one check command | Accepted |
| [0022](0022-public-repo-privacy-and-ai-contributions.md) | No real home data in the repo, and people answer for AI contributions | Accepted |
| [0023](0023-docker-image-host-networking-tagged-releases.md) | A Docker image with host networking, published from tags | Accepted |
| [0024](0024-interface-conventions.md) | Interface conventions: tokens, both themes, phone width, plain words | Accepted |
| [0025](0025-a-plex-home-user-for-each-tv.md) | A Plex Home user for each TV | Proposed |
| [0026](0026-how-sports-scores-refresh.md) | Sports scores refresh by polling, on two timers | Proposed |
| [0027](0027-trakt-back-in-the-interface.md) | Trakt is back in the interface, as an optional section under More | Proposed |
