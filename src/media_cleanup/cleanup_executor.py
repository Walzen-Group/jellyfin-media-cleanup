"""
Cleanup executor: deletes media from Radarr/Sonarr one item at a time,
verifies each deletion, and writes to the history DB immediately after confirmation.
"""

import json
import logging
import time
from datetime import datetime, timezone
from typing import Callable

import requests

from media_cleanup.clients.radarr import RadarrClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.config import AppConfig
from media_cleanup.database import Database
from media_cleanup.models import (
    CleanupLogEntry,
    CleanupReport,
    FullSeriesDeletion,
    MovieDeletion,
    RunPlan,
    SeasonCleanup,
)
from media_cleanup.types import CleanupEntryStatus, CleanupMediaType

logger = logging.getLogger(__name__)

# (item_index, total_items, title, status)
ProgressCallback = Callable[[int, int, str, CleanupEntryStatus], None]
CancelCheck = Callable[[], bool]

_VERIFY_RETRY_DELAY = 1.5  # seconds before a single re-check


class CleanupCancelledError(Exception):
    """Raised when a cancel_check signals cancellation between items."""


class CleanupExecutor:
    """Executes a RunPlan against Radarr/Sonarr, recording results in the DB."""

    def __init__(self, config: AppConfig, db: Database, simulate: bool = True) -> None:
        self._config = config
        self._db = db
        self._simulate = simulate

    def execute(
        self,
        run_plan: RunPlan,
        progress_cb: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> CleanupReport:
        """
        Process every item in run_plan one at a time.

        Order: movies -> full series -> season cleanups.
        Cancellation is checked before each item — a partial run is fully recorded.
        Returns a CleanupReport regardless of cancellation or per-item failures.
        """
        started_at = datetime.now(timezone.utc).isoformat()
        entries: list[CleanupLogEntry] = []

        total = (
            len(run_plan.movies)
            + len(run_plan.full_series)
            + len(run_plan.season_cleanups)
        )
        index = 0

        radarr = RadarrClient(
            root_url=self._config.radarr_url,
            api_key=self._config.radarr_api_key,
        )
        sonarr = SonarrClient(
            root_url=self._config.sonarr_url,
            api_key=self._config.sonarr_api_key,
        )

        try:
            for movie in run_plan.movies:
                self._check_cancel(cancel_check)
                entry = self._process_movie(radarr, movie, index, total, progress_cb)
                entries.append(entry)
                index += 1

            for series in run_plan.full_series:
                self._check_cancel(cancel_check)
                entry = self._process_series(sonarr, series, index, total, progress_cb)
                entries.append(entry)
                index += 1

            for cleanup in run_plan.season_cleanups:
                self._check_cancel(cancel_check)
                entry = self._process_seasons(sonarr, cleanup, index, total, progress_cb)
                entries.append(entry)
                index += 1

        except CleanupCancelledError:
            logger.info("Cleanup cancelled after %d/%d items", index, total)

        completed_at = datetime.now(timezone.utc).isoformat()
        deleted_count = sum(
            1 for e in entries
            if e.status in (CleanupEntryStatus.DELETED, CleanupEntryStatus.SIMULATED)
        )
        failed_count = sum(1 for e in entries if e.status == CleanupEntryStatus.FAILED)
        total_size = sum(e.size_bytes for e in entries)

        from media_cleanup.models import _format_size
        return CleanupReport(
            job_id="",  # filled in by CleanupJobManager
            simulate=self._simulate,
            started_at=started_at,
            completed_at=completed_at,
            entries=entries,
            total_size_bytes=total_size,
            total_size_fmt=_format_size(total_size),
            deleted_count=deleted_count,
            failed_count=failed_count,
        )

    # ------------------------------------------------------------------
    #  Per-item processors
    # ------------------------------------------------------------------

    def _process_movie(
        self,
        radarr: RadarrClient,
        movie: MovieDeletion,
        index: int,
        total: int,
        progress_cb: ProgressCallback | None,
    ) -> CleanupLogEntry:
        status = CleanupEntryStatus.SIMULATED
        error: str | None = None
        verified = False

        if not self._simulate:
            try:
                radarr.delete_movie(movie.radarr_id, delete_files=True)
                verified = self._verify_movie_deleted(radarr, movie.radarr_id)
                status = CleanupEntryStatus.DELETED if verified else CleanupEntryStatus.FAILED
                if not verified:
                    error = "Deletion not confirmed by Radarr"
            except Exception as exc:
                status = CleanupEntryStatus.FAILED
                error = str(exc)
                logger.warning("Failed to delete movie %r (id=%d): %s", movie.title, movie.radarr_id, exc)
        else:
            verified = True

        self._db.insert_or_ignore(
            path=movie.library_path,
            media_type=CleanupMediaType.MOVIE,
            title=movie.title,
            sonarr_id=None,
            radarr_id=movie.radarr_id,
            season_numbers=None,
            deleted_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=movie.size_bytes,
            simulated=1 if self._simulate else 0,
        )

        entry = CleanupLogEntry(
            media_type=CleanupMediaType.MOVIE,
            title=movie.title,
            path=movie.library_path,
            status=status,
            error=error,
            size_bytes=movie.size_bytes,
            verified=verified,
        )
        if progress_cb:
            progress_cb(index, total, movie.title, status)
        return entry

    def _process_series(
        self,
        sonarr: SonarrClient,
        series: FullSeriesDeletion,
        index: int,
        total: int,
        progress_cb: ProgressCallback | None,
    ) -> CleanupLogEntry:
        status = CleanupEntryStatus.SIMULATED
        error: str | None = None
        verified = False

        if not self._simulate:
            try:
                sonarr.delete_series(series.sonarr_series_id, delete_files=True)
                verified = self._verify_series_deleted(sonarr, series.sonarr_series_id)
                status = CleanupEntryStatus.DELETED if verified else CleanupEntryStatus.FAILED
                if not verified:
                    error = "Deletion not confirmed by Sonarr"
            except Exception as exc:
                status = CleanupEntryStatus.FAILED
                error = str(exc)
                logger.warning("Failed to delete series %r (id=%d): %s", series.title, series.sonarr_series_id, exc)
        else:
            verified = True

        self._db.insert_or_ignore(
            path=series.library_path,
            media_type=CleanupMediaType.SERIES,
            title=series.title,
            sonarr_id=series.sonarr_series_id,
            radarr_id=None,
            season_numbers=None,
            deleted_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=series.size_bytes,
            simulated=1 if self._simulate else 0,
        )

        entry = CleanupLogEntry(
            media_type=CleanupMediaType.SERIES,
            title=series.title,
            path=series.library_path,
            status=status,
            error=error,
            size_bytes=series.size_bytes,
            verified=verified,
        )
        if progress_cb:
            progress_cb(index, total, series.title, status)
        return entry

    def _process_seasons(
        self,
        sonarr: SonarrClient,
        cleanup: SeasonCleanup,
        index: int,
        total: int,
        progress_cb: ProgressCallback | None,
    ) -> CleanupLogEntry:
        status = CleanupEntryStatus.SIMULATED
        error: str | None = None
        verified = False

        if not self._simulate:
            try:
                files = sonarr.get_episode_files(cleanup.sonarr_series_id)
                season_files = [f for f in files if f.season_number in cleanup.season_numbers]
                if season_files:
                    sonarr.delete_episode_files_bulk([f.id for f in season_files])
                for sn in cleanup.season_numbers:
                    sonarr.unmonitor_season(cleanup.sonarr_series_id, sn)
                verified = self._verify_season_cleaned(
                    sonarr, cleanup.sonarr_series_id, cleanup.season_numbers
                )
                status = CleanupEntryStatus.DELETED if verified else CleanupEntryStatus.FAILED
                if not verified:
                    error = "Season files still present after deletion"
            except Exception as exc:
                status = CleanupEntryStatus.FAILED
                error = str(exc)
                logger.warning(
                    "Failed to clean seasons %s for %r (id=%d): %s",
                    cleanup.season_numbers, cleanup.title, cleanup.sonarr_series_id, exc,
                )
        else:
            verified = True

        self._db.insert_or_ignore(
            path=cleanup.library_path,
            media_type=CleanupMediaType.SEASON,
            title=cleanup.title,
            sonarr_id=cleanup.sonarr_series_id,
            radarr_id=None,
            season_numbers=json.dumps(cleanup.season_numbers),
            deleted_at=datetime.now(timezone.utc).isoformat(),
            size_bytes=cleanup.total_size_bytes,
            simulated=1 if self._simulate else 0,
        )

        entry = CleanupLogEntry(
            media_type=CleanupMediaType.SEASON,
            title=cleanup.title,
            path=cleanup.library_path,
            status=status,
            error=error,
            size_bytes=cleanup.total_size_bytes,
            verified=verified,
        )
        if progress_cb:
            progress_cb(index, total, cleanup.title, status)
        return entry

    # ------------------------------------------------------------------
    #  Verification helpers
    # ------------------------------------------------------------------

    def _verify_movie_deleted(self, radarr: RadarrClient, movie_id: int) -> bool:
        """Return True if the movie is confirmed gone (404) or has no file."""
        for attempt in range(2):
            if attempt > 0:
                time.sleep(_VERIFY_RETRY_DELAY)
            try:
                result = radarr.get_movie(movie_id)
                if not result.get("hasFile", True):
                    return True
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    return True
                raise
        return False

    def _verify_series_deleted(self, sonarr: SonarrClient, series_id: int) -> bool:
        """Return True if the series is confirmed gone (404)."""
        for attempt in range(2):
            if attempt > 0:
                time.sleep(_VERIFY_RETRY_DELAY)
            try:
                sonarr.get_series(series_id)
            except requests.HTTPError as exc:
                if exc.response is not None and exc.response.status_code == 404:
                    return True
                raise
        return False

    def _verify_season_cleaned(
        self, sonarr: SonarrClient, series_id: int, season_numbers: list[int]
    ) -> bool:
        """Return True if all episode files for the given seasons are gone."""
        for attempt in range(2):
            if attempt > 0:
                time.sleep(_VERIFY_RETRY_DELAY)
            files = sonarr.get_episode_files(series_id)
            remaining = [f for f in files if f.season_number in season_numbers]
            if not remaining:
                return True
        return False

    # ------------------------------------------------------------------
    #  Internal
    # ------------------------------------------------------------------

    @staticmethod
    def _check_cancel(cancel_check: CancelCheck | None) -> None:
        """Raise CleanupCancelledError if the caller has requested cancellation."""
        if cancel_check and cancel_check():
            raise CleanupCancelledError()
