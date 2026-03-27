"""
Base models and shared helper functions.
"""
from __future__ import annotations
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

from media_cleanup.matching import MatchResult
from media_cleanup.types import MediaStatus, SeasonSummary


class _Base(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )


class JobStatus(StrEnum):
    queued = "queued"
    running = "running"
    complete = "complete"
    cancelled = "cancelled"
    failed = "failed"


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


def _never_status(added: str, threshold_months: int) -> MediaStatus:
    """Return NEVER_NEW if the item was added within threshold_months, else NEVER."""
    if not added:
        return MediaStatus.NEVER
    try:
        added_dt = datetime.fromisoformat(added.replace("Z", "+00:00"))
        cutoff = datetime.now(timezone.utc) - timedelta(days=threshold_months * 30)
        return MediaStatus.NEVER_NEW if added_dt >= cutoff else MediaStatus.NEVER
    except (ValueError, TypeError):
        return MediaStatus.NEVER
