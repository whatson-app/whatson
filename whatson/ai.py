"""Optional AI layer. Every feature here has a non-AI fallback, so search and suggestions work with
AI off, slow or broken:

- interpret: a question -> search Filters (fallback: keyword reading)
- answer:    one line answering the question from the matches found (fallback: no line)
- rank:      re-order suggestion candidates with a short reason each (fallback: rule order)
- recap:     three sentences on a game from ESPN's play-by-play (fallback: the last plays)

AI never invents results: it only reads the question or the candidates it is given.
Providers: Claude (Anthropic SDK), and OpenAI, OpenAI-compatible servers or OpenRouter (OpenAI SDK).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime

import httpx

from .safe_http import PinnedTransport
from .search import Filters, basic_filters, take_decade

log = logging.getLogger(__name__)

PROVIDERS = ("none", "anthropic", "openai", "openrouter")
DEFAULT_MODELS = {"anthropic": "claude-opus-5-5"}
KEY_ENV = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY", "openrouter": "OPENROUTER_API_KEY"}
OPENROUTER = "https://openrouter.ai/api/v1"

FILTER_SCHEMA = {
    "type": "object",
    "properties": {
        "text": {"type": "string", "description": "Words to full-text search for: titles, team names, "
                 "people, topics. Empty when the question is only about time, type, mood or length."},
        "scope": {"type": "string", "enum": ["all", "guide", "library"]},
        "on_now": {"type": "boolean"},
        "within_minutes": {"type": "integer", "description": "Only airings starting within this many "
                           "minutes; 0 for no limit."},
        "max_minutes": {"type": "integer", "description": "Longest running time wanted; 0 for any."},
        "audience": {"type": "string", "enum": ["any", "family", "kids"]},
        "kinds": {"type": "array", "items": {"type": "string", "enum": ["movie", "episode", "sports", "show"]}},
        "genres": {"type": "array", "items": {"type": "string"}},
        "year_from": {"type": "integer", "description": "Earliest release year wanted; 0 for any."},
        "year_to": {"type": "integer", "description": "Latest release year wanted; 0 for any."},
        "note": {"type": "string", "description": "One short sentence saying how the question was read."},
    },
    "required": ["text", "scope", "on_now", "within_minutes", "max_minutes", "audience", "kinds", "genres",
                 "year_from", "year_to", "note"],
    "additionalProperties": False,
}

FILTER_SYSTEM = """You turn a question about what to watch into search filters for a home TV app.
The app searches two things: the Live TV guide (channels, airings, sports games with team names) and
the person's Plex library (movies and shows they own).
- scope: "guide" for live TV questions ("on now", "what channel", "tonight", games), "library" for
  things to watch from their collection, "all" when unclear.
- text: the distinctive search words only. Expand team nicknames to the school or city as well
  ("illini" -> "illinois illini", "da bears" -> "chicago bears"). Leave out filler like "what's on"
  and words already captured by other fields (mood, length, audience).
- kinds: "sports" for games and matches, "movie" for films, "show"/"episode" for series. Empty if any.
- genres: plain genre words (comedy, horror, documentary, animation) for a mood or genre.
- audience: "kids" for young children, "family" when watching with kids, else "any".
- on_now: true when they want what is airing right now.
- within_minutes: for "tonight" use the minutes until 2am local time; "in the next hour" is 60.
- max_minutes: "under 2 hours" is 120; 0 when not mentioned.
- year_from / year_to: release years. "90s" is 1990 and 1999, "since 2015" is 2015 and 0,
  "old movies" is 0 and 1979; 0 and 0 when not mentioned. Never put years or decades in text."""

ANSWER_SCHEMA = {
    "type": "object",
    "properties": {"answer": {"type": "string"}},
    "required": ["answer"], "additionalProperties": False,
}

ANSWER_SYSTEM = """You answer a question about what to watch in ONE or TWO short sentences, using only
the numbered matches provided (live TV airings, library titles, games). Name the best match, when and
where it is on, and why it fits. Never mention anything not in the list. If nothing fits, say so plainly."""

RANK_SCHEMA = {
    "type": "object",
    "properties": {"picks": {"type": "array", "items": {
        "type": "object",
        "properties": {"id": {"type": "string"}, "reason": {"type": "string"}},
        "required": ["id", "reason"], "additionalProperties": False}}},
    "required": ["picks"], "additionalProperties": False,
}

RANK_SYSTEM = """You pick what someone would most enjoy watching from a list of candidates, using their
taste signals (ratings, watchlist, recent viewing, favorite teams) given with each candidate.
Return up to the requested number of candidate ids, best first, each with a reason of at most 12 words
written to the viewer ("You rated Glass Onion 9"). Only use ids from the list. Don't invent facts."""

