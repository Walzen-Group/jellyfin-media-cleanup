"""
REST API routes.
"""

from __future__ import annotations

import json

import yaml
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from media_cleanup.database import Database
from media_cleanup.models import (
    AnalysisRequest,
    CleanupExecuteRequest,
    CleanupJobResponse,
    CleanupReport,
    FilterRequest,
    HistoryEntry,
    JobResponse,
    JobStatus,
    RunPlan,
    RunPlanSummary,
    _format_size,
    build_run_plan,
    filter_analysis_result,
)
from media_cleanup.server.cleanup_jobs import CleanupJob, CleanupJobManager
from media_cleanup.server.jobs import Job, JobManager

router = APIRouter(prefix="/api")

# Populated by app.py at startup
job_manager: JobManager | None = None
cleanup_manager: CleanupJobManager | None = None
db: Database | None = None


def _manager() -> JobManager:
    assert job_manager is not None, "JobManager not initialized"
    return job_manager


def _cleanup_manager() -> CleanupJobManager:
    assert cleanup_manager is not None, "CleanupJobManager not initialized"
    return cleanup_manager


def _db() -> Database:
    assert db is not None, "Database not initialized"
    return db


def _cleanup_job_to_response(job: CleanupJob) -> CleanupJobResponse:
    return CleanupJobResponse(
        job_id=job.job_id,
        status=job.status,
        simulate=job.simulate,
        created_at=job.created_at,
        completed_at=job.completed_at,
        error=job.error,
        report=job.report,
    )


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


@router.post("/analysis/{job_id}/filter")
def filter_analysis(job_id: str, request: FilterRequest) -> dict:
    """Filter a completed analysis result by user-selected categories."""
    job = _manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.result is None:
        raise HTTPException(status_code=400, detail="Job has no result")

    filtered = filter_analysis_result(job.result, request.categories, request.greedy, request.media_type, request.min_size_bytes, request.max_size_bytes)
    return filtered.model_dump(by_alias=True)


@router.post("/analysis/{job_id}/prepare", response_model=RunPlan)
def prepare_run_plan(job_id: str, request: FilterRequest) -> RunPlan:
    """Build a dry-run deletion plan from filtered analysis results and store it on the job."""
    job = _manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    if job.result is None:
        raise HTTPException(status_code=400, detail="Job has no result")

    filtered = filter_analysis_result(job.result, request.categories, request.greedy, request.media_type, request.min_size_bytes, request.max_size_bytes)
    plan = build_run_plan(filtered, categories=request.categories)
    job.run_plan = plan
    return plan


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


# ------------------------------------------------------------------
#  Cleanup execution endpoints
# ------------------------------------------------------------------

@router.post("/cleanup/execute", status_code=202)
def execute_cleanup(request: CleanupExecuteRequest) -> CleanupJobResponse:
    """
    Start a cleanup job from user-selected items.

    The request body carries the exact movies, full series, and season cleanups
    to process. Returns 202 immediately with the new cleanup job details.
    """
    total_size = (
        sum(m.size_bytes for m in request.movies)
        + sum(s.size_bytes for s in request.full_series)
        + sum(sc.total_size_bytes for sc in request.season_cleanups)
    )

    run_plan = RunPlan(
        movies=request.movies,
        full_series=request.full_series,
        season_cleanups=request.season_cleanups,
        summary=RunPlanSummary(
            movie_count=len(request.movies),
            full_series_count=len(request.full_series),
            season_cleanup_count=len(request.season_cleanups),
            total_size=total_size,
            total_size_fmt=_format_size(total_size),
        ),
    )

    job = _cleanup_manager().submit(run_plan, simulate=request.simulate)
    return _cleanup_job_to_response(job)


@router.get("/cleanup/current")
def get_current_cleanup() -> CleanupJobResponse:
    """Return the active or most recent completed cleanup job. Returns 204 if none."""
    job = _cleanup_manager().get_current()
    if job is None:
        raise HTTPException(status_code=204)
    return _cleanup_job_to_response(job)


@router.get("/cleanup/jobs/{job_id}")
def get_cleanup_job(job_id: str) -> CleanupJobResponse:
    """Get the status and report for a specific cleanup job."""
    job = _cleanup_manager().get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Cleanup job not found")
    return _cleanup_job_to_response(job)


@router.post("/cleanup/jobs/{job_id}/cancel")
def cancel_cleanup_job(job_id: str) -> dict:
    """Request cancellation of a running or queued cleanup job."""
    ok = _cleanup_manager().cancel(job_id)
    if not ok:
        raise HTTPException(
            status_code=404,
            detail="Cleanup job not found or already finished",
        )
    return {"status": "cancelling", "jobId": job_id}


@router.get("/cleanup/history")
def get_cleanup_history() -> list[HistoryEntry]:
    """Return all cleanup history rows, newest first."""
    rows = _db().list_all()
    entries: list[HistoryEntry] = []
    for row in rows:
        season_numbers = None
        if row.get("season_numbers"):
            try:
                season_numbers = json.loads(row["season_numbers"])
            except (ValueError, TypeError):
                season_numbers = None
        entries.append(HistoryEntry(
            id=row["id"],
            path=row["path"],
            media_type=row["media_type"],
            title=row["title"],
            sonarr_id=row.get("sonarr_id"),
            radarr_id=row.get("radarr_id"),
            season_numbers=season_numbers,
            deleted_at=row["deleted_at"],
            size_bytes=row.get("size_bytes", 0),
            simulated=bool(row.get("simulated", 0)),
        ))
    return entries


@router.get("/cleanup/history/has-data")
def cleanup_history_has_data() -> dict:
    """Return whether the history table has any rows."""
    return {"hasData": _db().has_any()}


@router.delete("/cleanup/history/{entry_id}", status_code=204)
def delete_history_entry(entry_id: int) -> None:
    """Remove a single history entry by its ID."""
    _db().delete_by_id(entry_id)


@router.delete("/cleanup/history", status_code=204)
def clear_cleanup_history() -> None:
    """Delete all cleanup history rows."""
    _db().clear_all()


@router.get("/cleanup/report/{job_id}")
def get_cleanup_report(job_id: str) -> CleanupReport:
    """Return the CleanupReport for a completed cleanup job."""
    job = _cleanup_manager().get(job_id)
    if job is None or job.report is None:
        raise HTTPException(status_code=404, detail="Report not found")
    return job.report


@router.get("/cleanup/report/{job_id}/download")
def download_cleanup_report(job_id: str) -> StreamingResponse:
    """Download the cleanup report as a YAML file attachment."""
    job = _cleanup_manager().get(job_id)
    if job is None or job.report is None:
        raise HTTPException(status_code=404, detail="Report not found")

    report_dict = job.report.model_dump(by_alias=True)
    yaml_text = yaml.dump(report_dict, allow_unicode=True, sort_keys=False)
    filename = f"cleanup_report_{job_id[:8]}.yaml"

    return StreamingResponse(
        iter([yaml_text]),
        media_type="application/x-yaml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
