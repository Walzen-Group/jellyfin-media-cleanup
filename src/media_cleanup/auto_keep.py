"""
Auto-keep: detect previously deleted media that was re-requested,
apply "keep" tags via Radarr/Sonarr, and remove from deletion history.
"""

import logging
from dataclasses import dataclass, field

from media_cleanup.config import AppConfig
from media_cleanup.database import Database
from media_cleanup.clients.radarr import RadarrClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.matching import MatchResult
from media_cleanup.types import SeasonSummary
from media_cleanup.service import ProgressCallback, CancelCheck, CancellationError

logger = logging.getLogger(__name__)


@dataclass
class AutoKeepResult:
    """Items that were auto-tagged as "keep" because they reappeared after deletion."""
    movies: list[MatchResult] = field(default_factory=list)
    seasons: list[SeasonSummary] = field(default_factory=list)


def apply_auto_keep(
    db: Database,
    config: AppConfig,
    movie_matches: list[MatchResult],
    season_matches: list[SeasonSummary],
    progress_callback: ProgressCallback | None = None,
    cancel_check: CancelCheck | None = None,
) -> AutoKeepResult:
    """
    Scan matched movies/seasons against the deletion history DB.

    For each item whose library path appears in the DB (meaning it was
    previously deleted and has since been re-requested):
      1. Apply the "keep" tag in Radarr/Sonarr
      2. Remove the path from the deletion history
      3. Include the item in the result so the frontend can report it

    Parameters
    ----------
    db : Database with deletion history
    config : app config for constructing API clients
    movie_matches : all matched movies (recent + old) from the pipeline
    season_matches : all matched seasons (recent + old) from the pipeline
    progress_callback : optional (step_name, current, total)
    cancel_check : optional cancellation hook
    """
    cb = progress_callback or (lambda *_: None)

    deleted_paths = db.get_paths_set()
    if not deleted_paths:
        cb("Applying auto-keep tags", 1, 1)
        return AutoKeepResult()

    # Find movies whose library path is in the deletion history
    auto_keep_movies = [
        m for m in movie_matches
        if m.matched_path and m.matched_path in deleted_paths
    ]

    # Find seasons whose Sonarr path is in the deletion history.
    # Deduplicate by sonarr path for tagging (one tag call per series).
    auto_keep_seasons = [
        s for s in season_matches
        if s.matched_sonarr_path and s.matched_sonarr_path in deleted_paths
    ]
    unique_sonarr_paths: dict[str, SeasonSummary] = {}
    for s in auto_keep_seasons:
        if s.matched_sonarr_path and s.matched_sonarr_path not in unique_sonarr_paths:
            unique_sonarr_paths[s.matched_sonarr_path] = s

    if not auto_keep_movies and not unique_sonarr_paths:
        cb("Applying auto-keep tags", 1, 1)
        return AutoKeepResult()

    total = len(auto_keep_movies) + len(unique_sonarr_paths)
    i = 0

    # Tag movies
    if auto_keep_movies:
        radarr = RadarrClient(
            root_url=config.radarr_url,
            api_key=config.radarr_api_key,
        )
        radarr_tag_id = radarr.get_keep_tag_id()

        for m in auto_keep_movies:
            if cancel_check is not None and cancel_check():
                raise CancellationError("Auto-keep cancelled by caller")

            i += 1
            title = m.matched_title or "Unknown movie"
            cb(f"Applying auto-keep tags: {title}", i, total)

            if radarr_tag_id is not None and m.radarr_movie_id is not None:
                try:
                    radarr.tag_movie(m.radarr_movie_id, radarr_tag_id)
                except Exception:
                    logger.exception("Failed to tag movie %s (id=%s)", title, m.radarr_movie_id)
                    continue

            if m.matched_path:
                db.delete_by_path(m.matched_path)
            logger.info("Auto-kept movie: %s", title)

    # Tag series (one call per unique Sonarr path)
    if unique_sonarr_paths:
        sonarr = SonarrClient(
            root_url=config.sonarr_url,
            api_key=config.sonarr_api_key,
        )
        sonarr_tag_id = sonarr.get_keep_tag_id()

        for path, representative in unique_sonarr_paths.items():
            if cancel_check is not None and cancel_check():
                raise CancellationError("Auto-keep cancelled by caller")

            i += 1
            cb(f"Applying auto-keep tags: {representative.series_name}", i, total)

            if sonarr_tag_id is not None and representative.sonarr_series_id is not None:
                try:
                    sonarr.tag_series(representative.sonarr_series_id, sonarr_tag_id)
                except Exception:
                    logger.exception(
                        "Failed to tag series %s (id=%s)",
                        representative.series_name, representative.sonarr_series_id,
                    )
                    continue

            db.delete_by_path(path)
            logger.info("Auto-kept series: %s", representative.series_name)

    return AutoKeepResult(movies=auto_keep_movies, seasons=auto_keep_seasons)
