"""
Reusable service layer for the media cleanup pipeline.

Extracts the orchestration logic from launch.py so it can be driven by
the CLI, a FastAPI endpoint, or any other caller.
"""

from collections import Counter, defaultdict
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
    collision_movie_matches: list[MatchResult] = field(default_factory=list)
    collision_season_matches: list[SeasonSummary] = field(default_factory=list)
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

        step_offsets, total_weight = get_pipeline_steps(mode)

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

            # Resolve recent and old paths separately. Jellyfin silently drops
            # stale IDs, so a combined call returns fewer results than inputs
            # and the slice indices would be wrong.
            # Progress uses offset-based totals so first call fills 0-50%, second 50-100%.
            n_recent_chunks = max(1, -(-len(recent_movie_ids) // jellyfin.chunk_length))
            n_old_chunks = max(1, -(-len(old_movie_ids) // jellyfin.chunk_length))
            n_total_chunks = n_recent_chunks + n_old_chunks
            recent_movie_paths = jellyfin.get_file_paths(
                recent_movie_ids,
                progress_callback=lambda s, c, t: cb("Resolving movie paths", c, n_total_chunks),
                desc="Resolving movie paths",
                cancel_check=cancel_check,
            )
            old_movie_paths = jellyfin.get_file_paths(
                old_movie_ids,
                progress_callback=lambda s, c, t: cb("Resolving movie paths", n_recent_chunks + c, n_total_chunks),
                desc="Resolving movie paths",
                cancel_check=cancel_check,
            )

            self._check_cancel(cancel_check)

            cb("Fetching Radarr library", 0, 1)
            result.all_movies = radarr.get_all_movies()
            eligible_movies = radarr.filter_kept_movies(result.all_movies)
            kept_movies = [m for m in result.all_movies if m not in eligible_movies]
            cb("Fetching Radarr library", 1, 1)

            kept_movie_paths = {m.path for m in kept_movies}

            self._check_cancel(cancel_check)

            recent_movie_matches, recent_unmatched = match_movies_by_path(
                recent_movie_paths, result.all_movies,
                progress_callback=lambda s, c, t: cb("Matching movies", c, t))
            old_movie_matches, old_unmatched = match_movies_by_path(
                old_movie_paths, result.all_movies,
                progress_callback=lambda s, c, t: cb("Matching movies", c, t))
            recent_movie_matches += fuzzy_match_movies(
                recent_unmatched, result.all_movies,
                progress_callback=lambda s, c, t: cb("Matching movies", c, t))
            old_movie_matches += fuzzy_match_movies(
                old_unmatched, result.all_movies,
                progress_callback=lambda s, c, t: cb("Matching movies", c, t))

            # Detect movie collisions: multiple Jellyfin items -> same library path
            path_counts = Counter(
                m.matched_path for m in recent_movie_matches + old_movie_matches
                if m.matched_path
            )
            collision_movie_paths = {p for p, c in path_counts.items() if c > 1}

            result.collision_movie_matches = [
                m for m in recent_movie_matches + old_movie_matches
                if m.matched_path in collision_movie_paths
            ]
            result.kept_movie_matches = [
                m for m in recent_movie_matches + old_movie_matches
                if m.matched_path in kept_movie_paths
                and m.matched_path not in collision_movie_paths
            ]
            exclude_movie_paths = kept_movie_paths | collision_movie_paths
            result.recent_movie_matches = [
                m for m in recent_movie_matches
                if m.matched_path not in exclude_movie_paths
            ]
            result.old_movie_matches = [
                m for m in old_movie_matches
                if m.matched_path not in exclude_movie_paths
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
            result.episodes = jellyfin.get_episode_metadata(
                result.episode_dates, progress_callback=cb, cancel_check=cancel_check)

            self._check_cancel(cancel_check)

            cb("Fetching Sonarr library", 0, 1)
            result.all_series = sonarr.get_all_series()
            eligible_series = sonarr.filter_kept_series(result.all_series)
            kept_series = [s for s in result.all_series if s not in eligible_series]
            cb("Fetching Sonarr library", 1, 1)

            kept_series_paths = {s.path for s in kept_series}

            self._check_cancel(cancel_check)

            recent_seasons, old_seasons = build_season_summaries(result.episodes, threshold)

            n_recent = len(recent_seasons)
            n_total = n_recent + len(old_seasons)
            def _seasons_cb(_, c, t):
                cb("Matching seasons", c, n_total)
            def _seasons_cb2(_, c, t):
                cb("Matching seasons", n_recent + c, n_total)
            recent_matched, recent_unmatched = match_seasons_to_sonarr(
                recent_seasons, result.all_series, progress_callback=_seasons_cb)
            old_matched, old_unmatched = match_seasons_to_sonarr(
                old_seasons, result.all_series, progress_callback=_seasons_cb2)

            # Detect series collisions: different series names -> same Sonarr path
            path_to_names: dict[str, set[str]] = defaultdict(set)
            for s in recent_matched + old_matched:
                if s.matched_sonarr_path:
                    path_to_names[s.matched_sonarr_path].add(s.series_name)
            collision_series_paths = {p for p, names in path_to_names.items() if len(names) > 1}

            result.collision_season_matches = [
                s for s in recent_matched + old_matched
                if s.matched_sonarr_path in collision_series_paths
            ]
            exclude_series_paths = kept_series_paths | collision_series_paths
            result.kept_season_matches = [
                s for s in recent_matched + old_matched
                if s.matched_sonarr_path in kept_series_paths
                and s.matched_sonarr_path not in collision_series_paths
            ]
            result.recent_seasons_matched = [
                s for s in recent_matched
                if s.matched_sonarr_path not in exclude_series_paths
            ]
            result.old_seasons_matched = [
                s for s in old_matched
                if s.matched_sonarr_path not in exclude_series_paths
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
#  Pipeline step metadata (shared between service and CLI)
# ------------------------------------------------------------------ #

MOVIE_STEPS: list[tuple[str, int]] = [
    ("Querying Jellyfin movie history", 2),
    ("Resolving movie paths", 3),
    ("Fetching Radarr library", 5),
    ("Matching movies", 5),
]
SERIES_STEPS: list[tuple[str, int]] = [
    ("Querying Jellyfin episode history", 2),
    ("Resolving episodes", 60),
    ("Fetching Sonarr library", 8),
    ("Matching seasons", 5),
]


def get_pipeline_steps(mode: str) -> tuple[dict[str, tuple[int, int]], int]:
    """
    Return ``(step_offsets, total_weight)`` for the given analysis mode.

    ``step_offsets`` maps each base step name to ``(global_offset, weight)``
    so callers can convert global progress values back to per-step local ones.
    """
    steps: list[tuple[str, int]] = []
    if mode in ("all", "movies"):
        steps += MOVIE_STEPS
    if mode in ("all", "series"):
        steps += SERIES_STEPS
    total_weight = sum(w for _, w in steps)
    offsets: dict[str, tuple[int, int]] = {}
    offset = 0
    for name, weight in steps:
        offsets[name] = (offset, weight)
        offset += weight
    return offsets, total_weight

