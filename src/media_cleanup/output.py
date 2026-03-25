"""
YAML report generator.

Produces a structured YAML file containing:
- Recently watched movies (MatchResult list)
- Not recently watched movies (MatchResult list — cleanup candidates)
- Recently watched series, grouped by series title with season detail
- Not recently watched series, grouped by series title with season detail
- Ambiguous fuzzy matches that need user review
"""

import yaml
from datetime import datetime
from typing import Any
from collections import defaultdict

from media_cleanup.matching import MatchResult
from media_cleanup.types import SeasonSummary


def generate_report(
    recently_watched_movies: list[MatchResult],
    not_recently_watched_movies: list[MatchResult],
    recent_seasons: list[SeasonSummary],
    old_seasons: list[SeasonSummary],
    month_threshold: int,
    unmatched_seasons: list[SeasonSummary] | None = None,
    kept_movie_matches: list[MatchResult] | None = None,
    kept_season_matches: list[SeasonSummary] | None = None,
    collision_movie_matches: list[MatchResult] | None = None,
    collision_season_matches: list[SeasonSummary] | None = None,
    output_path: str = "cleanup_report.yaml"
) -> str:
    """
    Write a YAML report to disk summarizing media watch status.

    Only matched items appear in recently_watched / not_recently_watched.
    Unmatched items (no Sonarr/Radarr match) go in their own section.

    Series are grouped by title in the output so each show appears once
    with a list of its seasons rather than one entry per season.

    Returns:
        The output file path.
    """
    if unmatched_seasons is None:
        unmatched_seasons = []
    if kept_movie_matches is None:
        kept_movie_matches = []
    if kept_season_matches is None:
        kept_season_matches = []
    if collision_movie_matches is None:
        collision_movie_matches = []
    if collision_season_matches is None:
        collision_season_matches = []

    # Unmatched movies are those that went through matching but got no match
    all_movies = recently_watched_movies + not_recently_watched_movies
    unmatched_movies = [m for m in all_movies if not m.is_matched]
    # Only matched movies in the watched sections
    matched_recent_movies = [m for m in recently_watched_movies if m.is_matched]
    matched_old_movies = [m for m in not_recently_watched_movies if m.is_matched]

    report: dict[str, Any] = {
        "report_metadata": {
            "generated_at": datetime.now().isoformat(),
            "month_threshold": month_threshold,
        },
        "recently_watched": {
            "movies": _format_movie_list(matched_recent_movies),
            "series": _format_season_list(recent_seasons),
        },
        "not_recently_watched": {
            "movies": _format_movie_list(matched_old_movies),
            "series": _format_season_list(old_seasons),
        },
        "keep": {
            "movies": _format_movie_list(kept_movie_matches),
            "series": _format_season_list(kept_season_matches),
        },
        "collision": {
            "movies": _format_movie_list(collision_movie_matches),
            "series": _format_season_list(collision_season_matches),
        },
        "unmatched": {
            "movies": [{"jellyfin_path": m.jellyfin_path} for m in unmatched_movies],
            "series": _format_season_list(unmatched_seasons),
        },
        "ambiguous_matches": {
            "movies": _collect_ambiguous_movies(all_movies),
            "series": _collect_ambiguous_seasons(recent_seasons + old_seasons + unmatched_seasons),
        },
    }

    with open(output_path, 'w', encoding='utf-8') as f:
        yaml.dump(report, f, default_flow_style=False, allow_unicode=True, sort_keys=False)

    return output_path


def _format_movie_list(matches: list[MatchResult]) -> list[dict[str, Any]]:
    """Convert a list of movie MatchResults into serializable dicts."""
    items: list[dict[str, Any]] = []
    for m in matches:
        entry: dict[str, Any] = {
            "title": m.matched_title or "UNMATCHED",
            "jellyfin_path": m.jellyfin_path,
        }
        if m.matched_path:
            entry["library_path"] = m.matched_path
        if m.match_method:
            entry["match_method"] = m.match_method
        if m.score is not None:
            entry["fuzzy_score"] = round(m.score, 1)
        if m.size_on_disk:
            entry["size_gb"] = round(m.size_on_disk / (1024 ** 3), 2)
        items.append(entry)
    return items


def _format_season_list(seasons: list[SeasonSummary]) -> list[dict[str, Any]]:
    """
    Group SeasonSummary objects by series title and format for YAML output.

    Each series appears once with a sorted list of its seasons, so the
    output is easy to scan for cleanup decisions.
    """
    # Group by matched Sonarr path (or series_name if unmatched)
    grouped: dict[str, list[SeasonSummary]] = defaultdict(list)
    for season in seasons:
        key = season.matched_sonarr_path or f"UNMATCHED:{season.series_name}"
        grouped[key].append(season)

    series_entries: list[dict[str, Any]] = []
    for sonarr_path, season_list in grouped.items():
        # Sort seasons numerically
        season_list.sort(key=lambda s: s.season_number)
        first = season_list[0]

        entry: dict[str, Any] = {
            "title": first.series_name,
        }
        if first.matched_sonarr_path:
            entry["library_path"] = first.matched_sonarr_path
        if first.match_method:
            entry["match_method"] = first.match_method
        if first.fuzzy_score is not None:
            entry["fuzzy_score"] = round(first.fuzzy_score, 1)

        total_size = sum(s.size_on_disk for s in season_list)
        if total_size:
            entry["size_gb"] = round(total_size / (1024 ** 3), 2)

        entry["seasons"] = [
            {
                "season": s.season_number,
                "last_played": s.last_played,
                "watched_episodes": s.episode_count,
                **({"size_gb": round(s.size_on_disk / (1024 ** 3), 2)} if s.size_on_disk else {}),
            }
            for s in season_list
        ]
        series_entries.append(entry)

    # Sort series alphabetically by title
    series_entries.sort(key=lambda e: e["title"].lower())
    return series_entries


def _collect_ambiguous_movies(matches: list[MatchResult]) -> list[dict[str, Any]]:
    """
    Extract ambiguous movie matches for user review.
    Each candidate now includes title, library_path, and score so the user
    can tell apart entries with the same name (e.g. remakes from different years).
    """
    return [
        {
            "jellyfin_path": m.jellyfin_path,
            "best_match": {
                "title": m.matched_title,
                "library_path": m.matched_path,
                "score": round(m.score, 1) if m.score is not None else None,
            },
            # duplicate_title: library has two entries with identical names (e.g. remakes)
            # similar_titles:  two different titles scored within the ambiguity margin
            "reason": m.ambiguity_reason,
            "other_candidates": m.ambiguous_candidates,
        }
        for m in matches if m.is_ambiguous
    ]


def _collect_ambiguous_seasons(seasons: list[SeasonSummary]) -> list[dict[str, Any]]:
    """
    Extract ambiguous series matches for user review.
    Each candidate includes title, library_path, and score.
    """
    return [
        {
            "series_name": s.series_name,
            "season": s.season_number,
            "best_match": {
                "title": s.series_name,
                "library_path": s.matched_sonarr_path,
                "score": round(s.fuzzy_score, 1) if s.fuzzy_score is not None else None,
            },
            "other_candidates": s.ambiguous_candidates,
        }
        for s in seasons if s.is_ambiguous
    ]
