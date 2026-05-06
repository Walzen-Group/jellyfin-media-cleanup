"""
SQLite-backed history store for cleanup operations.

Records every deletion (real or simulated) immediately after it is confirmed,
so that partial runs are fully preserved on cancellation or failure.
"""

import sqlite3
from pathlib import Path


_CREATE_TABLE = """
CREATE TABLE IF NOT EXISTS deleted_media (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    path          TEXT    UNIQUE NOT NULL,
    media_type    TEXT    NOT NULL,
    title         TEXT    NOT NULL,
    sonarr_id     INTEGER,
    radarr_id     INTEGER,
    season_numbers TEXT,
    deleted_at    TEXT    NOT NULL,
    size_bytes    INTEGER DEFAULT 0,
    simulated     INTEGER DEFAULT 0
)
"""


class Database:
    """Thin wrapper around a SQLite database for cleanup history."""

    def __init__(self, db_path: Path) -> None:
        """Open (or create) the database and ensure the schema exists."""
        self._path = db_path
        with self._connect() as conn:
            conn.execute(_CREATE_TABLE)

    # ------------------------------------------------------------------
    #  Write operations
    # ------------------------------------------------------------------

    def insert_or_ignore(
        self,
        *,
        path: str,
        media_type: str,
        title: str,
        sonarr_id: int | None,
        radarr_id: int | None,
        season_numbers: str | None,
        deleted_at: str,
        size_bytes: int,
        simulated: int,
    ) -> None:
        """Insert a new history row, silently ignoring duplicate paths."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO deleted_media
                    (path, media_type, title, sonarr_id, radarr_id,
                     season_numbers, deleted_at, size_bytes, simulated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (path, media_type, title, sonarr_id, radarr_id,
                 season_numbers, deleted_at, size_bytes, simulated),
            )

    def delete_by_id(self, id: int) -> None:
        """Remove a single history entry by its primary key."""
        with self._connect() as conn:
            conn.execute("DELETE FROM deleted_media WHERE id = ?", (id,))

    def delete_by_path(self, path: str) -> None:
        """Remove a history entry by its library path."""
        with self._connect() as conn:
            conn.execute("DELETE FROM deleted_media WHERE path = ?", (path,))

    def delete_by_ids(self, ids: list[int]) -> None:
        """Remove multiple history entries by their primary keys."""
        if not ids:
            return
        placeholders = ",".join("?" * len(ids))
        with self._connect() as conn:
            conn.execute(
                f"DELETE FROM deleted_media WHERE id IN ({placeholders})", ids
            )

    def clear_all(self) -> None:
        """Delete all rows from the history table."""
        with self._connect() as conn:
            conn.execute("DELETE FROM deleted_media")

    # ------------------------------------------------------------------
    #  Read operations
    # ------------------------------------------------------------------

    def list_all(self) -> list[dict]:
        """Return all history rows as plain dicts, newest first."""
        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM deleted_media ORDER BY deleted_at DESC"
            ).fetchall()
        return [dict(r) for r in rows]

    def list_paged(
        self,
        limit: int,
        offset: int,
        q: str | None = None,
    ) -> tuple[list[dict], int]:
        """Return a page of history rows and the total matching count.

        Args:
            limit: Maximum rows to return.
            offset: Number of rows to skip.
            q: Optional case-insensitive substring to match against title.

        Returns:
            (rows, total) where total is the count of all matching rows.
        """
        where = ""
        params: list[object] = []
        if q:
            where = "WHERE title LIKE '%' || ? || '%' COLLATE NOCASE"
            params.append(q)

        with self._connect() as conn:
            conn.row_factory = sqlite3.Row
            total: int = conn.execute(
                f"SELECT COUNT(*) FROM deleted_media {where}", params
            ).fetchone()[0]
            rows = conn.execute(
                f"SELECT * FROM deleted_media {where} ORDER BY deleted_at DESC LIMIT ? OFFSET ?",
                [*params, limit, offset],
            ).fetchall()
        return [dict(r) for r in rows], total

    def get_paths_set(self) -> set[str]:
        """Return the set of all recorded library paths (for auto-keep detection)."""
        with self._connect() as conn:
            rows = conn.execute("SELECT path FROM deleted_media").fetchall()
        return {r[0] for r in rows}

    def has_any(self) -> bool:
        """Return True if the history table contains at least one row."""
        with self._connect() as conn:
            row = conn.execute(
                "SELECT EXISTS(SELECT 1 FROM deleted_media LIMIT 1)"
            ).fetchone()
        return bool(row[0])

    # ------------------------------------------------------------------
    #  Internal
    # ------------------------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self._path)
