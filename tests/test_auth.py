"""
Tests that all backend endpoints enforce Bearer token authentication.

For each endpoint: one test with a valid master token (expects non-401),
one test with no token (expects 401).

Auth module globals (MASTER_TOKEN, OIDC_DISABLE) are read at import time,
so we patch them directly on the module rather than via env vars.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

_TOKEN = "test-secret-token"
_AUTH_HEADER = {"Authorization": f"Bearer {_TOKEN}"}

# Minimal valid bodies for POST endpoints that have Pydantic models.
_ANALYSIS_BODY = {
    "watchedWithinDays": 90,
    "mode": "all",
    "addedThresholdDays": 30,
}
_FILTER_BODY = {
    "categories": ["not_recently_watched"],
    "greedy": False,
    "mediaType": "all",
}
_CLEANUP_EXECUTE_BODY = {
    "simulate": True,
    "movies": [],
    "fullSeries": [],
    "seasonCleanups": [],
}


@pytest.fixture()
def client() -> TestClient:
    """
    Build a TestClient with auth enabled and MASTER_TOKEN set.

    Patches auth module globals directly (they are read at import time,
    so env var monkeypatching after import has no effect).
    All three route-level singletons are replaced with MagicMocks so no
    real DB, JobManager, or CleanupJobManager is needed.
    """
    mock_job_manager = MagicMock()
    mock_cleanup_manager = MagicMock()
    mock_db = MagicMock()

    # Make list_jobs / list_all return empty iterables so routes don't crash.
    mock_job_manager.list_jobs.return_value = []
    mock_job_manager.get_current.return_value = None
    mock_job_manager.get.return_value = None
    mock_cleanup_manager.get_current.return_value = None
    mock_cleanup_manager.get.return_value = None
    mock_db.list_all.return_value = []
    mock_db.has_any.return_value = False

    with (
        patch("media_cleanup.auth.MASTER_TOKEN", _TOKEN),
        patch("media_cleanup.auth.OIDC_DISABLE", False),
        patch("media_cleanup.server.routes.job_manager", mock_job_manager),
        patch("media_cleanup.server.routes.cleanup_manager", mock_cleanup_manager),
        patch("media_cleanup.server.routes.db", mock_db),
    ):
        from media_cleanup.server.app import create_app

        # create_app() calls load_config() and instantiates real managers;
        # patch those constructors so startup doesn't need secrets.yaml.
        with (
            patch("media_cleanup.server.app.load_config", return_value=MagicMock()),
            patch("media_cleanup.server.app.JobManager", return_value=mock_job_manager),
            patch("media_cleanup.server.app.CleanupJobManager", return_value=mock_cleanup_manager),
            patch("media_cleanup.server.app.Database", return_value=mock_db),
        ):
            app = create_app()

        # Re-inject mocks after create_app() may have overwritten module globals.
        import media_cleanup.server.routes as _routes

        _routes.job_manager = mock_job_manager
        _routes.cleanup_manager = mock_cleanup_manager
        _routes.db = mock_db

        yield TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Public endpoint -- no auth required
# ---------------------------------------------------------------------------


def test_auth_config_public(client: TestClient) -> None:
    """GET /api/auth/config is public and must return 200 without a token."""
    resp = client.get("/api/auth/config")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# POST /api/analysis
# ---------------------------------------------------------------------------


def test_post_analysis_valid_token(client: TestClient) -> None:
    resp = client.post("/api/analysis", json=_ANALYSIS_BODY, headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_post_analysis_no_token(client: TestClient) -> None:
    resp = client.post("/api/analysis", json=_ANALYSIS_BODY)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/analysis
# ---------------------------------------------------------------------------


def test_get_analysis_list_valid_token(client: TestClient) -> None:
    resp = client.get("/api/analysis", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_analysis_list_no_token(client: TestClient) -> None:
    resp = client.get("/api/analysis")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/analysis/current
# ---------------------------------------------------------------------------


def test_get_analysis_current_valid_token(client: TestClient) -> None:
    resp = client.get("/api/analysis/current", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_analysis_current_no_token(client: TestClient) -> None:
    resp = client.get("/api/analysis/current")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/analysis/{job_id}/filter
# ---------------------------------------------------------------------------


def test_post_analysis_filter_valid_token(client: TestClient) -> None:
    resp = client.post("/api/analysis/fake-job-id/filter", json=_FILTER_BODY, headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_post_analysis_filter_no_token(client: TestClient) -> None:
    resp = client.post("/api/analysis/fake-job-id/filter", json=_FILTER_BODY)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/analysis/{job_id}/prepare
# ---------------------------------------------------------------------------


def test_post_analysis_prepare_valid_token(client: TestClient) -> None:
    resp = client.post("/api/analysis/fake-job-id/prepare", json=_FILTER_BODY, headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_post_analysis_prepare_no_token(client: TestClient) -> None:
    resp = client.post("/api/analysis/fake-job-id/prepare", json=_FILTER_BODY)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/cleanup/execute
# ---------------------------------------------------------------------------


def test_post_cleanup_execute_valid_token(client: TestClient) -> None:
    resp = client.post("/api/cleanup/execute", json=_CLEANUP_EXECUTE_BODY, headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_post_cleanup_execute_no_token(client: TestClient) -> None:
    resp = client.post("/api/cleanup/execute", json=_CLEANUP_EXECUTE_BODY)
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/cleanup/current
# ---------------------------------------------------------------------------


def test_get_cleanup_current_valid_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/current", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_cleanup_current_no_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/current")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/cleanup/jobs/{id}
# ---------------------------------------------------------------------------


def test_get_cleanup_job_valid_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/jobs/fake-id", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_cleanup_job_no_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/jobs/fake-id")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# POST /api/cleanup/jobs/{id}/cancel
# ---------------------------------------------------------------------------


def test_post_cleanup_cancel_valid_token(client: TestClient) -> None:
    resp = client.post("/api/cleanup/jobs/fake-id/cancel", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_post_cleanup_cancel_no_token(client: TestClient) -> None:
    resp = client.post("/api/cleanup/jobs/fake-id/cancel")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/cleanup/history
# ---------------------------------------------------------------------------


def test_get_cleanup_history_valid_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/history", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_cleanup_history_no_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/cleanup/history/has-data
# ---------------------------------------------------------------------------


def test_get_cleanup_history_has_data_valid_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/history/has-data", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_cleanup_history_has_data_no_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/history/has-data")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/cleanup/history/{id}
# ---------------------------------------------------------------------------


def test_delete_cleanup_history_entry_valid_token(client: TestClient) -> None:
    resp = client.delete("/api/cleanup/history/1", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_delete_cleanup_history_entry_no_token(client: TestClient) -> None:
    resp = client.delete("/api/cleanup/history/1")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# DELETE /api/cleanup/history
# ---------------------------------------------------------------------------


def test_delete_cleanup_history_all_valid_token(client: TestClient) -> None:
    resp = client.delete("/api/cleanup/history", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_delete_cleanup_history_all_no_token(client: TestClient) -> None:
    resp = client.delete("/api/cleanup/history")
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# GET /api/cleanup/report/{job_id}
# ---------------------------------------------------------------------------


def test_get_cleanup_report_valid_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/report/fake-job-id", headers=_AUTH_HEADER)
    assert resp.status_code != 401


def test_get_cleanup_report_no_token(client: TestClient) -> None:
    resp = client.get("/api/cleanup/report/fake-job-id")
    assert resp.status_code == 401
