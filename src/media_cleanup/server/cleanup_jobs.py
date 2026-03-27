"""
Job queue for background cleanup execution tasks.

Modelled after jobs.py: one daemon worker thread processes jobs sequentially.
"""

from __future__ import annotations

import logging
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable

from media_cleanup.cleanup_executor import CleanupExecutor
from media_cleanup.config import AppConfig
from media_cleanup.database import Database
from media_cleanup.models import CleanupReport, JobStatus, RunPlan
from media_cleanup.types import CleanupEntryStatus

logger = logging.getLogger(__name__)


@dataclass
class CleanupJob:
    job_id: str
    status: JobStatus
    run_plan: RunPlan
    simulate: bool
    report: CleanupReport | None = None
    created_at: str = ""
    completed_at: str | None = None
    error: str | None = None
    _cancel_flag: bool = field(default=False, repr=False)


class CleanupJobManager:
    """Manages a sequential cleanup job queue with optional WebSocket broadcast."""

    MAX_JOBS = 50

    def __init__(self, config: AppConfig, db: Database) -> None:
        self._config = config
        self._db = db
        self._jobs: dict[str, CleanupJob] = {}
        self._lock = threading.Lock()
        self._queue: list[str] = []
        self._worker_running = False
        self._broadcast_fn: Callable[[dict], None] | None = None

    def set_broadcast(self, fn: Callable[[dict], None]) -> None:
        """Register a broadcast function (called from the WebSocket manager)."""
        self._broadcast_fn = fn

    def submit(self, run_plan: RunPlan, simulate: bool) -> CleanupJob:
        """Enqueue a cleanup job and start the worker if needed."""
        total_items = (
            len(run_plan.movies)
            + len(run_plan.full_series)
            + len(run_plan.season_cleanups)
        )
        job = CleanupJob(
            job_id=str(uuid.uuid4()),
            status=JobStatus.queued,
            run_plan=run_plan,
            simulate=simulate,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        with self._lock:
            self._jobs[job.job_id] = job
            self._queue.append(job.job_id)
            self._prune_old_jobs()

        self._broadcast({
            "type": "cleanup_started",
            "jobId": job.job_id,
            "simulate": simulate,
            "totalItems": total_items,
        })

        self._ensure_worker()
        return job

    def cancel(self, job_id: str) -> bool:
        """Request cancellation. Returns True if the job was found and is cancellable."""
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return False
            if job.status in (JobStatus.complete, JobStatus.failed, JobStatus.cancelled):
                return False
            job._cancel_flag = True
            if job.status == JobStatus.queued:
                job.status = JobStatus.cancelled
                job.completed_at = datetime.now(timezone.utc).isoformat()
                if job_id in self._queue:
                    self._queue.remove(job_id)
                self._broadcast({
                    "type": "cleanup_cancelled",
                    "jobId": job_id,
                })
        return True

    def get(self, job_id: str) -> CleanupJob | None:
        return self._jobs.get(job_id)

    def get_current(self) -> CleanupJob | None:
        """Return the active job if running/queued, else the most recent completed one."""
        for job in reversed(list(self._jobs.values())):
            if job.status in (JobStatus.running, JobStatus.queued):
                return job
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
            logger.exception("Cleanup worker loop crashed")
            with self._lock:
                self._worker_running = False

    def _run_job(self, job: CleanupJob) -> None:
        job.status = JobStatus.running
        total_items = (
            len(job.run_plan.movies)
            + len(job.run_plan.full_series)
            + len(job.run_plan.season_cleanups)
        )
        logger.info(
            "Cleanup job %s started (simulate=%s, items=%d)",
            job.job_id, job.simulate, total_items,
        )

        def progress_cb(
            item_index: int,
            total: int,
            title: str,
            status: CleanupEntryStatus,
        ) -> None:
            logger.info(
                "[cleanup:%s] [%d/%d] %s -> %s",
                job.job_id[:8], item_index + 1, total, title, status.value,
            )
            self._broadcast({
                "type": "cleanup_progress",
                "jobId": job.job_id,
                "itemIndex": item_index,
                "totalItems": total,
                "title": title,
                "status": status.value,
            })

        def cancel_ck() -> bool:
            return job._cancel_flag

        try:
            executor = CleanupExecutor(self._config, self._db, simulate=job.simulate)
            report = executor.execute(job.run_plan, progress_cb=progress_cb, cancel_check=cancel_ck)
            report = CleanupReport(
                job_id=job.job_id,
                simulate=report.simulate,
                started_at=report.started_at,
                completed_at=report.completed_at,
                entries=report.entries,
                total_size_bytes=report.total_size_bytes,
                total_size_fmt=report.total_size_fmt,
                deleted_count=report.deleted_count,
                failed_count=report.failed_count,
            )
            job.report = report

            # Treat a partially-cancelled run as cancelled if the flag is set
            if job._cancel_flag:
                job.status = JobStatus.cancelled
                job.completed_at = datetime.now(timezone.utc).isoformat()
                logger.info("Cleanup job %s cancelled", job.job_id)
                self._broadcast({"type": "cleanup_cancelled", "jobId": job.job_id})
            else:
                job.status = JobStatus.complete
                job.completed_at = datetime.now(timezone.utc).isoformat()
                logger.info("Cleanup job %s completed", job.job_id)
                self._broadcast({"type": "cleanup_complete", "jobId": job.job_id})

        except Exception as exc:
            job.status = JobStatus.failed
            job.error = str(exc)
            job.completed_at = datetime.now(timezone.utc).isoformat()
            logger.exception("Cleanup job %s failed", job.job_id)
            self._broadcast({
                "type": "cleanup_failed",
                "jobId": job.job_id,
                "error": str(exc),
            })

    def _prune_old_jobs(self) -> None:
        """Remove oldest finished jobs when exceeding MAX_JOBS. Must hold _lock."""
        finished = {JobStatus.complete, JobStatus.failed, JobStatus.cancelled}
        while len(self._jobs) > self.MAX_JOBS:
            oldest = None
            for jid, j in self._jobs.items():
                if j.status in finished:
                    if oldest is None or j.created_at < oldest.created_at:
                        oldest = j
            if oldest is None:
                break
            del self._jobs[oldest.job_id]

    def _broadcast(self, message: dict) -> None:
        if self._broadcast_fn:
            try:
                self._broadcast_fn(message)
            except Exception:
                logger.exception("Cleanup broadcast failed")
