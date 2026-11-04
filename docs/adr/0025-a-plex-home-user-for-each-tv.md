# 0025. A Plex Home user for each TV

- **Status:** Proposed. Not built. The approach was tested on one TV on 2026-11-03, as described below.
- **Date:** 2026-11-03

## Context

WhatsOn talks to Plex with one token, normally the server owner's. Plex ties watched status and On Deck to the token, so
everyone sees the owner's history, whoever is watching (ADR 0019). Jellyfin doesn't have this problem, because one key can
ask for any user's data.

A single picker wouldn't fix it on Plex. A title plays under whichever profile Plezy is using on that TV, and that
profile's progress is what updates, so WhatsOn could show one person's Up Next while the TV plays as someone else.

We want a TV's "what's on" to match who watches that TV. The obvious way is to ask Plezy who is signed in, but nothing
answers that while a TV is idle:

- **The TV connection** (Android TV Remote) reports which app is open, not anything inside it.
- **Plezy's links** send commands and report nothing back.
- **Plezy's companion remote** is built for Plezy's own apps and needs a secret tied to the Plex account.
- **Plex sessions** name the user only while something is playing.
- **Plex play history** shows who played on a device before, which is only a guess at who is there now.

Plezy can be told who to be, though. Its links accept `profile=`, matched by `resolveLinkProfile` in Plezy's
`lib/services/deep_links/deep_link.dart` against the profile id, then the Plex Home user UUID, then the display name.

## Decision

**Each TV gets a Plex Home user, set once in ⚙ → TVs. WhatsOn tells Plezy which user to use, rather than trying to detect
it.**

1. **Choosing a TV** makes watched status and Up Next follow that TV's user.
2. **Starting something from WhatsOn** adds `profile=<Plex Home user UUID>` to the link. The UUID is what Plezy's own links
   use, and its code says it survives signing the account in again.
3. **A TV with no user set** sends no `profile=` and shows the owner's history, as today.

**Credentials.** Getting a server token for a user takes two steps from the owner's token, using the existing plex.tv
host:

1. `POST /api/v2/home/users/<uuid>/switch` returns a token for plex.tv only.
2. `GET /api/v2/resources` with that token returns the user's `accessToken` for this server.

The owner's token keeps the guide, the library list and the busy check. The user's server token only supplies that user's
watched status and Up Next. It's a saved key like any other (ADR 0007): never sent to the browser, and only sent to the
address it was saved with, with a test.

**Code.** Per-user reads go behind the `Source` protocol, and anything cached per user is keyed by user. `library.watched`
and `library.viewed_leaf_count` hold one value per item, and the unwatched filter and Tonight's pick read them, so
per-user status needs its own table or a read from Plex. That choice is left to the implementation.

## What testing found

Tested on 2026-11-03 on one Android TV device running Plezy 2.25.0, with an unprotected, restricted second Plex Home user.
The user was read from Plex's own session report, not from the screen, so nobody confirmed the picture.

| Link sent | User Plex reported | Time to appear |
|---|---|---|
| Library title, no `profile=` | Plezy's current profile (owner) | 2-5 s |
| Library title, `profile=` second user | Second user | 4 s |
| Library title, `profile=` owner | Owner | 4 s |
| Live TV, `profile=` second user | Second user | 11 s |
| Live TV, `profile=` owner | Owner | 12 s |
| `plezy://open` with `profile=`, then a title with none | The profile named in the open link | 2 s |
| Library title, unknown UUID | Nothing started in 30 s; profile unchanged | |

From plex.tv and the Plex server:

- **The switch token doesn't work on the server:** it gets a 401, which is why the second credential step exists.
- **Repeating the switch** from the same client id returned the same token, so it shouldn't pile up tokens.
- **Expiry:** the switch response gave no expiry date (`rememberExpiresAt` was empty). That doesn't prove the token
  lasts, so WhatsOn has to cope with a refused token by switching again.
- **The user's server token sees that user's data:** On Deck shared no items with the owner's, and the restricted user saw
  fewer libraries and titles.
- **The busy check has to stay on the owner's token:** the user's token gets a 403 on `/status/sessions`.
- **Session user ids:** the Plex server reports the owner's id as `1`, not their plex.tv id. Matching a session to a user
  has to allow for that.
- **Progress:** plays of up to about 15 seconds left no resume point or watched mark for either user.

**Not tested:** a PIN-protected profile, a Plezy version without `profile=`, a TV where Plezy has no profile for the user,
starting a title a restricted user can't see, tokens from Sign in with Plex (the test used a `PLEX_TOKEN`), revoking a
user's token, or how long the token lasts.

## Consequences

- A TV's history and Plezy's profile agree, so progress goes to the person WhatsOn shows.
- **The profile sticks.** A switch lasts after the link, so a TV with no user set stays on whichever profile was last used,
  and pressing play overrides a profile someone chose by hand in Plezy.
- **An unknown user fails silently.** WhatsOn has to wait for the title to appear and then say it didn't start. The wait
  should allow for Live TV taking at least 12 seconds here.
- **Restricted users aren't a parental control in WhatsOn.** The library is listed with the owner's token, so that TV can
  show titles Plex hides from the user. The app has to say so plainly.
- **PIN-protected profiles** should still ask for the PIN on the TV, according to Plezy's code.
- **Older Plezy versions** may ignore `profile=`, and progress would go to the active profile. WhatsOn can only learn the
  version from a session, so the setup steps have to mention it.
- **More keys to protect:** two saved tokens per user in the data folder, and one device entry on each user's Plex account.
- **Identifies a TV, not a person.** It needs no login and doesn't reopen ADR 0002, but anyone can change the setting. Once
  accepted, this replaces the part of ADR 0019 about whose history Plex shows.
- Plex only. Jellyfin keeps its one user (ADR 0019), and doing the same there would be a new decision.

## Alternatives

- **Detect who is signed in to Plezy:** not possible while a TV is idle, as listed above. Guessing from play history would
  show the wrong person's Up Next with no sign it was a guess.
- **One user for the whole install, as on Jellyfin:** simpler, but WhatsOn and the TV can disagree about who is watching.
- **One user per browser:** follows the phone, not the TV, and the TV is where progress gets recorded.
- **Listing the library with each user's token:** respects their restrictions, but needs a library copy per user. It could
  be added later if the limit above matters enough.

## Where it lives

Nothing yet. It would touch `whatson/tune.py`, `whatson/plex_auth.py`, `whatson/sources/base.py`, `whatson/sources/plex.py`
and `whatson/db.py`. Related: ADR 0002, ADR 0007, ADR 0010, ADR 0011, ADR 0013, ADR 0019.
