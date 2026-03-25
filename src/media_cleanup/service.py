"""
Reusable service layer for the media cleanup pipeline.

Extracts the orchestration logic from launch.py so it can be driven by
the CLI, a FastAPI endpoint, or any other caller.
"""

from dataclasses import dataclass, field
from typing import Callable

from media_cleanup.config import AppConfig
from media_cleanup.clients.jellyfin import JellyfinClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.clients.radarr import RadarrClient
from media_cleanup.matching import (
    MatchResult,
    match_movies_by_path,
    fuzzy_match_movies,
    build_season_summaries,
    match_seasons_to_sonarr,
)
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.types import EpisodeInfo, SeasonSummary


# Type aliases for optional hooks the caller can provide
ProgressCallback = Callable[[str, int, int], None]
"""(step_name, current, total) — emitted at meaningful pipeline points."""

CancelCheck = Callable[[], bool]
"""Return True to request cancellation between pipeline steps."""


class CancellationError(Exception):
    """Raised when the caller's cancel_check returns True."""


@dataclass
class CleanupResult:
    """All categorized data produced by a single pipeline run."""
    recent_movie_matches: list[MatchResult] = field(default_factory=list)
    old_movie_matches: list[MatchResult] = field(default_factory=list)
    kept_movie_matches: list[MatchResult] = field(default_factory=list)
    recent_seasons_matched: list[SeasonSummary] = field(default_factory=list)
    old_seasons_matched: list[SeasonSummary] = field(default_factory=list)
    recent_seasons_unmatched: list[SeasonSummary] = field(default_factory=list)
    old_seasons_unmatched: list[SeasonSummary] = field(default_factory=list)
    kept_season_matches: list[SeasonSummary] = field(default_factory=list)
    all_movies: list[Movie] = field(default_factory=list)
    all_series: list[Series] = field(default_factory=list)
    episodes: list[EpisodeInfo] = field(default_factory=list)
    episode_dates: dict = field(default_factory=dict)