RECAP_SCHEMA = ANSWER_SCHEMA
RECAP_SYSTEM = """You catch a sports fan up on a game in at most three short sentences from the score,
clock and plays given: who leads, how it got there, and what is happening now. Use only the facts given."""


def _no_redirects(base_url: str, openai_mod):
    """A custom server can't bounce requests (and the key) somewhere else via a redirect, and its
    address is checked and pinned on every request (see safe_http)."""
    if not base_url:
        return None
    return openai_mod.DefaultAsyncHttpxClient(follow_redirects=False, transport=PinnedTransport())


def key_required(provider: str, base_url: str) -> bool:
    """Local OpenAI-compatible servers (LM Studio, Ollama, llama.cpp) usually take no key."""
    return not (provider == "openai" and base_url)


def _year(v) -> int | None:
    return v if isinstance(v, int) and not isinstance(v, bool) and 1880 <= v <= 2100 else None


def _to_filters(data: dict) -> Filters:
    return take_decade(Filters(text=data.get("text") or "", scope=data.get("scope") or "all",
                   on_now=bool(data.get("on_now")), within_minutes=data.get("within_minutes") or None,
                   max_minutes=data.get("max_minutes") or None,
                   audience=data.get("audience") if data.get("audience") in ("family", "kids") else "any",
                   kinds=list(data.get("kinds") or []), genres=list(data.get("genres") or []),
                   year_from=_year(data.get("year_from")), year_to=_year(data.get("year_to"))))


def _now() -> str:
    return datetime.now().astimezone().strftime("%A %Y-%m-%d %H:%M %Z")


async def list_models(provider: str, base_url: str = "", api_key: str = "", timeout: float = 15) -> list[dict]:
    """Models the provider offers, as [{id, name, note}]. Raises on auth or network errors."""
    if provider == "anthropic":
        import anthropic
        client = anthropic.AsyncAnthropic(api_key=api_key, timeout=timeout, max_retries=0)
        out = [{"id": m.id, "name": m.display_name or m.id, "note": ""} async for m in client.models.list()]
        return out
    if provider == "openrouter":
        # Public catalogue; prices help pick a cheap model for this small job.
        async with httpx.AsyncClient(timeout=timeout) as http:
            r = await http.get(f"{OPENROUTER}/models")
            r.raise_for_status()
        out = []
        for m in r.json().get("data", []):
            p = m.get("pricing") or {}
            try:
                note = f"${float(p.get('prompt', 0)) * 1e6:.2f} / ${float(p.get('completion', 0)) * 1e6:.2f} per M tokens"
            except (TypeError, ValueError):
                note = ""
            out.append({"id": m["id"], "name": m.get("name") or m["id"], "note": note})
        return sorted(out, key=lambda m: m["name"].lower())
    if provider == "openai":
        import openai
        client = openai.AsyncOpenAI(base_url=base_url or None, api_key=api_key or "not-needed",
                                    timeout=timeout, max_retries=0, http_client=_no_redirects(base_url, openai))
        ids = [m.id async for m in client.models.list()]
        if not base_url:
            # OpenAI's own list mixes in embedding, audio and image models; keep chat-capable ones.
            skip = ("embedding", "whisper", "tts", "dall-e", "audio", "image", "moderation", "transcribe",
                    "realtime", "search", "davinci", "babbage")
            ids = [i for i in ids if not any(s in i for s in skip)]
        return [{"id": i, "name": i, "note": ""} for i in sorted(ids)]
    return []


