"""Settings, read once from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_LEAGUES = (
    "football/college-football,football/nfl,basketball/nba,basketball/mens-college-basketball,"
    "basketball/womens-college-basketball,hockey/nhl,baseball/mlb,soccer/usa.1,soccer/eng.1"
)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    guide_hours: int = 24
    guide_refresh_minutes: int = 15
    library_refresh_minutes: int = 360
    sports_refresh_minutes: int = 5
    espn_leagues: tuple[str, ...] = field(default_factory=tuple)
    client_name: str = "WhatsOn"

    @property
    def db_path(self) -> Path:
        return self.data_dir / "whatson.db"

    @property
    def cert_dir(self) -> Path:
        return self.data_dir / "androidtv"


def load() -> Settings:
    # PLEX_URL / PLEX_TOKEN are optional now (Settings → Plex can sign in); plex_auth reads them.
    data_dir = Path(os.environ.get("DATA_DIR", "./data")).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    leagues = os.environ.get("ESPN_LEAGUES", DEFAULT_LEAGUES)
    return Settings(
        data_dir=data_dir,
        guide_hours=_int("GUIDE_HOURS", 24),
        guide_refresh_minutes=_int("GUIDE_REFRESH_MINUTES", 15),
        library_refresh_minutes=_int("LIBRARY_REFRESH_MINUTES", 360),
        sports_refresh_minutes=_int("SPORTS_REFRESH_MINUTES", 5),
        espn_leagues=tuple(x.strip() for x in leagues.split(",") if x.strip()),
        client_name=os.environ.get("CLIENT_NAME", "WhatsOn"),
    )
