"""
Pydantic models for the media-cleanup pipeline.

Shared between the CLI and the REST API server. Uses the same camelCase
alias pattern as the existing schema files for API-facing models.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel

from media_cleanup.matching import MatchResult
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult
from media_cleanup.types import SeasonSummary


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# ------------------------------------------------------------------
#  Helpers (moved from service.py)
# ------------------------------------------------------------------

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


def _never_status(added: str, threshold_months: int) -> str:
    """Return 'never_new' if the item was added within threshold_months, else 'never'."""
    if not added:
        return "never"
    try:
        added_dt = datetime.fromisoformat(added.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_months * 30)
        return "never_new" if added_dt >= cutoff else "never"
    except (ValueError, TypeError):
        return "never"


# ------------------------------------------------------------------
#  Request / enum
# ------------------------------------------------------------------

class AnalysisRequest(_Base):
    mode: str = "all"
    month_threshold: int = 6
    added_threshold: int = 12  # months -- never-watched items added within this are "never_new"


class JobStatus(str, Enum):
    queued = "queued"
    running = "running"
    complete = "complete"
    cancelled = "cancelled"
    failed = "failed"


# ------------------------------------------------------------------
#  Job
# ------------------------------------------------------------------

class JobResponse(_Base):
    job_id: str
    status: JobStatus
    progress_percent: float = 0
    progress_step: str = ""
    created_at: str
    completed_at: str | None = None
    error: str | None = None


# ------------------------------------------------------------------
#  Analysis result models
# ------------------------------------------------------------------

class MovieMatch(_Base):
    title: str | None = None
    jellyfin_path: str
    library_path: str | None = None
    match_method: str | None = None
    fuzzy_score: float | None = None
    size_bytes: int = 0
    is_ambiguous: bool = False
    ambiguity_reason: str | None = None
    ambiguous_candidates: list[dict[str, Any]] = []
    added: str = ""  # ISO 8601 from Radarr
    status: str = ""


class SeasonInfo(_Base):
    season_number: int
    last_played: str
    episode_count: int
    total_episodes: int = 0
    size_bytes: int = 0
    status: str = ""  # "recent", "old", "kept", "unmatched", "never"
    is_unwatched: bool = False  # True for synthetic seasons with no watch history


class SeriesGroup(_Base):
    title: str
    library_path: str | None = None
    match_method: str | None = None
    fuzzy_score: float | None = None
    size_bytes: int = 0
    status: str = ""  # "recent", "old", "mixed", "kept", "unmatched", "never", "never_new", "collision"
    added: str = ""  # ISO 8601 from Sonarr
    seasons: list[SeasonInfo] = []
    colliding_names: list[str] = []  # populated for collision entries


class MediaSection(_Base):
    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []


# ------------------------------------------------------------------
#  Summary sub-models
# ------------------------------------------------------------------

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
    """Episode resolution stats."""
    skipped: int = 0
    fallback: int = 0


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


class AnalysisResult(_Base):
    recently_watched: MediaSection
    not_recently_watched: MediaSection
    keep: MediaSection
    collision: MediaSection
    unmatched: MediaSection
    never_watched: MediaSection
    never_new: MediaSection  # never watched but recently added
    summary: SummaryModel


class FilterRequest(_Base):
    """User's category selections for filtering."""
    categories: list[str]  # subset of: "old", "never", "never_new"
    greedy: bool = False    # True = include mixed-status series

    @field_validator("categories")
    @classmethod
    def validate_categories(cls, v: list[str]) -> list[str]:
        allowed = {"old", "never", "never_new"}
        invalid = set(v) - allowed
        if invalid:
            raise ValueError(f"Invalid categories: {invalid}. Allowed: {allowed}")
        return v


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


class ProgressMessage(_Base):
    """WebSocket progress message."""
    type: str
    job_id: str
    step: str | None = None
    percent: float | None = None
    error: str | None = None


# ------------------------------------------------------------------
#  Summary builder
# ------------------------------------------------------------------

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
        m.matched_path for m in all_movie_matches + result.kept_movie_matches if m.matched_path
    }
    all_season_matches = (
        result.recent_seasons_matched + result.old_seasons_matched + result.kept_season_matches
    )
    watched_series_paths = {
        s.matched_sonarr_path for s in all_season_matches if s.matched_sonarr_path
    }

    never_movies: list[Movie] = []
    never_new_movies: list[Movie] = []
    for m in result.all_movies:
        if m.path not in watched_movie_paths:
            (never_new_movies if _never_status(m.added, added_threshold) == "never_new" else never_movies).append(m)

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
    for s in result.kept_season_matches:
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
            movie_count=len(result.kept_movie_matches),
            shows_count=_unique_shows(result.kept_season_matches),
            seasons_count=len(result.kept_season_matches),
            movie_size=_movie_size(result.kept_movie_matches),
            series_size=_full_series_size(cons_kept),
            series_size_greedy=_season_size(result.kept_season_matches),
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
            fallback=sum(1 for ep in result.episodes if ep.season_number == -1),
        ),
        space_savings=SpaceSavings(
            seasons_only_size=seasons_only,
            entire_shows_size=entire_shows,
            seasons_only_size_fmt=_format_size(seasons_only),
            entire_shows_size_fmt=_format_size(entire_shows),
        ),
    )


