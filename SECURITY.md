# Security

WhatsOn has **no login** by design and is meant for a home network. Anyone who can open it can change
its settings, control TVs and (when allowed) add titles to Radarr and Sonarr. Don't port-forward it or
put it behind a public reverse proxy. See the Security section of the README for what it does protect.

## Reporting a problem

Please use GitHub's **private vulnerability reporting** (Security tab → Report a vulnerability) rather
than a public issue. Useful reports include ways a web page could drive WhatsOn through someone's
browser, ways to read a stored key or token, and ways to make it call an address it should refuse.
