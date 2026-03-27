"""
Summary statistics models and builder.
"""
from __future__ import annotations
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult
from media_cleanup.types import MediaStatus

from .base import _Base, _format_size, _movie_size, _never_status, _season_size, _unique_shows


class CategoryStats(_Base):
    """Counts and sizes for a single watch category."""
    movie_count: int = 0
    shows_count: int = 0
    seasons_count: int = 0
    total_size: int = 0
    movie_size: int = 0
    series_size: int = 0
    series_size_greedy: int = 0
    total_size_fmt: str = ""
    movie_size_fmt: str = ""
    series_size_fmt: str = ""
    series_size_greedy_fmt: str = ""


class MatchingStats(_Base):
    """Counts for match quality categories."""
    matched_movie_count: int = 0
    matched_shows_count: int = 0
    matched_seasons_count: int = 0
    ambiguous_movie_count: int = 0
    ambiguous_shows_count: int = 0
    ambiguous_seasons_count: int = 0
    unmatched_movie_count: int = 0
    unmatched_shows_count: int = 0
    unmatched_seasons_count: int = 0
    collision_movie_count: int = 0
    collision_season_count: int = 0


class EpisodeStats(_Base):
    """Episode parsing stats."""
    skipped: int = 0
    unparseable: int = 0


class SpaceSavings(_Base):
    """Estimated disk savings from cleanup."""
    seasons_only_size: int = 0
    entire_shows_size: int = 0
    seasons_only_size_fmt: str = ""
    entire_shows_size_fmt: str = ""


class SummaryModel(_Base):
    """Structured summary statistics from a CleanupResult."""
    recent: CategoryStats = CategoryStats()
    old: CategoryStats = CategoryStats()
    never_watched: CategoryStats = CategoryStats()
    never_new: CategoryStats = CategoryStats()
    library: CategoryStats = CategoryStats()
    kept: CategoryStats = CategoryStats()
    matching: MatchingStats = MatchingStats()
    episodes: EpisodeStats = EpisodeStats()
    space_savings: SpaceSavings = SpaceSavings()


def _make_category(
    movie_count: int = 0,
    shows_count: int = 0,
    seasons_count: int = 0,
    movie_size: int = 0,
    series_size: int = 0,
    series_size_greedy: int = 0,
) -> CategoryStats:
    total = movie_size + series_size
    return CategoryStats(
        movie_count=movie_count,
        shows_count=shows_count,
        seasons_count=seasons_count,
        total_size=total,
        movie_size=movie_size,
        series_size=series_size,
        series_size_greedy=series_size_greedy,
        total_size_fmt=_format_size(total),
        movie_size_fmt=_format_size(movie_size),
        series_size_fmt=_format_size(series_size),
        series_size_greedy_fmt=_format_size(series_size_greedy),
    )