# ------------------------------------------------------------------
#  Converters
# ------------------------------------------------------------------

def _title_from_path(path: str) -> str:
    """Extract a readable title from a file path for unmatched items."""
    normalized = path.replace('\\', '/')
    parts = [p for p in normalized.split('/') if p]
    if len(parts) >= 2:
        return parts[-2]  # parent folder is typically the movie name
    return parts[-1] if parts else path


def match_result_to_model(mr: MatchResult, status: str = "") -> MovieMatch:
    title = mr.matched_title or _title_from_path(mr.jellyfin_path)
    return MovieMatch(
        title=title,
        jellyfin_path=mr.jellyfin_path,
        library_path=mr.matched_path,
        match_method=mr.match_method,
        fuzzy_score=mr.score,
        size_bytes=mr.size_on_disk,
        is_ambiguous=mr.is_ambiguous,
        ambiguity_reason=mr.ambiguity_reason,
        ambiguous_candidates=mr.ambiguous_candidates,
        status=status,
    )


def _derive_show_status(season_statuses: set[str]) -> str:
    """Derive a show-level status from the set of its season statuses."""
    if len(season_statuses) == 1:
        return next(iter(season_statuses))
    return "mixed"


def _build_all_series_groups(
    result: CleanupResult,
    added_threshold: int = 12,
) -> list[SeriesGroup]:
    """
    Merge ALL seasons across all categories into one SeriesGroup per show.
    Each season and show gets a status tag.
    """
    # Sonarr lookup for total episode counts
    sonarr_lookup: dict[str, dict[int, int]] = {}
    for s in result.all_series:
        sonarr_lookup[s.path] = {
            sn.season_number: sn.statistics.total_episode_count
            for sn in s.seasons
        }

    # Collect all seasons with their status.
    # Synthetic (unwatched) seasons get overridden: "recent" list → "never_new"
    # (show is active), "old" list → "never" (show is abandoned).
    tagged: list[tuple[SeasonSummary, str]] = []
    for s in result.recent_seasons_matched:
        tagged.append((s, "never_new" if s.is_unwatched else "recent"))
    for s in result.old_seasons_matched:
        tagged.append((s, "never" if s.is_unwatched else "old"))
    for s in result.kept_season_matches:
        tagged.append((s, "kept"))
    for s in result.recent_seasons_unmatched + result.old_seasons_unmatched:
        tagged.append((s, "unmatched"))
    for s in result.collision_season_matches:
        tagged.append((s, "collision"))

    # Group by show key
    grouped: dict[str, list[tuple[SeasonSummary, str]]] = defaultdict(list)
    for s, status in tagged:
        key = s.matched_sonarr_path or s.series_name
        grouped[key].append((s, status))

    # Build SeriesGroup per show
    groups: list[SeriesGroup] = []
    for key, season_list in grouped.items():
        sorted_seasons = sorted(season_list, key=lambda x: x[0].season_number)
        first_season = sorted_seasons[0][0]
        season_statuses = {status for _, status in sorted_seasons}
        sonarr_seasons = sonarr_lookup.get(key, {})

        distinct_names = sorted({s.series_name for s, _ in sorted_seasons})
        groups.append(SeriesGroup(
            title=first_season.series_name,
            library_path=first_season.matched_sonarr_path,
            match_method=first_season.match_method,
            fuzzy_score=first_season.fuzzy_score,
            status=_derive_show_status(season_statuses),
            colliding_names=distinct_names if len(distinct_names) > 1 else [],
            size_bytes=sum(s.size_on_disk for s, _ in sorted_seasons),
            seasons=[
                SeasonInfo(
                    season_number=s.season_number,
                    last_played=s.last_played,
                    episode_count=s.episode_count,
                    total_episodes=sonarr_seasons.get(s.season_number, 0),
                    size_bytes=s.size_on_disk,
                    status=status,
                    is_unwatched=s.is_unwatched,
                )
                for s, status in sorted_seasons
            ],
        ))

    # Add never-watched series
    watched_paths = {s.matched_sonarr_path for s, _ in tagged if s.matched_sonarr_path}
    for series in result.all_series:
        if series.path not in watched_paths:
            never_status = _never_status(series.added, added_threshold)
            groups.append(SeriesGroup(
                title=series.title,
                library_path=series.path,
                status=never_status,
                added=series.added,
                size_bytes=series.statistics.size_on_disk,
                seasons=[
                    SeasonInfo(
                        season_number=sn.season_number,
                        last_played="",
                        episode_count=0,
                        total_episodes=sn.statistics.total_episode_count,
                        size_bytes=sn.statistics.size_on_disk,
                        status=never_status,
                    )
                    for sn in series.seasons
                    if sn.season_number > 0
                ],
            ))

    groups.sort(key=lambda g: g.title.lower())
    return groups


