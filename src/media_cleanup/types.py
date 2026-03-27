"""
Shared data types used across the matching and output pipeline.
"""

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal, Optional


# ------------------------------------------------------------------
#  Typed enums and literals for strict typing
# ------------------------------------------------------------------

class MediaStatus(StrEnum):
    """Watch/match status for movies and series."""
    RECENT = "recent"
    OLD = "old"
    KEPT = "kept"
    UNMATCHED = "unmatched"
    NEVER = "never"
    NEVER_NEW = "never_new"
    COLLISION = "collision"
    MIXED = "mixed"


class MatchMethod(StrEnum):
    """How a media item was matched to its library entry."""
    PATH = "path"
    FUZZY = "fuzzy"
    SYNTHETIC = "synthetic"


MediaMode = Literal["all", "movies", "series"]
FilterCategory = Literal["old", "never", "never_new"]


@dataclass
class EpisodeInfo:
    """A single watched episode parsed from Jellyfin PlaybackActivity."""
    item_id: str
    series_name: str
    season_number: int
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
    match_method: Optional[str] = None   # "path", "fuzzy", or "synthetic"
    fuzzy_score: Optional[float] = None
    # Each candidate is a dict with "title", "library_path", and "score"
    ambiguous_candidates: list[dict[str, Any]] = field(default_factory=list)
    # True for synthetic seasons generated from Sonarr data (no Jellyfin watch history)
    is_unwatched: bool = False
    # Sonarr series ID for deletion API
    sonarr_series_id: Optional[int] = None

    @property
    def is_matched(self) -> bool:
        return self.matched_sonarr_path is not None

    @property
    def is_ambiguous(self) -> bool:
        return len(self.ambiguous_candidates) > 0
