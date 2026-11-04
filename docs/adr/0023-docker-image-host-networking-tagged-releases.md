# 0023. A Docker image with host networking, published from tags

- **Status:** Accepted
- **Date:** 2026-11-03

## Context

People run WhatsOn on home servers, including Raspberry Pis and Unraid. The app has to reach each TV directly on the LAN
and find TVs through mDNS.

## Decision

- **Docker first.** One image, published to `ghcr.io/whatson-app/whatson` for amd64 and arm64. It includes both AI SDKs, so
  turning AI on needs no rebuild.
- **Host networking,** so the container can reach TVs on the LAN.
- **Data in `/data`:** the database, keys and TV certificate.
- **Unraid template** in `deploy/unraid/`, so it shows as an ordinary Unraid container.
- **Tagged releases.** Pushing a `vX.Y.Z` tag publishes `:X.Y.Z`, `:X.Y` and `:latest`, runs them and creates a GitHub
  release from that version's changelog section. The workflow first checks that the tag, both version files and the
  changelog agree. Only maintainers tag.

Versions follow semver. A release normally bumps the last number. The middle one goes up for a big step, or for something
people must act on.

## Consequences

- Host networking gives the container the host's network, and port 8430 is taken on the host directly.
- The image is larger for people who don't use AI.
- If a step before the last fails, no GitHub release is created.
- `tests/test_release.py` and `tests/test_unraid.py` keep these files in line.

## Alternatives

**Inferred:** bridge networking with mapped ports wouldn't carry mDNS discovery or easily reach TVs. Not on record as having
been weighed.

## Where it lives

`Dockerfile`, `compose.yaml`, `deploy/unraid/whatson.xml`, `.github/workflows/release.yml`, `scripts/release_notes.py`,
CONTRIBUTING's "Releases".
