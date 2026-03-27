---
name: Stage 5 backend implementation
description: Stage 5 cleanup execution backend is fully implemented — new files, models, endpoints, and the run_plan storage pattern on Job
type: project
---

Stage 5 backend (cleanup execution) is complete as of 2026-03-27.

**Why:** Wizard was missing the actual execution step; this wires Radarr/Sonarr deletions to a SQLite history store with real-time WS progress.

**How to apply:** Frontend work (CleanupPanel, HistoryPanel, store updates) can proceed — all API contracts are documented in the Frontend Integration Note produced during implementation.

Key design decisions:
- `RunPlan` is stored on the `Job` dataclass (field `run_plan`) when `/prepare` is called — `/cleanup/execute` reads it from there by `job_id`.
- `CleanupExecutor.execute()` returns a `CleanupReport` with `job_id=""` — `CleanupJobManager` fills in the real job_id before storing on the job.
- DB uses `INSERT OR IGNORE` on `path` as dedup key, so partial/cancelled runs are idempotent.
- Cancel check fires between items only — never mid-deletion.
- Verification retries once after 1.5s for both movie (404 or hasFile==False) and series (404) and season (file count==0).
