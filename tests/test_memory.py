"""آزمون حافظهٔ بلندمدت — SQLite، redaction، نگهداری و خروجی."""
from __future__ import annotations

import sqlite3

from omid.memory.store import MemoryStore


def make_store(tmp_path) -> MemoryStore:
    return MemoryStore(tmp_path / "mem.sqlite3")


def test_preferences_roundtrip(tmp_path):
    store = make_store(tmp_path)
    store.set_preference("language", "fa")
    prefs = store.get_preferences()
    assert prefs["language"]["value"] == "fa"
    store.set_preference("language", "en")
    assert store.get_preferences()["language"]["value"] == "en"
    assert store.delete_preference("language") is True
    assert store.delete_preference("language") is False


def test_sensitive_values_redacted(tmp_path):
    store = make_store(tmp_path)
    store.set_preference("api_token", "SECRET-VALUE")
    prefs = store.get_preferences()
    assert prefs["api_token"]["value"] == "***REDACTED***"
    store.remember_event("test", "رویداد با داده حساس", data={"password": "hunter2"})
    assert "hunter2" not in str(store.search_events("حساس"))


def test_events_search(tmp_path):
    store = make_store(tmp_path)
    store.remember_event("op.motion", "حرکت شبیه‌سازی شد")
    store.remember_event("op.error", "خطای ارتباط با دستگاه")
    assert len(store.search_events("حرکت")) == 1
    assert len(store.search_events()) == 2


def test_operations_history(tmp_path):
    store = make_store(tmp_path)
    store.record_operation("t1", "بررسی وضعیت", "completed", "همه‌چیز سالم")
    store.record_operation("t2", "حرکت فیزیکی", "failed", "رد شد")
    ops = store.list_operations()
    assert len(ops) == 2
    assert ops[0]["id"] in {"t1", "t2"}


def test_prune_removes_old_events(tmp_path):
    store = make_store(tmp_path)
    store.remember_event("old", "رویداد قدیمی")
    # backdate مستقیم در DB
    with sqlite3.connect(store.path) as conn:
        conn.execute("UPDATE events SET ts='2020-01-01T00:00:00+00:00' WHERE type='old'")
    removed = store.prune(days=30)
    assert removed == 1
    assert store.search_events("قدیمی") == []


def test_export_and_clear(tmp_path):
    store = make_store(tmp_path)
    store.set_preference("k", "v")
    store.remember_event("e", "s")
    store.record_operation("t", "g", "completed", "r")
    export = store.export_all()
    assert "preferences" in export and "operations" in export and "events_recent" in export
    store.clear()
    stats = store.stats()
    assert stats == {"events": 0, "prefs": 0, "ops": 0}


def test_store_isolated_file(tmp_path):
    store = make_store(tmp_path)
    store.remember_event("x", "y")
    store.close()
    assert (tmp_path / "mem.sqlite3").exists()
