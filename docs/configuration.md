# Configuration

Most setup happens in ⚙ Settings, and all of these are optional. Environment variables go in `.env`, and
`.env.example` is a starting point. Values saved in Settings win over the environment for Plex, Radarr, Sonarr and AI.

Environment variables are read once at start-up, so restart after changing them.

## Server

| Variable | Default | What it does |
|---|---|---|
| `DATA_DIR` | `./data` (`/data` in the image) | Folder for the database and TV certificate |
| `ALLOWED_HOSTS` | Empty | Host names you open WhatsOn by, comma-separated. IP addresses and `localhost` always work. `*` turns the check off |
| `CLIENT_NAME` | `WhatsOn` | The name WhatsOn gives itself to TVs and Plex |

## Refresh

| Variable | Default | What it does |
|---|---|---|
| `GUIDE_HOURS` | `24` | How far ahead to load the guide |
| `GUIDE_REFRESH_MINUTES` | `15` | How often to reload the guide |
| `LIBRARY_REFRESH_MINUTES` | `360` | How often to reload the library |
| `SPORTS_REFRESH_MINUTES` | `5` | How often to reload games. Every 30 seconds while a followed team or league is playing |
| `ESPN_LEAGUES` | See `DEFAULT_LEAGUES` in `whatson/config.py` | Leagues to load, comma-separated ESPN paths |

## Plex

Used only when nothing is saved in ⚙ → Server → Plex. See [ADR 0013](adr/0013-plex-sign-in-and-server-token.md).

| Variable | What it does |
|---|---|
| `PLEX_URL` | Server address |
| `PLEX_TOKEN` | Token for that server |

## Radarr and Sonarr

A key set here only goes to the address set next to it.

| Variable | What it does |
|---|---|
| `RADARR_URL` | Radarr address |
| `RADARR_KEY` | Radarr API key |
| `SONARR_URL` | Sonarr address |
| `SONARR_KEY` | Sonarr API key |

## AI

Off by default, and everything works without it. See [ADR 0016](adr/0016-ai-is-optional-and-never-invents.md).

| Variable | What it does |
|---|---|
| `AI_PROVIDER` | `none`, `anthropic`, `openai` or `openrouter` |
| `AI_MODEL` | Model name. Required except for `anthropic`, which has a default |
| `AI_BASE_URL` | Address of an OpenAI-compatible server (LM Studio, Ollama). It needs no key |
| `AI_TIMEOUT` | Seconds to wait for an answer before falling back. Defaults to 30 |
| `ANTHROPIC_API_KEY` | Key for `anthropic` |
| `OPENAI_API_KEY` | Key for `openai` |
| `OPENROUTER_API_KEY` | Key for `openrouter` |

A key from the environment only goes to the provider's own address, never to `AI_BASE_URL`.

## Ports and networks

- WhatsOn listens on port 8430. The image sets this, not an environment variable.
- `compose.yaml` uses host networking so the container can reach TVs on ports 6466 and 6467.
