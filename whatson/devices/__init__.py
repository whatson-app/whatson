"""Device registry: the TVs this install can tune, and the driver for each kind."""

from __future__ import annotations

import sqlite3

from .base import TVDriver, TVStatus

__all__ = ["TVDriver", "TVStatus", "list_devices", "get_device", "add_device", "rename_device",
           "remove_device", "mark_paired"]


def list_devices(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute("SELECT * FROM devices ORDER BY name")]


def get_device(conn: sqlite3.Connection, device_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM devices WHERE id = ?", (device_id,)).fetchone()
    return dict(row) if row else None


def add_device(conn: sqlite3.Connection, name: str, host: str, kind: str = "androidtv",
               plex_player: str = "") -> int:
    cur = conn.execute(
        "INSERT INTO devices (name, kind, host, plex_player) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(host) DO UPDATE SET name = excluded.name, kind = excluded.kind, "
        "plex_player = excluded.plex_player RETURNING id",
        (name, kind, host, plex_player or name))
    return cur.fetchone()[0]


def rename_device(conn: sqlite3.Connection, device_id: int, name: str) -> None:
    conn.execute("UPDATE devices SET name = ? WHERE id = ?", (name, device_id))


def remove_device(conn: sqlite3.Connection, device_id: int) -> None:
    conn.execute("DELETE FROM devices WHERE id = ?", (device_id,))
    conn.execute("DELETE FROM tv_apps WHERE device_id = ?", (device_id,))


def mark_paired(conn: sqlite3.Connection, device_id: int, paired: bool = True) -> None:
    conn.execute("UPDATE devices SET paired = ? WHERE id = ?", (int(paired), device_id))