def build_summary(result: CleanupResult, mode: str = "all", added_threshold: int = 12) -> SummaryModel:
    """Compute structured summary statistics from a CleanupResult."""
    # Never-watched items -- split by added date
    all_movie_matches = result.recent_movie_matches + result.old_movie_matches
    watched_movie_paths = {
        m.matched_path for m in (
            all_movie_matches + result.kept_movie_matches
            + result.collision_movie_matches + result.auto_kept_movies
        ) if m.matched_path
    }
    all_season_matches = (
        result.recent_seasons_matched + result.old_seasons_matched
        + result.kept_season_matches + result.collision_season_matches
        + result.auto_kept_seasons
    )
    watched_series_paths = {
        s.matched_sonarr_path for s in all_season_matches if s.matched_sonarr_path
    }

    never_movies: list[Movie] = []
    never_new_movies: list[Movie] = []
    for m in result.all_movies:
        if m.path not in watched_movie_paths:
            (never_new_movies if _never_status(m.added, added_threshold) == MediaStatus.NEVER_NEW else never_movies).append(m)

    never_series: list[Series] = []
    never_new_series: list[Series] = []
    for s in result.all_series:
        if s.path not in watched_series_paths:
            (never_new_series if _never_status(s.added, added_threshold) == "never_new" else never_series).append(s)

    # Matching stats (exclude synthetic seasons -- they aren't "matched" from Jellyfin)
    matched_seasons = [s for s in result.recent_seasons_matched + result.old_seasons_matched if not s.is_unwatched]
    all_seasons_list = [
        s for s in (
            result.recent_seasons_matched + result.recent_seasons_unmatched
            + result.old_seasons_matched + result.old_seasons_unmatched
        ) if not s.is_unwatched
    ]
    unmatched_seasons = result.recent_seasons_unmatched + result.old_seasons_unmatched

    # Split watched vs synthetic (unwatched) seasons. Synthetic seasons in
    # recent_matched are "never_new" (active show), in old_matched are "never"
    # (abandoned show). They should not inflate recent/old greedy sizes.
    recent_watched = [s for s in result.recent_seasons_matched if not s.is_unwatched]
    recent_synthetic = [s for s in result.recent_seasons_matched if s.is_unwatched]
    old_watched = [s for s in result.old_seasons_matched if not s.is_unwatched]
    old_synthetic = [s for s in result.old_seasons_matched if s.is_unwatched]

    # Build per-category path sets for conservative series_size calculation.
    # - "not recently watched" (old): only if ALL seasons are old (none recent/kept)
    # - "recently watched": if ANY season is recent, the whole show counts
    # - "kept": if ANY season is kept, the whole show counts (highest priority)
    recent_paths: set[str] = set()
    old_paths: set[str] = set()
    kept_paths: set[str] = set()
    for s in result.recent_seasons_matched:
        if s.matched_sonarr_path:
            recent_paths.add(s.matched_sonarr_path)
    for s in result.old_seasons_matched:
        if s.matched_sonarr_path:
            old_paths.add(s.matched_sonarr_path)
    for s in result.kept_season_matches + result.auto_kept_seasons:
        if s.matched_sonarr_path:
            kept_paths.add(s.matched_sonarr_path)

    # Conservative (series_size): each series assigned to exactly one bucket.
    # Priority: kept > recent > old. Adds up to library total.
    cons_kept = kept_paths
    cons_recent = recent_paths - kept_paths
    cons_old = old_paths - recent_paths - kept_paths

    series_by_path = {s.path: s for s in result.all_series}

    def _full_series_size(paths: set[str]) -> int:
        return sum(
            series_by_path[p].statistics.size_on_disk
            for p in paths if p in series_by_path
        )

    # Space savings (only watched old seasons, not synthetics)
    seasons_only = _movie_size(result.old_movie_matches) + _season_size(old_watched)
    entire_shows = _movie_size(result.old_movie_matches)
    if mode in ("all", "series") and old_watched:
        entire_shows += _full_series_size(old_paths)

    # Greedy synthetic sizes: never_new gets synthetics from active shows,
    # never_watched gets synthetics from abandoned shows.
    synthetic_never_new_size = _season_size(recent_synthetic)
    synthetic_never_size = _season_size(old_synthetic)

    return SummaryModel(
        recent=_make_category(
            movie_count=len(result.recent_movie_matches),
            shows_count=_unique_shows(recent_watched),
            seasons_count=len(recent_watched),
            movie_size=_movie_size(result.recent_movie_matches),
            series_size=_full_series_size(cons_recent),
            series_size_greedy=_season_size(recent_watched),
        ),
        old=_make_category(
            movie_count=len(result.old_movie_matches),
            shows_count=_unique_shows(old_watched),
            seasons_count=len(old_watched),
            movie_size=_movie_size(result.old_movie_matches),
            series_size=_full_series_size(cons_old),
            series_size_greedy=_season_size(old_watched),
        ),
        never_watched=_make_category(
            movie_count=len(never_movies),
            shows_count=len(never_series),
            movie_size=sum(m.size_on_disk for m in never_movies),
            series_size=sum(s.statistics.size_on_disk for s in never_series),
            series_size_greedy=sum(s.statistics.size_on_disk for s in never_series) + synthetic_never_size,
        ),
        never_new=_make_category(
            movie_count=len(never_new_movies),
            shows_count=len(never_new_series),
            movie_size=sum(m.size_on_disk for m in never_new_movies),
            series_size=sum(s.statistics.size_on_disk for s in never_new_series),
            series_size_greedy=sum(s.statistics.size_on_disk for s in never_new_series) + synthetic_never_new_size,
        ),
        library=_make_category(
            movie_count=len(result.all_movies),
            shows_count=len(result.all_series),
            movie_size=sum(m.size_on_disk for m in result.all_movies),
            series_size=sum(s.statistics.size_on_disk for s in result.all_series),
            series_size_greedy=sum(s.statistics.size_on_disk for s in result.all_series),
        ),
        kept=_make_category(
            movie_count=len(result.kept_movie_matches) + len(result.auto_kept_movies),
            shows_count=_unique_shows(result.kept_season_matches + result.auto_kept_seasons),
            seasons_count=len(result.kept_season_matches) + len(result.auto_kept_seasons),
            movie_size=_movie_size(result.kept_movie_matches + result.auto_kept_movies),
            series_size=_full_series_size(cons_kept),
            series_size_greedy=_season_size(result.kept_season_matches + result.auto_kept_seasons),
        ),
        matching=MatchingStats(
            matched_movie_count=sum(1 for m in all_movie_matches if m.is_matched),
            matched_shows_count=_unique_shows(matched_seasons),
            matched_seasons_count=len(matched_seasons),
            ambiguous_movie_count=sum(1 for m in all_movie_matches if m.is_ambiguous),
            ambiguous_shows_count=_unique_shows([s for s in all_seasons_list if s.is_ambiguous]),
            ambiguous_seasons_count=sum(1 for s in all_seasons_list if s.is_ambiguous),
            unmatched_movie_count=sum(1 for m in all_movie_matches if not m.is_matched),
            unmatched_shows_count=_unique_shows(unmatched_seasons),
            unmatched_seasons_count=len(unmatched_seasons),
            collision_movie_count=len(result.collision_movie_matches),
            collision_season_count=len(result.collision_season_matches),
        ),
        episodes=EpisodeStats(
            skipped=len(result.episode_dates) - len(result.episodes),
            unparseable=sum(1 for ep in result.episodes if ep.season_number == -1),
        ),
        space_savings=SpaceSavings(
            seasons_only_size=seasons_only,
            entire_shows_size=entire_shows,
            seasons_only_size_fmt=_format_size(seasons_only),
            entire_shows_size_fmt=_format_size(entire_shows),
        ),
    )
