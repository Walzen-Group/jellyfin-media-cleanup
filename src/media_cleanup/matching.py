"""
Media matching module.

Movies:
    Matches Jellyfin file paths against Radarr using path prefix matching,
    with rapidfuzz fallback for moved/renamed files.

Series:
    Groups resolved episodes by (series_name, season_number) to produce
    SeasonSummary objects. Seasons are classified as recently/not-recently
    watched based on the most recent episode play date. Series are then
    matched to Sonarr using path prefix matching, with fuzzy fallback.

When fuzzy matching produces multiple close candidates, they are flagged
as ambiguous so the user can review them.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from rapidfuzz import fuzz, process
from typing import Any, Callable, Optional
from media_cleanup.schema.radarr_schema import Movie
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.types import EpisodeInfo, SeasonSummary



ProgressCallback = Callable[[str, int, int], None]



# Minimum similarity score (0–100) for a fuzzy match to be considered valid
FUZZY_THRESHOLD = 88

# If two candidates score within this margin of each other, flag as ambiguous
AMBIGUITY_MARGIN = 5

# Minimum length ratio between two titles for a word-boundary or fuzzy match
# to be accepted.  Prevents "House" (5 chars) matching "House of Guinness" (17).
# len(shorter) / len(longer) must be >= this value.
LENGTH_RATIO_THRESHOLD = 0.65


# ------------------------------------------------------------------ #
#  Movie match result
# ------------------------------------------------------------------ #

@dataclass
class MatchResult:
    """Result of matching a Jellyfin file path to a Radarr movie."""
    jellyfin_path: str
    matched_title: Optional[str] = None
    matched_path: Optional[str] = None
    match_method: Optional[str] = None  # "path" or "fuzzy"
    score: Optional[float] = None       # fuzzy score; None for path matches
    # Each candidate is a dict with "title", "library_path", and "score"
    # so the user can tell apart duplicates (e.g. two "Little Women" with different years)
    ambiguous_candidates: list[dict[str, Any]] = field(default_factory=list)
    # Why was this flagged ambiguous?
    # "duplicate_title"  — library has multiple entries with the same title (e.g. remakes)
    # "similar_titles"   — two different titles scored within AMBIGUITY_MARGIN of each other
    ambiguity_reason: Optional[str] = None

    size_on_disk: int = 0  # bytes, from Radarr

    @property
    def is_matched(self) -> bool:
        return self.matched_title is not None

    @property
    def is_ambiguous(self) -> bool:
        return len(self.ambiguous_candidates) > 0


# ------------------------------------------------------------------ #
#  Movie matching (file-path level)
# ------------------------------------------------------------------ #

def match_movies_by_path(
    jellyfin_paths: list[str],
    radarr_movies: list[Movie],
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[MatchResult], list[str]]:
    """
    Match Jellyfin file paths to Radarr movies by checking if the movie's
    root path is a prefix of the Jellyfin path.

    Returns:
        - matched: list of successful MatchResults
        - unmatched_paths: Jellyfin paths that had no path-based match
    """
    matched: list[MatchResult] = []
    unmatched_paths: list[str] = []
    cb = progress_callback or (lambda *_: None)
    total = len(jellyfin_paths)

    for i, jf_path in enumerate(jellyfin_paths):
        found = False
        for movie in radarr_movies:
            if movie.path in jf_path:
                matched.append(MatchResult(
                    jellyfin_path=jf_path,
                    matched_title=movie.title,
                    matched_path=movie.path,
                    match_method="path",
                    size_on_disk=movie.size_on_disk,
                ))
                found = True
                break
        if not found:
            unmatched_paths.append(jf_path)
        cb("Matching movies by path", i + 1, total)

    return matched, unmatched_paths


def fuzzy_match_movies(
    unmatched_paths: list[str],
    radarr_movies: list[Movie],
    progress_callback: ProgressCallback | None = None,
) -> list[MatchResult]:
    """
    Fuzzy fallback for movies that couldn't be matched by path.
    Extracts a guessed title from the file path and scores against Radarr titles.
    """
    if not unmatched_paths or not radarr_movies:
        return []

    # Keep duplicates (e.g. two "Little Women" from different years) so they
    # surface as ambiguous — the report includes library_path to tell them apart
    titles = [m.title for m in radarr_movies]

    return _fuzzy_match_paths(unmatched_paths, titles, radarr_movies, "Fuzzy matching movies", progress_callback)


# ------------------------------------------------------------------ #
#  Series matching (season level)
# ------------------------------------------------------------------ #

def build_season_summaries(
    episodes: list[EpisodeInfo],
    month_threshold: int,
) -> tuple[list[SeasonSummary], list[SeasonSummary]]:
    """
    Group EpisodeInfo records by (series_name, season_number) and classify
    each season as recently or not-recently watched.

    A season is "recently watched" if its most recent episode play is within
    the last `month_threshold` months. Classification uses the most recent
    play date across all watched episodes of that season.

    Returns:
        - recent_seasons: seasons with at least one episode watched within threshold
        - old_seasons: seasons whose most recent episode watch is older than threshold
    """
    # Group episodes: (series_name, season_number) -> list of EpisodeInfo
    groups: dict[tuple[str, int], list[EpisodeInfo]] = {}
    for ep in episodes:
        key = (ep.series_name, ep.season_number)
        groups.setdefault(key, []).append(ep)

    cutoff = datetime.now() - timedelta(days=month_threshold * 30)

    recent_seasons: list[SeasonSummary] = []
    old_seasons: list[SeasonSummary] = []

    for (series_name, season_number), eps in groups.items():
        # Most recent play date across all episodes in this season
        last_played = max(ep.last_played for ep in eps)

        summary = SeasonSummary(
            series_name=series_name,
            season_number=season_number,
            last_played=last_played,
            episode_count=len(eps),
        )

        # Parse the date string (Jellyfin returns "YYYY-MM-DD HH:MM:SS")
        try:
            last_played_dt = datetime.fromisoformat(last_played)
        except ValueError:
            # If parsing fails, conservatively treat as old
            old_seasons.append(summary)
            continue

        if last_played_dt >= cutoff:
            recent_seasons.append(summary)
        else:
            old_seasons.append(summary)

    # Sort for readability: recent by most-recently-watched first, old by oldest first
    recent_seasons.sort(key=lambda s: s.last_played, reverse=True)
    old_seasons.sort(key=lambda s: s.last_played)

    return recent_seasons, old_seasons


def match_seasons_to_sonarr(
    seasons: list[SeasonSummary],
    sonarr_series: list[Series],
    progress_callback: ProgressCallback | None = None,
) -> tuple[list[SeasonSummary], list[SeasonSummary]]:
    """
    Enrich SeasonSummary objects with Sonarr path data by matching
    series_name against Sonarr series paths (path prefix) or titles (fuzzy).

    Returns:
        - matched: seasons that were successfully matched to a Sonarr series
        - unmatched: seasons with no Sonarr match (path or fuzzy both failed)
    """
    if not seasons or not sonarr_series:
        return [], seasons

    # Keep full list + titles (with possible duplicates) for fuzzy matching
    sonarr_titles = [s.title for s in sonarr_series]

    matched: list[SeasonSummary] = []
    unmatched: list[SeasonSummary] = []
    cb = progress_callback or (lambda *_: None)
    total = len(seasons)

    for i, season in enumerate(seasons):
        # --- Primary: check if any Sonarr series path appears in the season's
        #     series_name (a loose check since we only have the name from Jellyfin)
        path_match = _path_match_season(season, sonarr_series)
        if path_match:
            season.matched_sonarr_path = path_match.path
            season.match_method = "path"
            season.size_on_disk = _get_season_size(path_match, season.season_number)
            matched.append(season)
            cb("Matching seasons", i + 1, total)
            continue

        # --- Fallback: fuzzy match series name against Sonarr titles
        top_matches = process.extract(
            season.series_name,
            sonarr_titles,
            scorer=fuzz.token_sort_ratio,
            limit=3
        )

        if (
            top_matches
            and top_matches[0][1] >= FUZZY_THRESHOLD
            and _length_ratio(season.series_name, top_matches[0][0]) >= LENGTH_RATIO_THRESHOLD
        ):
            best_title, best_score, best_idx = top_matches[0]
            ambiguous = [
                {
                    "title": title,
                    "library_path": sonarr_series[idx].path,
                    "score": round(score, 1),
                }
                for title, score, idx in top_matches[1:]
                if score >= FUZZY_THRESHOLD and (best_score - score) <= AMBIGUITY_MARGIN
                and _length_ratio(season.series_name, title) >= LENGTH_RATIO_THRESHOLD
            ]
            season.matched_sonarr_path = sonarr_series[best_idx].path
            season.match_method = "fuzzy"
            season.fuzzy_score = best_score
            season.ambiguous_candidates = ambiguous
            season.size_on_disk = _get_season_size(sonarr_series[best_idx], season.season_number)
            matched.append(season)
        else:
            unmatched.append(season)

        cb("Matching seasons", i + 1, total)

    return matched, unmatched


def _get_season_size(series: Series, season_number: int) -> int:
    """Look up size_on_disk for a specific season from the Sonarr series object."""
    for s in series.seasons:
        if s.season_number == season_number:
            return s.statistics.size_on_disk
    # Fallback: if season not found (e.g. season_number=-1), use whole series size
    return series.statistics.size_on_disk if season_number == -1 else 0


_YEAR_SUFFIX_RE = re.compile(r'\s*\((\d{4})\)\s*$')


def _strip_year(title: str) -> str:
    """Strip a trailing year suffix like '(2024)' from a title."""
    return _YEAR_SUFFIX_RE.sub('', title)


def _extract_year(title: str) -> int | None:
    """Extract a trailing year like '(2024)' from a title, or None."""
    m = _YEAR_SUFFIX_RE.search(title)
    return int(m.group(1)) if m else None


def _length_ratio(a: str, b: str) -> float:
    """Return len(shorter) / len(longer), or 1.0 if both are empty.

    Strips trailing year suffixes like '(2024)' before comparing so that
    'Dark Matter' vs 'Dark Matter (2024)' isn't penalized.
    """
    a, b = _strip_year(a), _strip_year(b)
    la, lb = len(a), len(b)
    if la == 0 and lb == 0:
        return 1.0
    return min(la, lb) / max(la, lb)


def _path_match_season(season: SeasonSummary, sonarr_series: list[Series]) -> Optional[Series]:
    """
    Try to match a season's series_name to a Sonarr series.

    Match priority:
    1. Exact title match (case-insensitive)
    2. Exact match after stripping year suffixes (e.g. 'Dark Matter' matches
       'Dark Matter (2024)').  When multiple series match after stripping,
       pick the one whose year is closest to (but not after) the watch date.
    3. Word-boundary substring match, gated by a minimum length ratio to
       prevent 'House' from matching 'House of Guinness'.
    """
    name_lower = season.series_name.lower()
    name_stripped = _strip_year(name_lower)

    # Pass 1: exact title match (no year stripping)
    for series in sonarr_series:
        if series.title.lower() == name_lower:
            return series

    # Pass 2: year-stripped exact match -- collect all candidates
    year_candidates: list[Series] = []
    for series in sonarr_series:
        if _strip_year(series.title.lower()) == name_stripped:
            year_candidates.append(series)

    if len(year_candidates) == 1:
        return year_candidates[0]
    if len(year_candidates) > 1:
        return _pick_by_watch_date(year_candidates, season.last_played)

    # Pass 3: word-boundary match with length guard
    for series in sonarr_series:
        title_lower = series.title.lower()
        if _length_ratio(title_lower, name_lower) >= LENGTH_RATIO_THRESHOLD:
            if re.search(r'\b' + re.escape(title_lower) + r'\b', name_lower):
                return series
            if re.search(r'\b' + re.escape(name_lower) + r'\b', title_lower):
                return series
    return None


def _pick_by_watch_date(candidates: list[Series], last_played: str) -> Series:
    """
    Given multiple Sonarr series with the same base title (e.g. 'Dark Matter
    (2024)' and 'Dark Matter (2026)'), pick the one whose year best fits
    the watch date.  Prefer the most recent year that is <= the watch year.
    Falls back to the earliest year if all are after the watch year.
    """
    try:
        watch_year = int(last_played[:4])
    except (ValueError, IndexError):
        return candidates[0]

    best: Series | None = None
    best_year: int = 0
    for series in candidates:
        year = _extract_year(series.title) or 0
        if year <= watch_year and year > best_year:
            best = series
            best_year = year

    if best is not None:
        return best

    # All candidates are newer than the watch date -- pick the earliest
    return min(candidates, key=lambda s: _extract_year(s.title) or 9999)


# ------------------------------------------------------------------ #
#  Shared fuzzy matching for movie paths
# ------------------------------------------------------------------ #

def _fuzzy_match_paths(
    unmatched_paths: list[str],
    candidate_titles: list[str],
    candidate_items: list[Movie],
    description: str = "Fuzzy matching",
    progress_callback: ProgressCallback | None = None,
) -> list[MatchResult]:
    """
    Core fuzzy matching logic for movie file paths.

    Uses the index returned by rapidfuzz to look up the specific item from
    candidate_items, so duplicate titles (e.g. remakes) resolve to the correct
    entry and the ambiguous report can show each candidate's library path.

    For each unmatched path:
    1. Extract a best-guess title from the path (last meaningful directory name).
    2. Score it against all candidate titles using token_sort_ratio.
    3. Accept if above FUZZY_THRESHOLD; flag ambiguous if multiple close scores.
    """
    results: list[MatchResult] = []
    cb = progress_callback or (lambda *_: None)
    total = len(unmatched_paths)

    for i, path in enumerate(unmatched_paths):
        guessed_title = _extract_title_from_path(path)
        if not guessed_title:
            results.append(MatchResult(jellyfin_path=path))
            cb(description, i + 1, total)
            continue

        top_matches = process.extract(
            guessed_title,
            candidate_titles,
            scorer=fuzz.token_sort_ratio,
            limit=5
        )

        if (
            not top_matches
            or top_matches[0][1] < FUZZY_THRESHOLD
            or _length_ratio(guessed_title, top_matches[0][0]) < LENGTH_RATIO_THRESHOLD
        ):
            results.append(MatchResult(jellyfin_path=path))
            cb(description, i + 1, total)
            continue

        best_title, best_score, best_idx = top_matches[0]
        best_item = candidate_items[best_idx]

        # Build rich candidate info for any close-scoring alternatives
        ambiguous: list[dict[str, Any]] = [
            {
                "title": title,
                "library_path": candidate_items[idx].path,
                "score": round(score, 1),
            }
            for title, score, idx in top_matches[1:]
            if score >= FUZZY_THRESHOLD and (best_score - score) <= AMBIGUITY_MARGIN
            and _length_ratio(guessed_title, title) >= LENGTH_RATIO_THRESHOLD
        ]

        # Determine why this match is ambiguous, if at all
        ambiguity_reason: Optional[str] = None
        if ambiguous:
            if any(c['title'] == best_title for c in ambiguous):
                ambiguity_reason = "duplicate_title"
            else:
                ambiguity_reason = "similar_titles"

        results.append(MatchResult(
            jellyfin_path=path,
            matched_title=best_title,
            matched_path=best_item.path,
            match_method="fuzzy",
            score=best_score,
            ambiguous_candidates=ambiguous,
            ambiguity_reason=ambiguity_reason,
            size_on_disk=best_item.size_on_disk,
        ))

        cb(description, i + 1, total)

    return results


def _extract_title_from_path(path: str) -> str:
    """
    Best-effort title extraction from a file path.

    Grabs the innermost meaningful directory name, which is typically the
    movie folder (e.g. '/media/movies/The Matrix (1999)/file.mkv' -> 'The Matrix (1999)').
    Years are kept so that remakes with the same name can be distinguished
    during fuzzy matching.
    """
    normalized = path.replace('\\', '/')
    parts = [p for p in normalized.split('/') if p]

    if len(parts) < 2:
        return parts[0] if parts else ''

    candidate = parts[-2]

    # If it looks like "Season 01", go one level up
    if re.match(r'^[Ss]eason\s+\d+$', candidate) and len(parts) >= 3:
        candidate = parts[-3]

    return candidate.strip()
