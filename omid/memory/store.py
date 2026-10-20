"""omid.memory.store — حافظهٔ بلندمدت مبتنی بر SQLite.

- رویدادها، ترجیحات مجاز و خلاصهٔ عملیات ذخیره و قابل جست‌وجو هستند.
- سیاست نگهداری (prune) و خروجی‌گیری/پاک‌سازی کامل پشتیبانی می‌شود.
- دادهٔ آزمایشی با حافظهٔ واقعی کاربر مخلوط نمی‌شود: آزمون‌ها از فایل
  موقت مستقل استفاده می‌کنند.
- اطلاعات حساس ذخیره نمی‌شود: کلیدهای مشکوک هنگام نوشتن redact می‌شوند.

© هوشمندسازی صنعت امید — OMID Industrial AI Agent
طراح و سازندهٔ اصلی: مهندس امید براتی
"""
from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from omid.events import redact, utc_now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    type TEXT NOT NULL,
    summary TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}'
);
CREATE TABLE IF NOT EXISTS prefs (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS ops (
    id TEXT PRIMARY KEY,
    ts TEXT NOT NULL,
    goal TEXT NOT NULL,
    status TEXT NOT NULL,
    result_summary TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_ops_ts ON ops(ts);
"""


class MemoryStore:
    """حافظهٔ بلندمدت thread-safe با SQLite."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock, self._conn:
            self._conn.executescript(_SCHEMA)
            self._conn.execute("PRAGMA journal_mode=WAL;")

    # ---------- رویدادها ----------
    def remember_event(self, type_: str, summary: str, data: dict[str, Any] | None = None) -> int:
        payload = json.dumps(redact(data or {}), ensure_ascii=False)
        with self._lock, self._conn:
            cur = self._conn.execute(
                "INSERT INTO events(ts, type, summary, data) VALUES (?,?,?,?)",
                (utc_now_iso(), type_, summary, payload),
            )
            return int(cur.lastrowid or 0)

    def search_events(self, term: str = "", limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            if term.strip():
                like = f"%{term.strip()}%"
                rows = self._conn.execute(
                    "SELECT * FROM events WHERE summary LIKE ? OR type LIKE ? ORDER BY id DESC LIMIT ?",
                    (like, like, limit),
                ).fetchall()
            else:
                rows = self._conn.execute("SELECT * FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [self._event_dict(r) for r in rows]

    # ---------- ترجیحات ----------
    def set_preference(self, key: str, value: Any) -> None:
        payload = json.dumps(redact({key: value})[key], ensure_ascii=False)
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO prefs(key, value, updated) VALUES (?,?,?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated=excluded.updated",
                (key, payload, utc_now_iso()),
            )

    def get_preferences(self) -> dict[str, Any]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value, updated FROM prefs").fetchall()
        out: dict[str, Any] = {}
        for r in rows:
            try:
                out[r["key"]] = {"value": json.loads(r["value"]), "updated": r["updated"]}
            except json.JSONDecodeError:
                out[r["key"]] = {"value": r["value"], "updated": r["updated"]}
        return out

    def delete_preference(self, key: str) -> bool:
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM prefs WHERE key=?", (key,))
            return cur.rowcount > 0

    # ---------- عملیات ----------
    def record_operation(self, task_id: str, goal: str, status: str, result_summary: str) -> None:
        with self._lock, self._conn:
            self._conn.execute(
                "INSERT INTO ops(id, ts, goal, status, result_summary) VALUES (?,?,?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET status=excluded.status, result_summary=excluded.result_summary",
                (task_id, utc_now_iso(), goal[:500], status, result_summary[:2000]),
            )

    def list_operations(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM ops ORDER BY ts DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- نگهداری و خروجی ----------
    def prune(self, days: int = 90) -> int:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=max(1, days))).isoformat(timespec="seconds")
        with self._lock, self._conn:
            cur = self._conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            return cur.rowcount

    def export_all(self) -> dict[str, Any]:
        return {
            "exported_at": utc_now_iso(),
            "preferences": self.get_preferences(),
            "operations": self.list_operations(limit=1000),
            "events_recent": self.search_events(limit=500),
        }

    def clear(self) -> None:
        """پاک‌سازی کامل حافظه (برای آزمون یا درخواست صریح کاربر)."""
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM events")
            self._conn.execute("DELETE FROM prefs")
            self._conn.execute("DELETE FROM ops")

    def stats(self) -> dict[str, int]:
        with self._lock:
            counts = {}
            for table in ("events", "prefs", "ops"):
                counts[table] = self._conn.execute(f"SELECT COUNT(*) c FROM {table}").fetchone()["c"]  # noqa: S608
        return counts

    def close(self) -> None:
        with self._lock:
            try:
                self._conn.close()
            except sqlite3.Error:
                pass

    @staticmethod
    def _event_dict(row: sqlite3.Row) -> dict[str, Any]:
        item = dict(row)
        try:
            item["data"] = json.loads(item.get("data") or "{}")
        except json.JSONDecodeError:
            item["data"] = {}
        return item
