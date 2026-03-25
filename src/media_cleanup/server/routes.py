"""
REST API routes.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from media_cleanup.models import (
    AnalysisRequest,
    JobResponse,
    JobStatus,
)
from media_cleanup.server.jobs import Job, JobManager

router = APIRouter(prefix="/api")

# Populated by app.py at startup
job_manager: JobManager | None = None


def _manager() -> JobManager:
    assert job_manager is not None, "JobManager not initialized"
    return job_manager


def _job_to_response(job: Job) -> JobResponse:
    return JobResponse(
        job_id=job.job_id,
        status=job.status,
        progress_percent=job.progress_percent,
        progress_step=job.progress_step,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
    )


# ------------------------------------------------------------------
#  Endpoints
# ------------------------------------------------------------------

@router.post("/analysis", status_code=202)
def create_analysis(request: AnalysisRequest) -> JobResponse:
    """Submit a new analysis job. Returns immediately with 202."""
    job = _manager().submit(request)
    return _job_to_response(job)


@router.get("/analysis")
def list_analyses() -> list[JobResponse]:
    """List all jobs (recent first)."""
    jobs = _manager().list_jobs()
    return [_job_to_response(j) for j in reversed(jobs)]


@router.get("/analysis/current")
def get_current_analysis() -> dict:
    """Get the active job or most recent completed result. Returns 204 if none."""
    job = _manager().get_current()
    if job is None:
        raise HTTPException(status_code=204)

    resp = _job_to_response(job).model_dump(by_alias=True)
    if job.status == JobStatus.complete and job.result is not None:
        resp["result"] = job.result.model_dump(by_alias=True)
    return resp


@router.get("/analysis/{job_id}")
def get_analysis(job_id: str) -> dict:
    """
    Get job status. If complete, includes the full analysis result.
    """
    job = _manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")

    resp = _job_to_response(job).model_dump(by_alias=True)
    if job.status == JobStatus.complete and job.result is not None:
        resp["result"] = job.result.model_dump(by_alias=True)
    return resp


@router.delete("/analysis/{job_id}")
def cancel_analysis(job_id: str) -> dict:
    """Cancel a queued or running job."""
    ok = _manager().cancel(job_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Job not found or already finished",
        )
    return {"status": "cancelling", "jobId": job_id}


@router.delete("/analysis")
def clear_all() -> dict:
    """Clear all completed jobs (keeps running/queued)."""
    _manager().clear_completed()
    return {"status": "cleared"}


@router.get("/health")
def health() -> dict:
    return {"status": "ok"}
