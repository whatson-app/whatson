"""ESPN's public scoreboard feed: teams, start times, live scores and TV networks.

Guide listings rarely name the teams ("Live: College Football"), so games are matched
to airings by network and kickoff, which is what makes a team name find the right channel.

Decisions: ADR 0014.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import httpx

BASE = "https://site.api.espn.com/apis/site/v2/sports/{league}/scoreboard"
# College feeds only list ranked/featured games unless a group is given.
GROUPS = {"football/college-football": "80", "basketball/mens-college-basketball": "50",
          "basketball/womens-college-basketball": "50"}

# How each ESPN network name shows up in channel names. Broadcast networks are matched
# on the word alone (with "FOX SPORTS" excluded), cable ones by their usual spellings.
NETWORK_ALIASES: dict[str, tuple[str, ...]] = {
    "FS1": ("fox sports 1", "fs1"), "FS2": ("fox sports 2", "fs2"),
    "BTN": ("big ten network", "btn"), "SEC Network": ("sec network", "secn"),
    "ACC Network": ("acc network", "accn"), "ESPN": ("espn",), "ESPN2": ("espn 2", "espn2"),
    "ESPNU": ("espnu", "espn u"), "ESPNEWS": ("espnews",), "CBSSN": ("cbs sports network", "cbssn"),
    "NFL Network": ("nfl network",), "NBA TV": ("nba tv",), "MLB Network": ("mlb network",),
    "NHL Network": ("nhl network",), "TNT": ("tnt",), "truTV": ("trutv", "tru tv"),
    "TBS": ("tbs",), "USA Net": ("usa network",), "Big Ten Network": ("big ten network",),
    "Golf": ("golf channel",), "CNBC": ("cnbc",), "The CW": ("cw",), "CW": ("cw",),
}
BROADCAST = ("ABC", "CBS", "FOX", "NBC")


@dataclass
class Game:
    id: str
    league: str
    name: str
    short_name: str
    starts: int
    state: str
    detail: str
    home: str
    away: str
    home_score: str
    away_score: str
    networks: list[str]
    terms: list[str]
    home_id: str = ""
    away_id: str = ""
    home_logo: str = ""
    away_logo: str = ""


def network_matches(network: str, channel_title: str) -> bool:
    title = channel_title.lower()
    net = network.strip()
    if net.upper() in BROADCAST:
        word = net.lower()
        # "FOX Sports 1", "NBC News Now" and "FOX Business" are other channels, not the broadcast network.
        return bool(re.search(rf"(^|[\s\d]){word}\b(?!\s+(sports|news|business))", title))
    aliases = NETWORK_ALIASES.get(net, (net.lower(),))
    return any(re.search(rf"(^|[^a-z]){re.escape(a)}($|[^a-z])", title) for a in aliases)


def _score(side: dict) -> str:
    sc = side.get("score", "")
    return str(sc.get("displayValue", "")) if isinstance(sc, dict) else str(sc or "")


def _logo(team: dict) -> str:
    return team.get("logo") or (team.get("logos") or [{}])[0].get("href", "") or ""


def _parse(league: str, ev: dict) -> Game | None:
    comp = (ev.get("competitions") or [{}])[0]
    sides = {c.get("homeAway"): c for c in comp.get("competitors", [])}
    if "home" not in sides or "away" not in sides:
        return None
    terms: list[str] = []
    for c in sides.values():
        t = c.get("team", {})
        for k in ("displayName", "shortDisplayName", "name", "abbreviation", "location", "nickname"):
            if t.get(k) and t[k] not in terms:
                terms.append(t[k])
    nets: list[str] = []
    for b in comp.get("broadcasts", []):
        nets += [n for n in b.get("names", []) if n not in nets]
    for g in comp.get("geoBroadcasts", []):
        if g.get("type", {}).get("shortName") == "TV":
            n = g.get("media", {}).get("shortName")
            if n and n not in nets:
                nets.append(n)
    # Scoreboards put status on the event; team schedules put it on the competition.
    st = (ev.get("status") or comp.get("status") or {}).get("type", {})
    starts = int(datetime.fromisoformat(ev["date"].replace("Z", "+00:00")).timestamp())
    return Game(
        id=f"{league}:{ev['id']}", league=league, name=ev.get("name", ""),
        short_name=ev.get("shortName", ""), starts=starts, state=st.get("state", "pre"),
        detail=st.get("shortDetail") or st.get("detail", ""),
        home=sides["home"]["team"].get("shortDisplayName", ""),
        away=sides["away"]["team"].get("shortDisplayName", ""),
        home_score=_score(sides["home"]), away_score=_score(sides["away"]),
        networks=nets, terms=terms,
        home_id=str(sides["home"]["team"].get("id", "")), away_id=str(sides["away"]["team"].get("id", "")),
        home_logo=_logo(sides["home"]["team"]), away_logo=_logo(sides["away"]["team"]))


async def fetch_games(leagues: tuple[str, ...], http: httpx.AsyncClient | None = None,
                      now: datetime | None = None) -> list[Game]:
    now = now or datetime.now(timezone.utc)
    # Today and tomorrow in US time, so late games and tomorrow's early slate are covered.
    local = now - timedelta(hours=6)
    days = [(local + timedelta(days=d)).strftime("%Y%m%d") for d in (0, 1)]
    own = http is None
    http = http or httpx.AsyncClient(timeout=20)

    async def one(league: str, day: str) -> list[Game]:
        params = {"dates": day, "limit": "500"}
        if league in GROUPS:
            params["groups"] = GROUPS[league]
        try:
            r = await http.get(BASE.format(league=league), params=params)
            r.raise_for_status()
        except httpx.HTTPError:
            return []
        return [g for ev in r.json().get("events", []) if (g := _parse(league, ev))]

    try:
        batches = await asyncio.gather(*(one(lg, d) for lg in leagues for d in days))
    finally:
        if own:
            await http.aclose()
    seen: dict[str, Game] = {}
    for g in (g for b in batches for g in b):
        seen[g.id] = g
    return list(seen.values())


# --- Teams, schedules and play-by-play (for followed teams and "catch me up") ---------------------

TEAMS = "https://site.api.espn.com/apis/site/v2/sports/{league}/teams"
SCHEDULE = "https://site.api.espn.com/apis/site/v2/sports/{league}/teams/{team}/schedule"
SUMMARY = "https://site.api.espn.com/apis/site/v2/sports/{league}/summary"

LEAGUE_LABELS = {
    "football/nfl": "NFL", "football/college-football": "College football", "basketball/nba": "NBA",
    "basketball/wnba": "WNBA", "basketball/mens-college-basketball": "Men's college basketball",
    "basketball/womens-college-basketball": "Women's college basketball", "hockey/nhl": "NHL",
    "baseball/mlb": "MLB", "soccer/usa.1": "MLS", "soccer/eng.1": "Premier League",
    "soccer/esp.1": "La Liga", "soccer/uefa.champions": "Champions League",
}


# ESPN gives a school one team id across its college sports (the same id in football and
# basketball), so following a school in one college league follows it in all of them. Pro team ids
# only mean something within their own league (team 4 in the NHL is someone else in the NBA).
COLLEGE_LEAGUES = ("football/college-football", "basketball/mens-college-basketball",
                   "basketball/womens-college-basketball")


def team_leagues(league: str) -> tuple[str, ...]:
    """The leagues in which a team followed in `league` plays under the same id."""
    return COLLEGE_LEAGUES if league in COLLEGE_LEAGUES else (league,)


def followed_team_keys(rows) -> set[tuple[str, str]]:
    """(league, team id) pairs for followed teams, from `follows` rows of kind 'team'."""
    return {(lg, r["team_id"]) for r in rows for lg in team_leagues(r["league"])}


def is_followed_game(keys: set[tuple[str, str]], league: str, home_id: str, away_id: str) -> bool:
    return (league, home_id) in keys or (league, away_id) in keys


def league_label(league: str) -> str:
    return LEAGUE_LABELS.get(league, league.split("/")[-1].replace("-", " ").title())


async def fetch_teams(league: str, http: httpx.AsyncClient) -> list[dict]:
    r = await http.get(TEAMS.format(league=league), params={"limit": "1000"})
    r.raise_for_status()
    out = []
    for lg in r.json().get("sports", [{}])[0].get("leagues", []):
        for t in lg.get("teams", []):
            t = t.get("team", {})
            logo = (t.get("logos") or [{}])[0].get("href", "")
            out.append({"id": str(t.get("id")), "name": t.get("displayName", ""),
                        "short": t.get("shortDisplayName", ""), "abbr": t.get("abbreviation", ""), "logo": logo})
    return sorted(out, key=lambda t: t["name"])


async def fetch_schedule(league: str, team_id: str, http: httpx.AsyncClient) -> dict:
    """{'last': game-ish dict | None, 'next': game-ish dict | None} for one team."""
    r = await http.get(SCHEDULE.format(league=league, team=team_id))
    r.raise_for_status()
    games = [g for ev in r.json().get("events", []) if (g := _parse(league, ev))]
    done = [g for g in games if g.state == "post"]
    ahead = sorted((g for g in games if g.state != "post"), key=lambda g: g.starts)
    return {"last": max(done, key=lambda g: g.starts) if done else None, "next": ahead[0] if ahead else None}


async def fetch_recap_facts(league: str, event_id: str, http: httpx.AsyncClient) -> tuple[str, list[str]]:
    """(facts for the AI, the last plays as plain lines for the no-AI fallback)."""
    r = await http.get(SUMMARY.format(league=league), params={"event": event_id})
    r.raise_for_status()
    d = r.json()
    comp = (d.get("header", {}).get("competitions") or [{}])[0]
    teams = [f"{c.get('team', {}).get('displayName', '')} {c.get('score', '')}" for c in comp.get("competitors", [])]
    status = comp.get("status", {}).get("type", {}).get("detail", "")
    scoring = [f"P{s.get('period', {}).get('number', '')}: {s.get('text', '')}" for s in d.get("scoringPlays", [])]
    plays: list[str] = []
    drives = d.get("drives", {})
    for drive in (drives.get("previous") or [])[-2:] + ([drives["current"]] if drives.get("current") else []):
        plays += [p.get("text", "") for p in drive.get("plays", [])]
    plays += [p.get("text", "") for p in (d.get("plays") or [])[-12:]]
    plays = [p for p in plays if p][-10:]
    lines = [f"Score: {' - '.join(teams)}. Status: {status}.", "Scoring plays:", *scoring[-12:],
             "Most recent plays:", *plays]
    return "\n".join(lines), plays[-5:]