class Interpreter:
    def __init__(self, provider: str, model: str = "", base_url: str = "", api_key: str = "",
                 timeout: float = 30.0):
        self.provider = provider
        self.model = model
        self._client = None
        # Search waits on these calls, so they give up quickly (then the fallback takes over)
        # rather than hang on a slow local model or a server that's switched off.
        # No retries: a retry doubles the wait.
        limits = {"timeout": timeout, "max_retries": 0}
        # A provider without a key (or model, where one is required) stays off rather than failing.
        if provider == "anthropic" and api_key:
            import anthropic  # optional dependency
            self._client = anthropic.AsyncAnthropic(api_key=api_key, **limits)
            self.model = model or DEFAULT_MODELS["anthropic"]
        elif provider in ("openai", "openrouter") and model and (api_key or not key_required(provider, base_url)):
            import openai  # optional dependency
            default_base = OPENROUTER if provider == "openrouter" else None
            # The SDK insists on some key; keyless local servers ignore it.
            self._client = openai.AsyncOpenAI(base_url=base_url or default_base,
                                              api_key=api_key or "not-needed", **limits,
                                              http_client=_no_redirects(base_url, openai))

    @property
    def enabled(self) -> bool:
        return self._client is not None

    async def _json(self, system: str, prompt: str, schema: dict, name: str) -> dict:
        if self.provider == "anthropic":
            response = await self._client.beta.messages.create(
                model=self.model,
                max_tokens=4000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=system,
                output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
                messages=[{"role": "user", "content": prompt}],
            )
            if response.stop_reason == "refusal":
                raise RuntimeError("model declined the request")
            return json.loads(next(b.text for b in response.content if b.type == "text"))
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            response_format={"type": "json_schema", "json_schema": {"name": name, "schema": schema, "strict": True}},
        )
        return json.loads(response.choices[0].message.content)

    async def interpret(self, query: str, raise_errors: bool = False) -> tuple[Filters, str]:
        if not self._client:
            return basic_filters(query), ""
        try:
            data = await self._json(FILTER_SYSTEM, f"Local time: {_now()}\nQuestion: {query}",
                                    FILTER_SCHEMA, "filters")
            return _to_filters(data), data.get("note", "")
        except Exception as exc:
            if raise_errors:
                raise
            log.warning("AI interpretation failed (%s); using keyword search", exc)
            return basic_filters(query), ""

    async def answer(self, query: str, matches: list[str]) -> str:
        if not self._client or not matches:
            return ""
        listing = "\n".join(f"{i + 1}. {m}" for i, m in enumerate(matches[:15]))
        try:
            data = await self._json(ANSWER_SYSTEM, f"Local time: {_now()}\nQuestion: {query}\nMatches:\n{listing}",
                                    ANSWER_SCHEMA, "answer")
            return (data.get("answer") or "").strip()
        except Exception as exc:
            log.warning("AI answer failed (%s)", exc)
            return ""

    async def rank(self, candidates: list[dict], want: int, context: str = "") -> list[dict]:
        """candidates: [{id, text}] -> [{id, reason}] using only known ids; [] when off or on error."""
        if not self._client or not candidates:
            return []
        listing = "\n".join(f"[{c['id']}] {c['text']}" for c in candidates[:40])
        prompt = f"Local time: {_now()}\n{context}\nPick up to {want}.\nCandidates:\n{listing}"
        try:
            data = await self._json(RANK_SYSTEM, prompt, RANK_SCHEMA, "picks")
        except Exception as exc:
            log.warning("AI ranking failed (%s)", exc)
            return []
        known = {c["id"] for c in candidates}
        return [p for p in data.get("picks", []) if p.get("id") in known][:want]

    async def recap(self, facts: str) -> str:
        if not self._client or not facts:
            return ""
        try:
            data = await self._json(RECAP_SYSTEM, facts, RECAP_SCHEMA, "recap")
            return (data.get("answer") or "").strip()
        except Exception as exc:
            log.warning("AI recap failed (%s)", exc)
            return ""