class CleanupService:
    """Runs the full fetch-match-classify pipeline against Jellyfin + Sonarr/Radarr."""

    def __init__(self, config: AppConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------ #
    #  Public API
    # ------------------------------------------------------------------ #

    def run_analysis(
        self,
        mode: str = "all",
        month_threshold: int | None = None,
        progress_callback: ProgressCallback | None = None,
        cancel_check: CancelCheck | None = None,
    ) -> CleanupResult:
        """
        Execute the full pipeline and return categorised results.

        Parameters
        ----------
        mode : "all" | "movies" | "series"
        month_threshold : override config default if provided
        progress_callback : optional (step_name, current, total) hook
        cancel_check : optional callable; if it returns True a
                       CancellationError is raised between major steps
        """
        threshold = month_threshold if month_threshold is not None else self._config.month_threshold
        result = CleanupResult()
        raw_cb = progress_callback or (lambda *_: None)

        # Define step weights so progress is a single 0→100 bar.
        # Episode resolution is the heaviest step (~60% of wall time).
        movie_steps = [
            ("Querying Jellyfin movie history", 2),
            ("Resolving movie paths", 3),
            ("Fetching Radarr library", 5),
            ("Matching movies", 5),
        ]
        series_steps = [
            ("Querying Jellyfin episode history", 2),
            ("Resolving episodes", 60),
            ("Fetching Sonarr library", 8),
            ("Matching seasons", 5),
        ]
        steps: list[tuple[str, int]] = []
        if mode in ("all", "movies"):
            steps += movie_steps
        if mode in ("all", "series"):
            steps += series_steps

        total_weight = sum(w for _, w in steps)
        step_offsets: dict[str, tuple[int, int]] = {}  # base_name -> (offset, weight)
        offset = 0
        for name, weight in steps:
            step_offsets[name] = (offset, weight)
            offset += weight

        def cb(step: str, current: int, total: int) -> None:
            """Translate per-step (current/total) into global progress."""
            base = step.split(":")[0].rstrip()
            if base not in step_offsets:
                raw_cb(step, current, total)
                return
            step_offset, step_weight = step_offsets[base]
            local_frac = (current / total) if total > 0 else 1.0
            global_current = step_offset + int(local_frac * step_weight)
            raw_cb(step, global_current, total_weight)

        jellyfin = JellyfinClient(
            root_url=self._config.jellyfin_url,
            api_key=self._config.jellyfin_api_key,
        )

        # ===== MOVIES =====
        if mode in ("all", "movies"):
            self._check_cancel(cancel_check)

            radarr = RadarrClient(
                root_url=self._config.radarr_url,
                api_key=self._config.radarr_api_key,
            )

            cb("Querying Jellyfin movie history", 0, 2)
            recent_movie_ids = jellyfin.get_recently_watched_movies(threshold)
            cb("Querying Jellyfin movie history", 1, 2)
            old_movie_ids = jellyfin.get_not_recently_watched_movies(threshold)
            cb("Querying Jellyfin movie history", 2, 2)

            self._check_cancel(cancel_check)

            recent_movie_paths = jellyfin.get_file_paths(
                recent_movie_ids, progress_callback=lambda s, c, t: cb("Resolving movie paths", c, t),
                desc="Resolving movie paths") if recent_movie_ids else []
            old_movie_paths = jellyfin.get_file_paths(
                old_movie_ids, progress_callback=lambda s, c, t: cb("Resolving movie paths", c, t),
                desc="Resolving movie paths") if old_movie_ids else []

            self._check_cancel(cancel_check)

            cb("Fetching Radarr library", 0, 1)
            result.all_movies = radarr.get_all_movies()
            eligible_movies = radarr.filter_kept_movies(result.all_movies)
            kept_movies = [m for m in result.all_movies if m not in eligible_movies]
            cb("Fetching Radarr library", 1, 1)

            kept_movie_paths = {m.path for m in kept_movies}

            self._check_cancel(cancel_check)

            cb("Matching movies", 0, 2)
            recent_movie_matches, recent_unmatched = match_movies_by_path(
                recent_movie_paths, result.all_movies)
            old_movie_matches, old_unmatched = match_movies_by_path(
                old_movie_paths, result.all_movies)
            cb("Matching movies", 1, 2)
            recent_movie_matches += fuzzy_match_movies(recent_unmatched, result.all_movies)
            old_movie_matches += fuzzy_match_movies(old_unmatched, result.all_movies)
            cb("Matching movies", 2, 2)

            result.kept_movie_matches = [
                m for m in recent_movie_matches + old_movie_matches
                if m.matched_path in kept_movie_paths
            ]
            result.recent_movie_matches = [
                m for m in recent_movie_matches
                if m.matched_path not in kept_movie_paths
            ]
            result.old_movie_matches = [
                m for m in old_movie_matches
                if m.matched_path not in kept_movie_paths
            ]

        # ===== SERIES =====
        if mode in ("all", "series"):
            self._check_cancel(cancel_check)

            sonarr = SonarrClient(
                root_url=self._config.sonarr_url,
                api_key=self._config.sonarr_api_key,
            )

            cb("Querying Jellyfin episode history", 0, 1)
            result.episode_dates = jellyfin.get_all_watched_episode_dates()
            cb("Querying Jellyfin episode history", 1, 1)

            self._check_cancel(cancel_check)

            # Episode resolution is the heaviest step — callback goes through
            # the global progress wrapper via the "Resolving episodes" base name
            result.episodes = jellyfin.get_episode_metadata(result.episode_dates, progress_callback=cb)

            self._check_cancel(cancel_check)

            cb("Fetching Sonarr library", 0, 1)
            result.all_series = sonarr.get_all_series()
            eligible_series = sonarr.filter_kept_series(result.all_series)
            kept_series = [s for s in result.all_series if s not in eligible_series]
            cb("Fetching Sonarr library", 1, 1)

            kept_series_paths = {s.path for s in kept_series}

            self._check_cancel(cancel_check)

            recent_seasons, old_seasons = build_season_summaries(result.episodes, threshold)

            cb("Matching seasons", 0, 2)
            recent_matched, recent_unmatched = match_seasons_to_sonarr(
                recent_seasons, result.all_series)
            old_matched, old_unmatched = match_seasons_to_sonarr(
                old_seasons, result.all_series)
            cb("Matching seasons", 2, 2)

            result.kept_season_matches = [
                s for s in recent_matched + old_matched
                if s.matched_sonarr_path in kept_series_paths
            ]
            result.recent_seasons_matched = [
                s for s in recent_matched
                if s.matched_sonarr_path not in kept_series_paths
            ]
            result.old_seasons_matched = [
                s for s in old_matched
                if s.matched_sonarr_path not in kept_series_paths
            ]
            result.recent_seasons_unmatched = recent_unmatched
            result.old_seasons_unmatched = old_unmatched

        return result

    # ------------------------------------------------------------------ #
    #  Internals
    # ------------------------------------------------------------------ #

    @staticmethod
    def _check_cancel(cancel_check: CancelCheck | None) -> None:
        if cancel_check is not None and cancel_check():
            raise CancellationError("Pipeline cancelled by caller")


# ------------------------------------------------------------------ #
#  Summary computation (presentation-agnostic)
# ------------------------------------------------------------------ #

def _unique_shows(seasons: list[SeasonSummary]) -> int:
    return len({s.series_name for s in seasons})


def _movie_size(matches: list[MatchResult]) -> int:
    return sum(m.size_on_disk for m in matches)


def _season_size(seasons: list[SeasonSummary]) -> int:
    return sum(s.size_on_disk for s in seasons)


def _format_size(total_bytes: int) -> str:
    gb = total_bytes / (1024 ** 3)
    if gb >= 1024:
        return f"{gb / 1024:.1f} TB"
    return f"{gb:.1f} GB"


def build_summary(result: CleanupResult, mode: str = "all") -> dict:
    """
    Compute summary statistics from a CleanupResult.

    Returns a dict with all the counts and sizes needed to render a
    summary table (CLI) or return as JSON (API).
    """
    recent_size = _movie_size(result.recent_movie_matches) + _season_size(result.recent_seasons_matched)
    old_size = _movie_size(result.old_movie_matches) + _season_size(result.old_seasons_matched)
    kept_size = _movie_size(result.kept_movie_matches) + _season_size(result.kept_season_matches)

    lib_size = (
        sum(m.size_on_disk for m in result.all_movies)
        + sum(s.statistics.size_on_disk for s in result.all_series)
    )
    never_watched_size = lib_size - recent_size - old_size - kept_size

    # Never-watched items
    all_movie_matches = result.recent_movie_matches + result.old_movie_matches
    watched_movie_paths = {
        m.matched_path for m in all_movie_matches + result.kept_movie_matches if m.matched_path
    }
    never_watched_movies = [m for m in result.all_movies if m.path not in watched_movie_paths]

    all_season_matches = (
        result.recent_seasons_matched + result.old_seasons_matched + result.kept_season_matches
    )
    watched_series_paths = {
        s.matched_sonarr_path for s in all_season_matches if s.matched_sonarr_path
    }
    never_watched_series = [s for s in result.all_series if s.path not in watched_series_paths]

    # Matching stats
    matched_seasons = result.recent_seasons_matched + result.old_seasons_matched
    all_seasons_list = (
        result.recent_seasons_matched + result.recent_seasons_unmatched
        + result.old_seasons_matched + result.old_seasons_unmatched
    )
    unmatched_seasons = result.recent_seasons_unmatched + result.old_seasons_unmatched

    # Space savings
    seasons_only_size = _movie_size(result.old_movie_matches) + _season_size(result.old_seasons_matched)
    entire_shows_size = _movie_size(result.old_movie_matches)
    if mode in ("all", "series") and result.old_seasons_matched:
        series_by_path = {s.path: s for s in result.all_series}
        old_series_paths = {
            s.matched_sonarr_path for s in result.old_seasons_matched if s.matched_sonarr_path
        }
        entire_shows_size += sum(
            series_by_path[p].statistics.size_on_disk
            for p in old_series_paths if p in series_by_path
        )

    # Episode resolution stats
    skipped_episodes = len(result.episode_dates) - len(result.episodes)
    fallback_episodes = sum(1 for ep in result.episodes if ep.season_number == -1)

    return {
        # Counts
        "recent_movie_count": len(result.recent_movie_matches),
        "old_movie_count": len(result.old_movie_matches),
        "recent_shows_count": _unique_shows(result.recent_seasons_matched),
        "recent_seasons_count": len(result.recent_seasons_matched),
        "old_shows_count": _unique_shows(result.old_seasons_matched),
        "old_seasons_count": len(result.old_seasons_matched),
        "never_watched_movie_count": len(never_watched_movies),
        "never_watched_series_count": len(never_watched_series),
        "library_movie_count": len(result.all_movies),
        "library_series_count": len(result.all_series),
        "kept_movie_count": len(result.kept_movie_matches),
        "kept_shows_count": _unique_shows(result.kept_season_matches),
        "kept_seasons_count": len(result.kept_season_matches),
        "matched_movie_count": sum(1 for m in all_movie_matches if m.is_matched),
        "matched_shows_count": _unique_shows(matched_seasons),
        "matched_seasons_count": len(matched_seasons),
        "ambiguous_movie_count": sum(1 for m in all_movie_matches if m.is_ambiguous),
        "ambiguous_shows_count": _unique_shows([s for s in all_seasons_list if s.is_ambiguous]),
        "ambiguous_seasons_count": sum(1 for s in all_seasons_list if s.is_ambiguous),
        "unmatched_movie_count": sum(1 for m in all_movie_matches if not m.is_matched),
        "unmatched_shows_count": _unique_shows(unmatched_seasons),
        "unmatched_seasons_count": len(unmatched_seasons),
        "skipped_episodes": skipped_episodes,
        "fallback_episodes": fallback_episodes,
        # Sizes (bytes)
        "recent_size": recent_size,
        "old_size": old_size,
        "kept_size": kept_size,
        "lib_size": lib_size,
        "never_watched_size": never_watched_size,
        "seasons_only_size": seasons_only_size,
        "entire_shows_size": entire_shows_size,
        # Formatted sizes (human-readable)
        "recent_size_fmt": _format_size(recent_size),
        "old_size_fmt": _format_size(old_size),
        "kept_size_fmt": _format_size(kept_size),
        "lib_size_fmt": _format_size(lib_size),
        "never_watched_size_fmt": _format_size(never_watched_size),
        "seasons_only_size_fmt": _format_size(seasons_only_size),
        "entire_shows_size_fmt": _format_size(entire_shows_size),
    }
