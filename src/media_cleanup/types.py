"""
Shared data types used across the matching and output pipeline.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class EpisodeInfo:
    """A single watched episode resolved from Jellyfin, with series/season context."""
    item_id: str
    series_name: str
    season_number: int
    file_path: str
    last_played: str  # ISO date string from PlaybackActivity (e.g. "2024-03-01 21:00:00")


@dataclass
class SeasonSummary:
    """
    A watched TV season, grouped from individual EpisodeInfo records.

    The season is the unit of cleanup analysis: a season is eligible for
    cleanup if its most recent episode watch is older than the threshold.
    May be enriched with Sonarr match data after path/fuzzy matching.
    """
    series_name: str
    season_number: int
    last_played: str        # most recent episode watch date across the whole season
    episode_count: int      # number of distinct watched episodes in this season

    # Filled in after matching against Sonarr
    size_on_disk: int = 0  # bytes, from Sonarr season statistics
    matched_sonarr_path: Optional[str] = None
    match_method: Optional[str] = None   # "path" or "fuzzy"
    fuzzy_score: Optional[float] = None
    # Each candidate is a dict with "title", "library_path", and "score"
    ambiguous_candidates: list[dict[str, Any]] = field(default_factory=list)
    # True for synthetic seasons generated from Sonarr data (no Jellyfin watch history)
    is_unwatched: bool = False

    @property
    def is_matched(self) -> bool:
        return self.matched_sonarr_path is not None

    @property
    def is_ambiguous(self) -> bool:
        return len(self.ambiguous_candidates) > 0
