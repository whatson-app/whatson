"""AI settings edited from the web UI. Values saved in the database win; environment variables
(AI_PROVIDER, AI_MODEL, AI_BASE_URL, *_API_KEY) are the fallback, so existing .env setups keep working.

Keys are stored in the app's SQLite file (chmod 600) and never sent back to the browser in full.

Decisions: ADR 0007, 0016."""

from __future__ import annotations

import logging
import os
import sqlite3
from dataclasses import dataclass
from urllib.parse import urlparse

from . import db
from .safe_http import check_base_url
from .ai import DEFAULT_MODELS, KEY_ENV, PROVIDERS, Interpreter, key_required


@dataclass
class AIConfig:
    provider: str
    model: str
    base_url: str
    keys: dict[str, tuple[str, str]]  # provider -> (key, source: "saved" | "env" | "")

    def key(self) -> str:
        return self.keys.get(self.provider, ("", ""))[0]


log = logging.getLogger(__name__)


def load(conn: sqlite3.Connection) -> AIConfig:
    def pick(name: str, env: str) -> str:
        return db.get_meta(conn, f"ai.{name}") or os.environ.get(env, "").strip()

    base_url = pick("base_url", "AI_BASE_URL")
    keys = {}
    for p, env in KEY_ENV.items():
        saved = db.get_meta(conn, f"ai.key.{p}")
        env_key = os.environ.get(env, "").strip()
        # A key only travels to the address it was saved for, so changing the base URL can't
        # redirect it to another server. .env keys only go to the provider's own default URL.
        if saved and db.get_meta(conn, f"ai.key_base.{p}") == base_url:
            keys[p] = (saved, "saved")
        elif env_key and not base_url:
            keys[p] = (env_key, "env")
        else:
            keys[p] = ("", "")
    provider = (pick("provider", "AI_PROVIDER") or "none").lower()
    return AIConfig(provider=provider if provider in PROVIDERS else "none",
                    model=pick("model", "AI_MODEL"), base_url=base_url, keys=keys)


def interpreter(cfg: AIConfig) -> Interpreter:
    timeout = float(os.environ.get("AI_TIMEOUT", "") or 30)
    try:
        check_base_url(cfg.base_url)  # re-checked at start-up too: DNS can change after saving
    except ValueError:
        log.warning("AI server %s is not allowed; AI search stays off", urlparse(cfg.base_url).hostname)
        return Interpreter("none")
    return Interpreter(cfg.provider, cfg.model, cfg.base_url, cfg.key(), timeout=timeout)


def public(cfg: AIConfig, active: bool) -> dict:
    """What the browser may see: never a full key."""
    return {
        "provider": cfg.provider, "model": cfg.model, "base_url": cfg.base_url, "active": active,
        "default_models": DEFAULT_MODELS, "key_required": key_required(cfg.provider, cfg.base_url),
        "keys": {p: {"set": bool(k), "hint": f"…{k[-4:]}" if len(k) > 8 else ("set" if k else ""),
                     "source": src} for p, (k, src) in cfg.keys.items()},
    }


def save(conn: sqlite3.Connection, provider: str, model: str, base_url: str,
         new_keys: dict[str, str], clear_keys: list[str], checked: bool = False) -> None:
    """checked=True when the caller already ran check_base_url (async callers do it off the loop)."""
    if provider not in PROVIDERS:
        raise ValueError(f"provider must be one of {', '.join(PROVIDERS)}")
    # Only the OpenAI-compatible provider talks to a custom server.
    base_url = base_url.strip() if provider == "openai" else ""
    if not checked:
        check_base_url(base_url)
    db.set_meta(conn, "ai.provider", provider)
    db.set_meta(conn, "ai.model", model.strip())
    db.set_meta(conn, "ai.base_url", base_url)
    for p, k in new_keys.items():
        if p in KEY_ENV and k.strip():
            db.set_meta(conn, f"ai.key.{p}", k.strip())
            db.set_meta(conn, f"ai.key_base.{p}", base_url)
    for p in clear_keys:
        conn.execute("DELETE FROM meta WHERE key IN (?, ?)", (f"ai.key.{p}", f"ai.key_base.{p}"))
