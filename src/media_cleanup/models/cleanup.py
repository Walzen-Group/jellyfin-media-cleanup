"""
Cleanup execution models.
"""
from __future__ import annotations
from media_cleanup.types import CleanupEntryStatus, CleanupMediaType
from .base import _Base, JobStatus
from .run_plan import FullSeriesDeletion, MovieDeletion, SeasonCleanup


class CleanupLogEntry(_Base):
    """Result of a single item in a cleanup run."""
    media_type: CleanupMediaType
    title: str
    path: str
    status: CleanupEntryStatus
    error: str | None = None
    size_bytes: int = 0
    verified: bool = False


class CleanupReport(_Base):
    """Full report for a completed or in-progress cleanup job."""
    job_id: str
    simulate: bool
    started_at: str
    completed_at: str | None = None
    entries: list[CleanupLogEntry] = []
    total_size_bytes: int = 0
    total_size_fmt: str = ""
    deleted_count: int = 0
    failed_count: int = 0


class HistoryEntry(_Base):
    """A row from the deleted_media history table."""
    id: int
    path: str
    media_type: CleanupMediaType
    title: str
    sonarr_id: int | None = None
    radarr_id: int | None = None
    season_numbers: list[int] | None = None
    deleted_at: str
    size_bytes: int = 0
    simulated: bool = False


class CleanupExecuteRequest(_Base):
    """Request body to start a cleanup execution with user-selected items."""
    simulate: bool = True
    movies: list[MovieDeletion] = []
    full_series: list[FullSeriesDeletion] = []
    season_cleanups: list[SeasonCleanup] = []


class CleanupJobResponse(_Base):
    """Status and result for a cleanup job."""
    job_id: str
    status: JobStatus
    simulate: bool
    created_at: str
    completed_at: str | None = None
    error: str | None = None
    report: CleanupReport | None = None
