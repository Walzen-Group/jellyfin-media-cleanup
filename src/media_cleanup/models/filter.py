"""
Filter models and result filtering.
"""
from __future__ import annotations
from typing import Sequence
from media_cleanup.types import FilterCategory, MediaMode, MediaStatus
from .base import _Base, _format_size
from .analysis import AnalysisResult, MediaSection, MovieMatch, SeriesGroup


class FilterRequest(_Base):
    """User's category selections for filtering."""
    categories: list[FilterCategory]
    greedy: bool = False
    media_type: MediaMode = "all"
    min_size_bytes: int = 0
    max_size_bytes: int | None = None  # None = no upper limit


class FilteredSummary(_Base):
    """Summary counts for a filtered result set."""
    movie_count: int = 0
    series_count: int = 0
    season_count: int = 0
    total_size: int = 0
    total_size_fmt: str = ""
    total_movie_count: int = 0
    total_series_count: int = 0
    total_season_count: int = 0
    total_library_size: int = 0
    total_library_size_fmt: str = ""


class FilteredResult(_Base):
    """Filtered analysis result containing only user-selected categories."""
    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []
    summary: FilteredSummary = FilteredSummary()


def filter_analysis_result(
    result: AnalysisResult,
    categories: Sequence[str],
    greedy: bool = False,
    media_type: str = "all",
    min_size_bytes: int = 0,
    max_size_bytes: int | None = None,
) -> FilteredResult:
    """Filter an AnalysisResult down to user-selected categories.

    Args:
        result: The full analysis result to filter.
        categories: Category names to include ("old", "never", "never_new").
        greedy: If True, include mixed-status series. If False, exclude them.
        min_size_bytes: Exclude items smaller than this threshold (inclusive lower bound).
        max_size_bytes: Exclude items larger than this threshold, or None for no upper limit.

    Returns:
        A FilteredResult with only items from the selected categories.
    """
    section_map: dict[str, MediaSection] = {
        "old": result.not_recently_watched,
        "never": result.never_watched,
        "never_new": result.never_new,
        "unmatched": result.unmatched,
    }
    unmatched_selected = "unmatched" in categories

    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []

    for cat in categories:
        section = section_map.get(cat)
        if section is None:
            continue
        # When the unmatched category is opted in, UNMATCHED-status items are
        # legitimate prune targets; otherwise keep the historical safety filter.
        for m in section.movies:
            if m.status == MediaStatus.UNMATCHED and not unmatched_selected:
                continue
            movies.append(m)
        for s in section.series:
            if s.status == MediaStatus.UNMATCHED and not unmatched_selected:
                continue
            if not greedy and s.status == MediaStatus.MIXED:
                continue
            eligible_seasons = [sn for sn in s.seasons if sn.status in categories]
            if not eligible_seasons:
                continue
            matching_size = sum(sn.size_bytes for sn in eligible_seasons)
            # Keep all seasons visible so the frontend can grey out non-matching
            # ones via activeCategories. Only recalculate size from eligible.
            all_visible_seasons = (
                list(s.seasons)
                if unmatched_selected
                else [sn for sn in s.seasons if sn.status != MediaStatus.UNMATCHED]
            )
            series.append(s.model_copy(update={
                "size_bytes": matching_size,
                "seasons": all_visible_seasons,
            }))

    # Apply media_type filter
    if media_type == "movies":
        series = []
    elif media_type == "series":
        movies = []

    # Apply size range filter
    def _in_range(size: int) -> bool:
        if size < min_size_bytes:
            return False
        if max_size_bytes is not None and size > max_size_bytes:
            return False
        return True

    movies = [m for m in movies if _in_range(m.size_bytes)]
    series = [s for s in series if _in_range(s.size_bytes)]

    total_size = (
        sum(m.size_bytes for m in movies)
        + sum(s.size_bytes for s in series)
    )

    # Count only seasons whose status matches the selected categories
    # (unmatched seasons are already excluded from the series above)
    matching_season_count = sum(
        1 for s in series for sn in s.seasons if sn.status in categories
    )

    # Compute totals across ALL sections of the full result.
    # Unmatched movies are duplicates of recent+old (see line ~643), so exclude them.
    all_sections = [
        result.recently_watched,
        result.not_recently_watched,
        result.keep,
        result.collision,
        result.never_watched,
        result.never_new,
    ]
    unmatched_section = result.unmatched

    total_movie_count = sum(len(sec.movies) for sec in all_sections)
    total_movie_size = sum(m.size_bytes for sec in all_sections for m in sec.movies)

    all_series_sections = all_sections + [unmatched_section]
    total_series_count = sum(len(sec.series) for sec in all_series_sections)
    total_season_count = sum(
        len(s.seasons) for sec in all_series_sections for s in sec.series
    )
    total_series_size = sum(
        s.size_bytes for sec in all_series_sections for s in sec.series
    )

    total_library_size = total_movie_size + total_series_size

    return FilteredResult(
        movies=movies,
        series=series,
        summary=FilteredSummary(
            movie_count=len(movies),
            series_count=len(series),
            season_count=matching_season_count,
            total_size=total_size,
            total_size_fmt=_format_size(total_size),
            total_movie_count=total_movie_count,
            total_series_count=total_series_count,
            total_season_count=total_season_count,
            total_library_size=total_library_size,
            total_library_size_fmt=_format_size(total_library_size),
        ),
    )
