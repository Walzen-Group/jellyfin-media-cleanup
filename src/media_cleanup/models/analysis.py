"""
Analysis models and builders.
"""
from __future__ import annotations
from collections import defaultdict
from typing import Any

from media_cleanup.matching import MatchResult
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult
from media_cleanup.types import MatchMethod, MediaMode, MediaStatus, SeasonSummary

from .base import _Base, _never_status
from .summary import SummaryModel, build_summary


class AnalysisRequest(_Base):
    mode: MediaMode = "all"
    month_threshold: int = 6
    added_threshold: int = 12  # months -- never-watched items added within this are "never_new"
    precise_matching: bool = True  # resolve all episodes for path matching (slower, handles multi-library)
    apply_auto_keep: bool = True  # re-tag previously deleted items as "keep" if re-requested


class MovieMatch(_Base):
    title: str | None = None
    jellyfin_path: str
    library_path: str | None = None
    match_method: MatchMethod | None = None
    fuzzy_score: float | None = None
    size_bytes: int = 0
    is_ambiguous: bool = False
    ambiguity_reason: str | None = None
    ambiguous_candidates: list[dict[str, Any]] = []
    added: str = ""  # ISO 8601 from Radarr
    status: MediaStatus | str = ""
    radarr_id: int | None = None


class SeasonInfo(_Base):
    season_number: int
    last_played: str
    episode_count: int
    total_episodes: int = 0
    size_bytes: int = 0
    status: MediaStatus | str = ""
    is_unwatched: bool = False  # True for synthetic seasons with no watch history


class SeriesGroup(_Base):
    title: str
    library_path: str | None = None
    match_method: MatchMethod | None = None
    fuzzy_score: float | None = None
    size_bytes: int = 0
    status: MediaStatus | str = ""
    added: str = ""  # ISO 8601 from Sonarr
    seasons: list[SeasonInfo] = []
    total_season_count: int = 0  # total seasons from Sonarr (not just filtered)
    colliding_names: list[str] = []  # populated for collision entries
    sonarr_series_id: int | None = None


class MediaSection(_Base):
    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []


class AnalysisResult(_Base):
    recently_watched: MediaSection
    not_recently_watched: MediaSection
    keep: MediaSection
    collision: MediaSection
    unmatched: MediaSection
    never_watched: MediaSection
    never_new: MediaSection  # never watched but recently added
    summary: SummaryModel


def _title_from_path(path: str) -> str:
    """Extract a readable title from a file path for unmatched items."""
    normalized = path.replace('\\', '/')
    parts = [p for p in normalized.split('/') if p]
    if len(parts) >= 2:
        return parts[-2]  # parent folder is typically the movie name
    return parts[-1] if parts else path


def match_result_to_model(mr: MatchResult, status: MediaStatus | str = "") -> MovieMatch:
    title = mr.matched_title or _title_from_path(mr.jellyfin_path)
    return MovieMatch(
        title=title,
        jellyfin_path=mr.jellyfin_path,
        library_path=mr.matched_path,
        match_method=MatchMethod(mr.match_method) if mr.match_method else None,
        fuzzy_score=mr.score,
        size_bytes=mr.size_on_disk,
        is_ambiguous=mr.is_ambiguous,
        ambiguity_reason=mr.ambiguity_reason,
        ambiguous_candidates=mr.ambiguous_candidates,
        status=status,
        radarr_id=mr.radarr_movie_id,
    )