def _movie_to_match(movie: Movie, status: str = "never") -> MovieMatch:
    """Convert a Radarr Movie to a MovieMatch model (for never-watched items)."""
    return MovieMatch(
        title=movie.title,
        jellyfin_path="",
        library_path=movie.path,
        size_bytes=movie.size_on_disk,
        added=movie.added,
        status=status,
    )


def cleanup_result_to_response(
    result: CleanupResult,
    mode: str,
    added_threshold: int = 12,
) -> AnalysisResult:
    """Convert a CleanupResult into the API AnalysisResult model."""
    # Movies -- split by category, never-watched split by added date
    all_matches = result.recent_movie_matches + result.old_movie_matches + result.kept_movie_matches
    watched_movie_paths = {m.matched_path for m in all_matches if m.matched_path}
    never_movies: list[MovieMatch] = []
    never_new_movies: list[MovieMatch] = []
    for m in result.all_movies:
        if m.path not in watched_movie_paths:
            status = _never_status(m.added, added_threshold)
            match = _movie_to_match(m, status=status)
            if status == "never_new":
                never_new_movies.append(match)
            else:
                never_movies.append(match)

    # Series -- unified: one entry per show, placed in one category by status
    all_series_groups = _build_all_series_groups(result, added_threshold)
    series_by_cat: dict[str, list[SeriesGroup]] = defaultdict(list)
    for g in all_series_groups:
        if g.status == "recent":
            series_by_cat["recent"].append(g)
        elif g.status in ("old", "mixed"):
            series_by_cat["old"].append(g)
        elif g.status == "kept":
            series_by_cat["kept"].append(g)
        elif g.status == "collision":
            series_by_cat["collision"].append(g)
        elif g.status == "unmatched":
            series_by_cat["unmatched"].append(g)
        elif g.status == "never":
            series_by_cat["never"].append(g)
        elif g.status == "never_new":
            series_by_cat["never_new"].append(g)

    return AnalysisResult(
        recently_watched=MediaSection(
            movies=[match_result_to_model(m, status="recent") for m in result.recent_movie_matches],
            series=series_by_cat.get("recent", []),
        ),
        not_recently_watched=MediaSection(
            movies=[match_result_to_model(m, status="old") for m in result.old_movie_matches],
            series=series_by_cat.get("old", []),
        ),
        keep=MediaSection(
            movies=[match_result_to_model(m, status="kept") for m in result.kept_movie_matches],
            series=series_by_cat.get("kept", []),
        ),
        collision=MediaSection(
            movies=[match_result_to_model(m, status="collision") for m in result.collision_movie_matches],
            series=series_by_cat.get("collision", []),
        ),
        unmatched=MediaSection(
            movies=[
                match_result_to_model(m, status="unmatched")
                for m in result.recent_movie_matches + result.old_movie_matches
                if not m.is_matched
            ],
            series=series_by_cat.get("unmatched", []),
        ),
        never_watched=MediaSection(
            movies=never_movies,
            series=series_by_cat.get("never", []),
        ),
        never_new=MediaSection(
            movies=never_new_movies,
            series=series_by_cat.get("never_new", []),
        ),
        summary=build_summary(result, mode, added_threshold),
    )


def filter_analysis_result(
    result: AnalysisResult,
    categories: list[str],
    greedy: bool = False,
) -> FilteredResult:
    """Filter an AnalysisResult down to user-selected categories.

    Args:
        result: The full analysis result to filter.
        categories: Category names to include ("old", "never", "never_new").
        greedy: If True, include mixed-status series. If False, exclude them.

    Returns:
        A FilteredResult with only items from the selected categories.
    """
    section_map: dict[str, MediaSection] = {
        "old": result.not_recently_watched,
        "never": result.never_watched,
        "never_new": result.never_new,
    }

    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []

    for cat in categories:
        section = section_map.get(cat)
        if section is None:
            continue
        movies.extend(section.movies)
        for s in section.series:
            if not greedy and s.status == "mixed":
                continue
            # Recalculate size_bytes to only sum seasons matching selected categories
            matching_size = sum(
                sn.size_bytes for sn in s.seasons if sn.status in categories
            )
            series.append(s.model_copy(update={"size_bytes": matching_size}))

    total_size = (
        sum(m.size_bytes for m in movies)
        + sum(s.size_bytes for s in series)
    )

    # Count only seasons whose status matches the selected categories
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
