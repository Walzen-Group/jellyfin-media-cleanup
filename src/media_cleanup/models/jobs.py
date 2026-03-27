"""
Job models.
"""
from __future__ import annotations
from .base import _Base, JobStatus


class JobResponse(_Base):
    job_id: str
    status: JobStatus
    progress_percent: float = 0
    progress_step: str = ""
    created_at: str
    completed_at: str | None = None
    error: str | None = None


class ProgressMessage(_Base):
    """WebSocket progress message."""
    type: str
    job_id: str
    step: str | None = None
    percent: float | None = None
    error: str | None = None
