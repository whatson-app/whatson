# 0002. Self-hosted on a home network, with no login

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

WhatsOn runs in a home, next to the TVs and media server it controls. Everyone in the house should be able to open it
on a phone and use it. It also holds keys to other services, which makes who can reach it the main security question.

## Decision

WhatsOn has no login and no accounts. It's meant for a trusted home network and must not be port-forwarded or put behind
a public reverse proxy. A login was considered and decided against, and shouldn't be added without a new ADR.

Protection goes where a login wouldn't help: other web pages driving WhatsOn through a browser (ADR 0006), keys
leaking (ADR 0007), and typed addresses reaching things they shouldn't (ADR 0008).

## Consequences

- Nothing to sign in to or manage, on any device.
- Anyone who can open WhatsOn can change settings, pair and control TVs, and add titles when adding is on. That's stated
  in the README and `SECURITY.md`, and it's out of scope for security reports.
- Actions with outside effects need their own switch, such as adding to Radarr and Sonarr (ADR 0017).
- Everyone shares one set of follows and favorites (ADR 0019).

## Alternatives

- **A login.** Decided against; the reason isn't on record. **Inferred:** it would add friction on every TV-side device
  in the home for a threat the deployment rules already exclude.

## Where it lives

`SECURITY.md`, the README's Security section, `AGENTS.md`.
