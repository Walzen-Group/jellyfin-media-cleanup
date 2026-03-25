"""
Pydantic response models for the REST API.

Uses the same camelCase alias pattern as the existing schema files.
"""

from __future__ import annotations

from collections import defaultdict
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from media_cleanup.matching import MatchResult
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.service import CleanupResult, build_summary
from media_cleanup.types import SeasonSummary


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


# ------------------------------------------------------------------
#  Request / enum
# ------------------------------------------------------------------

class AnalysisRequest(_Base):
    mode: str = "all"
    month_threshold: int = 6


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


class SeasonInfo(_Base):
    season_number: int
    last_played: str
    episode_count: int
    size_bytes: int = 0


class SeriesGroup(_Base):
    title: str
    library_path: str | None = None
    match_method: str | None = None
    fuzzy_score: float | None = None
    size_bytes: int = 0
    seasons: list[SeasonInfo] = []


class MediaSection(_Base):
    movies: list[MovieMatch] = []
    series: list[SeriesGroup] = []


class AnalysisResult(_Base):
    recently_watched: MediaSection
    not_recently_watched: MediaSection
    keep: MediaSection
    unmatched: MediaSection
    never_watched: MediaSection
    summary: dict


class ProgressMessage(_Base):
    """WebSocket progress message."""
    type: str
    job_id: str
    step: str | None = None
    percent: float | None = None
    error: str | None = None


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


def match_result_to_model(mr: MatchResult) -> MovieMatch:
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
    )


def seasons_to_series_groups(seasons: list[SeasonSummary]) -> list[SeriesGroup]:
    """Group SeasonSummary objects by series into SeriesGroup models."""
    grouped: dict[str, list[SeasonSummary]] = defaultdict(list)
    for s in seasons:
        key = s.matched_sonarr_path or s.series_name
        grouped[key].append(s)

    groups: list[SeriesGroup] = []
    for _key, season_list in grouped.items():
        # Dedup seasons by number — keep the one with the most recent last_played
        by_num: dict[int, SeasonSummary] = {}
        for s in season_list:
            existing = by_num.get(s.season_number)
            if existing is None or s.last_played > existing.last_played:
                by_num[s.season_number] = s
        deduped = sorted(by_num.values(), key=lambda s: s.season_number)
        first = deduped[0]
        groups.append(SeriesGroup(
            title=first.series_name,
            library_path=first.matched_sonarr_path,
            match_method=first.match_method,
            fuzzy_score=first.fuzzy_score,
            size_bytes=sum(s.size_on_disk for s in deduped),
            seasons=[
                SeasonInfo(
                    season_number=s.season_number,
                    last_played=s.last_played,
                    episode_count=s.episode_count,
                    size_bytes=s.size_on_disk,
                )
                for s in deduped
            ],
        ))
    groups.sort(key=lambda g: g.title.lower())
    return groups


def _dedup_movies(matches: list[MatchResult]) -> list[MovieMatch]:
    """Convert MatchResults to MovieMatch models, deduplicating by matched_path."""
    seen: set[str] = set()
    result: list[MovieMatch] = []
    for m in matches:
        key = m.matched_path or m.jellyfin_path
        if key in seen:
            continue
        seen.add(key)
        result.append(match_result_to_model(m))
    return result


def _movie_to_match(movie: Movie) -> MovieMatch:
    """Convert a Radarr Movie to a MovieMatch model (for never-watched items)."""
    return MovieMatch(
        title=movie.title,
        jellyfin_path="",
        library_path=movie.path,
        size_bytes=movie.size_on_disk,
    )


def _series_to_group(series: Series) -> SeriesGroup:
    """Convert a Sonarr Series to a SeriesGroup model (for never-watched items)."""
    return SeriesGroup(
        title=series.title,
        library_path=series.path,
        size_bytes=series.statistics.size_on_disk,
        seasons=[
            SeasonInfo(
                season_number=s.season_number,
                last_played="",
                episode_count=s.statistics.episode_file_count,
                size_bytes=s.statistics.size_on_disk,
            )
            for s in series.seasons
            if s.season_number > 0  # skip specials (season 0)
        ],
    )


def cleanup_result_to_response(result: CleanupResult, mode: str) -> AnalysisResult:
    """Convert a CleanupResult into the API AnalysisResult model."""
    # Compute never-watched: library items not in any watch history
    all_matches = result.recent_movie_matches + result.old_movie_matches + result.kept_movie_matches
    watched_movie_paths = {m.matched_path for m in all_matches if m.matched_path}
    never_movies = [m for m in result.all_movies if m.path not in watched_movie_paths]

    all_season_matches = (
        result.recent_seasons_matched + result.old_seasons_matched + result.kept_season_matches
    )
    watched_series_paths = {s.matched_sonarr_path for s in all_season_matches if s.matched_sonarr_path}
    never_series = [s for s in result.all_series if s.path not in watched_series_paths]

    return AnalysisResult(
        recently_watched=MediaSection(
            movies=_dedup_movies(result.recent_movie_matches),
            series=seasons_to_series_groups(result.recent_seasons_matched),
        ),
        not_recently_watched=MediaSection(
            movies=_dedup_movies(result.old_movie_matches),
            series=seasons_to_series_groups(result.old_seasons_matched),
        ),
        keep=MediaSection(
            movies=_dedup_movies(result.kept_movie_matches),
            series=seasons_to_series_groups(result.kept_season_matches),
        ),
        unmatched=MediaSection(
            movies=[
                match_result_to_model(m)
                for m in result.recent_movie_matches + result.old_movie_matches
                if not m.is_matched
            ],
            series=seasons_to_series_groups(
                result.recent_seasons_unmatched + result.old_seasons_unmatched
            ),
        ),
        never_watched=MediaSection(
            movies=[_movie_to_match(m) for m in never_movies],
            series=[_series_to_group(s) for s in never_series],
        ),
        summary=build_summary(result, mode),
    )
