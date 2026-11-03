# Security

WhatsOn has **no login** by design and is meant for a home network. Anyone who can open it can change
its settings, control TVs and (when allowed) add titles to Radarr and Sonarr. Don't port-forward it or
put it behind a public reverse proxy. See the Security section of the README for what it does protect.

## Reporting a problem

Please report security problems privately, not in a public issue.

**How:** use [Report a vulnerability](https://github.com/whatson-app/whatson/security/advisories/new) on the
repository's Security tab. You'll get an answer within a week. Please give us a reasonable time to ship a fix before
you publish details.

**In scope:**
- Ways a web page could drive WhatsOn through someone's browser.
- Ways to read a stored key or token.
- Ways to make WhatsOn call an address it should refuse, or send a saved key to another address.
- Ways to edit or delete anything in Radarr or Sonarr through WhatsOn.

**Not in scope:** what someone can do after opening WhatsOn on your network, or after you've exposed it to the
internet. There is no login, on purpose. Problems in Plex, Jellyfin, Radarr, Sonarr, Plezy or the TV itself should go
to those projects.

Supported versions: the latest release. Fixes are not backported.
