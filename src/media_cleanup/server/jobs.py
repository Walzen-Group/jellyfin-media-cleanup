"""
Job queue for background analysis tasks.

Jobs are processed sequentially in a single daemon thread.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from media_cleanup.config import AppConfig, load_config
from media_cleanup.service import CancellationError, CleanupService
from media_cleanup.models import (
    AnalysisRequest,
    AnalysisResult,
    JobStatus,
    cleanup_result_to_response,
)

logger = logging.getLogger(__name__)


@dataclass
class Job:
    job_id: str
    status: JobStatus
    request: AnalysisRequest
    result: AnalysisResult | None = None
    progress_percent: float = 0
    progress_step: str = ""
    created_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    _cancel_flag: bool = field(default=False, repr=False)


class JobManager:
    """Manages a sequential job queue with optional WebSocket broadcast."""

    def __init__(self, config: AppConfig | None = None) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self._queue: list[str] = []  # job_ids in submission order
        self._worker_running = False
        self._broadcast_fn: Callable[[dict], None] | None = None
        self._config = config or load_config()

    def set_broadcast(self, fn: Callable[[dict], None]) -> None:
        """Register a broadcast function (called from the WebSocket manager)."""
        self._broadcast_fn = fn

    def submit(self, request: AnalysisRequest) -> Job:
        """Add a job to the queue. Starts the worker thread if needed."""
        job = Job(
            job_id=str(uuid.uuid4()),
            status=JobStatus.queued,
            request=request,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._queue.append(job.job_id)

        self._broadcast({
            "type": "job_created",
            "job": {
                "jobId": job.job_id,
                "status": job.status.value,
                "progressPercent": 0,
                "progressStep": "Queued",
                "stepIndex": 0,
                "totalSteps": 0,
                "createdAt": job.created_at,
                "completedAt": None,
                "error": None,
            },
        })

        self._ensure_worker()
        return job

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns True if the job was found."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in (JobStatus.complete, JobStatus.failed, JobStatus.cancelled):
                return False
            job._cancel_flag = True
            # If still queued, mark cancelled immediately
            if job.status == JobStatus.queued:
                job.status = JobStatus.cancelled
                job.completed_at = datetime.now(timezone.utc).isoformat()
                if job_id in self._queue:
                    self._queue.remove(job_id)
                self._broadcast({
                    "type": "job_cancelled",
                    "jobId": job_id,
                })
        return True

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    def list_jobs(self) -> list[Job]:
        return list(self._jobs.values())

    def clear_completed(self) -> None:
        """Remove all completed/cancelled/failed jobs."""
        with self._lock:
            self._jobs = {
                jid: j for jid, j in self._jobs.items()
                if j.status in (JobStatus.running, JobStatus.queued)
            }

    def get_current(self) -> Job | None:
        """Return the active (running/queued) job, or the most recent completed one."""
        # Prefer running/queued
        for job in reversed(list(self._jobs.values())):
            if job.status in (JobStatus.running, JobStatus.queued):
                return job
        # Fall back to most recent completed
        for job in reversed(list(self._jobs.values())):
            if job.status == JobStatus.complete:
                return job
        return None

    # ------------------------------------------------------------------
    #  Worker
    # ------------------------------------------------------------------

    def _ensure_worker(self) -> None:
        with self._lock:
            if self._worker_running:
                return
            self._worker_running = True

        t = threading.Thread(target=self._worker_loop, daemon=True)
        t.start()

    def _worker_loop(self) -> None:
        """Process jobs from the queue one at a time."""
        try:
            while True:
                with self._lock:
                    if not self._queue:
                        self._worker_running = False
                        return
                    job_id = self._queue.pop(0)
                    job = self._jobs.get(job_id)

                if job is None or job.status == JobStatus.cancelled:
                    continue

                self._run_job(job)
        except Exception:
            logger.exception("Worker loop crashed")
            with self._lock:
                self._worker_running = False

    def _run_job(self, job: Job) -> None:
        job.status = JobStatus.running
        logger.info("Job %s started (mode=%s, threshold=%d)",
                     job.job_id, job.request.mode, job.request.month_threshold)

        import time
        _last_broadcast = 0.0
        _last_log = 0.0
        _last_log_step = ""
        _current_step_idx = 0
        _THROTTLE_INTERVAL = 0.25  # seconds
        _LOG_INTERVAL = 2.0  # seconds — less noisy than WS

        # Build step list matching service.py's step names
        _step_names: list[str] = []
        mode = job.request.mode
        if mode in ("all", "movies"):
            _step_names += ["Querying Jellyfin movie history", "Resolving movie paths", "Fetching Radarr library", "Matching movies"]
        if mode in ("all", "series"):
            _step_names += ["Querying Jellyfin episode history", "Resolving episodes", "Fetching Sonarr library", "Matching seasons"]
        _total_steps = len(_step_names)

        def progress_cb(step: str, current: int, total: int) -> None:
            nonlocal _last_broadcast, _last_log, _last_log_step, _current_step_idx
            pct = (current / total * 100) if total > 0 else 0
            job.progress_percent = pct
            job.progress_step = step
            now = time.monotonic()

            # Track which step we're on
            step_base = step.split(":")[0].rstrip()
            if step_base != _last_log_step:
                for i, name in enumerate(_step_names):
                    if name == step_base:
                        _current_step_idx = i + 1
                        break

            # Log to console (throttled, or on new step base)
            if step_base != _last_log_step or (now - _last_log) >= _LOG_INTERVAL:
                _last_log = now
                _last_log_step = step_base
                logger.info("[%s] [%d/%d] %3.0f%% %s", job.job_id[:8], _current_step_idx, _total_steps, pct, step)

            # Broadcast to WebSocket clients (throttled)
            if current == total or (now - _last_broadcast) >= _THROTTLE_INTERVAL:
                _last_broadcast = now
                self._broadcast({
                    "type": "job_progress",
                    "jobId": job.job_id,
                    "step": step,
                    "percent": pct,
                    "stepIndex": _current_step_idx,
                    "totalSteps": _total_steps,
                })

        def cancel_ck() -> bool:
            return job._cancel_flag

        try:
            service = CleanupService(self._config)
            cleanup_result = service.run_analysis(
                mode=job.request.mode,
                month_threshold=job.request.month_threshold,
                progress_callback=progress_cb,
                cancel_check=cancel_ck,
            )
            job.result = cleanup_result_to_response(
                cleanup_result, job.request.mode, job.request.added_threshold)
            job.status = JobStatus.complete
            job.completed_at = datetime.now(timezone.utc).isoformat()
            job.progress_percent = 1.0
            job.progress_step = "Complete"
            logger.info("Job %s completed", job.job_id)
            self._broadcast({
                "type": "job_complete",
                "jobId": job.job_id,
            })

        except CancellationError:
            job.status = JobStatus.cancelled
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.info("Job %s cancelled", job.job_id)
            self._broadcast({
                "type": "job_cancelled",
                "jobId": job.job_id,
            })

        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.exception("Job %s failed", job.job_id)
            self._broadcast({
                "type": "job_failed",
                "jobId": job.job_id,
                "error": str(exc),
            })

    def _broadcast(self, message: dict) -> None:
        if self._broadcast_fn:
            try:
                self._broadcast_fn(message)
            except Exception:
                logger.exception("Broadcast failed")
