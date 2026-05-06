"""
Tests for Database.list_paged() -- pagination and title search.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from media_cleanup.database import Database


def _make_db() -> Database:
    """Create an in-memory-style temp-file database for testing."""
    tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
    return Database(Path(tmp.name))


def _insert(db: Database, title: str, path: str, deleted_at: str = "2024-01-01T00:00:00") -> None:
    db.insert_or_ignore(
        path=path,
        media_type="movie",
        title=title,
        sonarr_id=None,
        radarr_id=1,
        season_numbers=None,
        deleted_at=deleted_at,
        size_bytes=1_000_000,
        simulated=0,
    )


class TestListPaged:
    def test_limit_restricts_rows(self):
        db = _make_db()
        for i in range(10):
            _insert(db, f"Show {i}", f"/tv/show{i}")

        rows, total = db.list_paged(limit=3, offset=0)

        assert len(rows) == 3
        assert total == 10

    def test_offset_skips_rows(self):
        db = _make_db()
        # Insert in known deleted_at order so we can predict ordering
        for i in range(5):
            _insert(db, f"Movie {i}", f"/movies/movie{i}", deleted_at=f"2024-01-0{i+1}T00:00:00")

        rows_first, total = db.list_paged(limit=2, offset=0)
        rows_second, _ = db.list_paged(limit=2, offset=2)

        assert total == 5
        # No overlap between pages
        first_titles = {r["title"] for r in rows_first}
        second_titles = {r["title"] for r in rows_second}
        assert first_titles.isdisjoint(second_titles)
        # Together they cover 4 of 5 rows
        assert len(first_titles | second_titles) == 4

    def test_q_filters_by_title_substring(self):
        db = _make_db()
        _insert(db, "Euphoria", "/tv/euphoria")
        _insert(db, "Kakegurui", "/tv/kakegurui")
        _insert(db, "Top Gear US", "/tv/topgear")

        rows, total = db.list_paged(limit=50, offset=0, q="gear")

        assert total == 1
        assert len(rows) == 1
        assert rows[0]["title"] == "Top Gear US"

    def test_q_is_case_insensitive(self):
        db = _make_db()
        _insert(db, "Euphoria", "/tv/euphoria")
        _insert(db, "Kakegurui", "/tv/kakegurui")

        rows_upper, total_upper = db.list_paged(limit=50, offset=0, q="EUPHORIA")
        rows_lower, total_lower = db.list_paged(limit=50, offset=0, q="euphoria")

        assert total_upper == 1
        assert total_lower == 1
        assert rows_upper[0]["title"] == rows_lower[0]["title"] == "Euphoria"

    def test_q_none_returns_all(self):
        db = _make_db()
        _insert(db, "Show A", "/tv/a")
        _insert(db, "Show B", "/tv/b")

        rows, total = db.list_paged(limit=50, offset=0, q=None)

        assert total == 2
        assert len(rows) == 2

    def test_empty_q_string_treated_as_no_filter(self):
        """Callers passing q='' should get unfiltered results (routes.py passes None for empty)."""
        db = _make_db()
        _insert(db, "Show A", "/tv/a")
        _insert(db, "Show B", "/tv/b")

        # list_paged with q=None (the route strips empty strings to None)
        rows, total = db.list_paged(limit=50, offset=0, q=None)
        assert total == 2
        assert len(rows) == 2

    def test_offset_beyond_total_returns_empty(self):
        db = _make_db()
        _insert(db, "Only One", "/tv/one")

        rows, total = db.list_paged(limit=10, offset=100)

        assert total == 1
        assert rows == []

    def test_q_with_offset_and_limit(self):
        db = _make_db()
        for i in range(6):
            _insert(db, f"Star Trek {i}", f"/tv/st{i}", deleted_at=f"2024-01-0{i+1}T00:00:00")
        _insert(db, "Unrelated", "/tv/other")

        rows, total = db.list_paged(limit=2, offset=2, q="Star Trek")

        assert total == 6  # 6 matching rows total
        assert len(rows) == 2  # page of 2 starting at offset 2