def _derive_show_status(season_statuses: set[str]) -> MediaStatus | str:
    """Derive a show-level status from the set of its season statuses."""
    if len(season_statuses) == 1:
        return next(iter(season_statuses))
    return MediaStatus.MIXED


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
    # Count of non-special seasons with files on disk per series path
    sonarr_on_disk_count: dict[str, int] = {}
    for s in result.all_series:
        sonarr_lookup[s.path] = {
            sn.season_number: sn.statistics.total_episode_count
            for sn in s.seasons
        }
        sonarr_on_disk_count[s.path] = len([
            sn for sn in s.seasons
            if sn.season_number > 0 and sn.statistics.size_on_disk > 0
        ])

    # Collect all seasons with their status.
    # Synthetic (unwatched) seasons get overridden: "recent" list → "never_new"
    # (show is active), "old" list → "never" (show is abandoned).
    tagged: list[tuple[SeasonSummary, str]] = []
    for s in result.recent_seasons_matched:
        tagged.append((s, MediaStatus.NEVER_NEW if s.is_unwatched else MediaStatus.RECENT))
    for s in result.old_seasons_matched:
        tagged.append((s, MediaStatus.NEVER if s.is_unwatched else MediaStatus.OLD))
    for s in result.kept_season_matches:
        tagged.append((s, MediaStatus.KEPT))
    for s in result.recent_seasons_unmatched + result.old_seasons_unmatched:
        tagged.append((s, MediaStatus.UNMATCHED))
    for s in result.collision_season_matches:
        tagged.append((s, MediaStatus.COLLISION))

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
        # Use the first non-None sonarr_series_id from any season
        sonarr_id = next(
            (s.sonarr_series_id for s, _ in sorted_seasons if s.sonarr_series_id is not None),
            None,
        )
        # Seasons with files on disk (excluding specials/S00)
        total_sonarr_seasons = sonarr_on_disk_count.get(key, 0)
        groups.append(SeriesGroup(
            title=first_season.series_name,
            library_path=first_season.matched_sonarr_path,
            match_method=MatchMethod(first_season.match_method) if first_season.match_method else None,
            fuzzy_score=first_season.fuzzy_score,
            status=_derive_show_status(season_statuses),
            colliding_names=distinct_names if len(distinct_names) > 1 else [],
            size_bytes=sum(s.size_on_disk for s, _ in sorted_seasons),
            sonarr_series_id=sonarr_id,
            total_season_count=total_sonarr_seasons,
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
            never_season_count = len([sn for sn in series.seasons if sn.season_number > 0 and sn.statistics.size_on_disk > 0])
            groups.append(SeriesGroup(
                title=series.title,
                library_path=series.path,
                status=never_status,
                added=series.added,
                size_bytes=series.statistics.size_on_disk,
                sonarr_series_id=series.id,
                total_season_count=never_season_count,
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


def _movie_to_match(movie: Movie, status: MediaStatus = MediaStatus.NEVER) -> MovieMatch:
    """Convert a Radarr Movie to a MovieMatch model (for never-watched items)."""
    return MovieMatch(
        title=movie.title,
        jellyfin_path="",
        library_path=movie.path,
        size_bytes=movie.size_on_disk,
        added=movie.added,
        status=status,
        radarr_id=movie.id,
    )


def cleanup_result_to_response(
    result: CleanupResult,
    mode: str,
    added_threshold: int = 12,
) -> AnalysisResult:
    """Convert a CleanupResult into the API AnalysisResult model."""
    # Movies -- split by category, never-watched split by added date
    all_matches = (
        result.recent_movie_matches + result.old_movie_matches
        + result.kept_movie_matches + result.collision_movie_matches
        + result.auto_kept_movies
    )
    watched_movie_paths = {m.matched_path for m in all_matches if m.matched_path}
    never_movies: list[MovieMatch] = []
    never_new_movies: list[MovieMatch] = []
    for m in result.all_movies:
        if m.path not in watched_movie_paths:
            status = _never_status(m.added, added_threshold)
            match = _movie_to_match(m, status=status)
            if status == MediaStatus.NEVER_NEW:
                never_new_movies.append(match)
            else:
                never_movies.append(match)

    # Series -- unified: one entry per show, placed in one category by status
    all_series_groups = _build_all_series_groups(result, added_threshold)
    series_by_cat: dict[str, list[SeriesGroup]] = defaultdict(list)
    for g in all_series_groups:
        if g.status == MediaStatus.RECENT:
            series_by_cat["recent"].append(g)
        elif g.status in (MediaStatus.OLD, MediaStatus.MIXED):
            series_by_cat["old"].append(g)
        elif g.status == MediaStatus.KEPT:
            series_by_cat["kept"].append(g)
        elif g.status == MediaStatus.COLLISION:
            series_by_cat["collision"].append(g)
        elif g.status == MediaStatus.UNMATCHED:
            series_by_cat["unmatched"].append(g)
        elif g.status == MediaStatus.NEVER:
            series_by_cat["never"].append(g)
        elif g.status == MediaStatus.NEVER_NEW:
            series_by_cat["never_new"].append(g)

    # Build auto-keep series groups from auto-kept seasons
    auto_keep_series: list[SeriesGroup] = []
    if result.auto_kept_seasons:
        # Group auto-kept seasons by Sonarr path
        ak_grouped: dict[str, list[SeasonSummary]] = defaultdict(list)
        for s in result.auto_kept_seasons:
            key = s.matched_sonarr_path or s.series_name
            ak_grouped[key].append(s)

        sonarr_lookup: dict[str, dict[int, int]] = {}
        for s in result.all_series:
            sonarr_lookup[s.path] = {
                sn.season_number: sn.statistics.total_episode_count
                for sn in s.seasons
            }

        for key, seasons in sorted(ak_grouped.items(), key=lambda x: x[1][0].series_name.lower()):
            sorted_seasons = sorted(seasons, key=lambda s: s.season_number)
            first = sorted_seasons[0]
            sonarr_seasons = sonarr_lookup.get(key, {})
            auto_keep_series.append(SeriesGroup(
                title=first.series_name,
                library_path=first.matched_sonarr_path,
                match_method=MatchMethod(first.match_method) if first.match_method else None,
                fuzzy_score=first.fuzzy_score,
                status=MediaStatus.AUTO_KEEP,
                size_bytes=sum(s.size_on_disk for s in sorted_seasons),
                sonarr_series_id=first.sonarr_series_id,
                seasons=[
                    SeasonInfo(
                        season_number=s.season_number,
                        last_played=s.last_played,
                        episode_count=s.episode_count,
                        total_episodes=sonarr_seasons.get(s.season_number, 0),
                        size_bytes=s.size_on_disk,
                        status=MediaStatus.AUTO_KEEP,
                        is_unwatched=s.is_unwatched,
                    )
                    for s in sorted_seasons
                ],
            ))

    return AnalysisResult(
        recently_watched=MediaSection(
            movies=[
                match_result_to_model(m, status=MediaStatus.RECENT)
                for m in result.recent_movie_matches
                if m.is_matched
            ],
            series=series_by_cat.get("recent", []),
        ),
        not_recently_watched=MediaSection(
            movies=[
                match_result_to_model(m, status=MediaStatus.OLD)
                for m in result.old_movie_matches
                if m.is_matched
            ],
            series=series_by_cat.get("old", []),
        ),
        keep=MediaSection(
            movies=[match_result_to_model(m, status=MediaStatus.KEPT) for m in result.kept_movie_matches] + [match_result_to_model(m, status=MediaStatus.AUTO_KEEP) for m in result.auto_kept_movies],
            series=series_by_cat.get("kept", []) + auto_keep_series,
        ),
        collision=MediaSection(
            movies=[match_result_to_model(m, status=MediaStatus.COLLISION) for m in result.collision_movie_matches],
            series=series_by_cat.get("collision", []),
        ),
        unmatched=MediaSection(
            movies=[
                match_result_to_model(m, status=MediaStatus.UNMATCHED)
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
