"""
Run plan models and generation.
"""
from __future__ import annotations
from typing import Sequence
from .base import _Base, _format_size
from .filter import FilteredResult


class MovieDeletion(_Base):
    """A movie to delete from Radarr."""
    radarr_id: int
    title: str
    library_path: str
    size_bytes: int


class FullSeriesDeletion(_Base):
    """An entire series to delete from Sonarr."""
    sonarr_series_id: int
    title: str
    library_path: str
    size_bytes: int
    season_count: int


class SeasonCleanup(_Base):
    """Partial season cleanup: delete episode files and unmonitor seasons."""
    sonarr_series_id: int
    title: str
    library_path: str
    season_numbers: list[int]
    total_size_bytes: int
    episode_file_count: int
    total_season_count: int = 0
    total_episode_count: int = 0


class RunPlanSummary(_Base):
    """Counts and totals for a run plan."""
    movie_count: int = 0
    full_series_count: int = 0
    season_cleanup_count: int = 0
    total_size: int = 0
    total_size_fmt: str = ""


class RunPlan(_Base):
    """Dry-run deletion plan showing exactly what API calls will be made."""
    movies: list[MovieDeletion] = []
    full_series: list[FullSeriesDeletion] = []
    season_cleanups: list[SeasonCleanup] = []
    summary: RunPlanSummary = RunPlanSummary()


def build_run_plan(
    filtered: FilteredResult,
    categories: Sequence[str] | None = None,
    greedy: bool = True,
) -> RunPlan:
    """Build a dry-run deletion plan from a filtered result.

    Determines which Radarr/Sonarr API calls would be needed to delete
    the filtered items. Series are split into full deletions (all seasons
    selected) vs partial cleanups (only some seasons selected).

    Args:
        filtered: The filtered analysis result.
        categories: Active category filters (e.g. ["old", "never"]). When provided,
            only seasons whose status matches are considered for the plan.
            When None, all seasons in the filtered result are used.
        greedy: When True (default), partial season cleanups are emitted for shows
            where only some seasons are eligible. When False, only full-series
            deletions are emitted -- any show that doesn't cover all on-disk seasons
            is dropped entirely. greedy=False also conservatively drops shows where
            total_season_count is 0 (unknown total) because we cannot confirm full
            coverage.
    """
    movie_deletions: list[MovieDeletion] = []
    full_series_deletions: list[FullSeriesDeletion] = []
    season_cleanups: list[SeasonCleanup] = []

    # Movies with a radarr_id become MovieDeletion entries
    for m in filtered.movies:
        if m.radarr_id is not None:
            movie_deletions.append(MovieDeletion(
                radarr_id=m.radarr_id,
                title=m.title or "",
                library_path=m.library_path or "",
                size_bytes=m.size_bytes,
            ))

    # Series: compare eligible seasons against total on-disk seasons
    for sg in filtered.series:
        if sg.sonarr_series_id is None:
            continue

        # Only count seasons whose status matches the active categories
        eligible = [sn for sn in sg.seasons if sn.status in categories] if categories else sg.seasons
        filtered_season_numbers = sorted(sn.season_number for sn in eligible)

        if not filtered_season_numbers:
            continue

        # Compare filtered seasons against the total on-disk seasons from Sonarr.
        # total == 0 means the Sonarr lookup missed; we cannot confirm full coverage.
        total = sg.total_season_count
        all_seasons_present = total > 0 and len(filtered_season_numbers) >= total

        if greedy:
            # greedy=True: full deletion when all seasons present (or unknown total
            # as a best-effort fallback); partial cleanup otherwise.
            if total == 0 or all_seasons_present:
                full_series_deletions.append(FullSeriesDeletion(
                    sonarr_series_id=sg.sonarr_series_id,
                    title=sg.title,
                    library_path=sg.library_path or "",
                    size_bytes=sg.size_bytes,
                    season_count=sg.total_season_count,
                ))
            else:
                episode_file_count = sum(sn.total_episodes for sn in eligible)
                total_episode_count = sum(sn.total_episodes for sn in sg.seasons)
                season_cleanups.append(SeasonCleanup(
                    sonarr_series_id=sg.sonarr_series_id,
                    title=sg.title,
                    library_path=sg.library_path or "",
                    season_numbers=filtered_season_numbers,
                    total_size_bytes=sg.size_bytes,
                    episode_file_count=episode_file_count,
                    total_season_count=sg.total_season_count,
                    total_episode_count=total_episode_count,
                ))
        else:
            # greedy=False: only emit full-series deletions. Partial coverage and
            # unknown totals (total == 0) are both dropped -- we cannot confirm
            # the user is cleaning up the entire show.
            if all_seasons_present:
                full_series_deletions.append(FullSeriesDeletion(
                    sonarr_series_id=sg.sonarr_series_id,
                    title=sg.title,
                    library_path=sg.library_path or "",
                    size_bytes=sg.size_bytes,
                    season_count=sg.total_season_count,
                ))

    total_size = (
        sum(md.size_bytes for md in movie_deletions)
        + sum(fs.size_bytes for fs in full_series_deletions)
        + sum(sc.total_size_bytes for sc in season_cleanups)
    )

    return RunPlan(
        movies=movie_deletions,
        full_series=full_series_deletions,
        season_cleanups=season_cleanups,
        summary=RunPlanSummary(
            movie_count=len(movie_deletions),
            full_series_count=len(full_series_deletions),
            season_cleanup_count=len(season_cleanups),
            total_size=total_size,
            total_size_fmt=_format_size(total_size),
        ),
    )
