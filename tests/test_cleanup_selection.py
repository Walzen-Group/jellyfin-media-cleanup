"""
Tests that the cleanup execute endpoint only processes user-selected items,
not the full run plan. Verifies that the RunPlan submitted to the
CleanupJobManager contains exactly the items from the request.
"""

from dataclasses import dataclass
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient

from media_cleanup.models import (
    CleanupExecuteRequest,
    FullSeriesDeletion,
    JobStatus,
    MovieDeletion,
    RunPlan,
    SeasonCleanup,
)
from media_cleanup.server.app import create_app


def _make_movie(radarr_id: int, title: str, size: int = 2_000_000_000) -> MovieDeletion:
    """Helper to build a MovieDeletion."""
    return MovieDeletion(
        radarr_id=radarr_id,
        title=title,
        library_path=f"/movies/{title}",
        size_bytes=size,
    )


def _make_full_series(
    sonarr_id: int, title: str, season_count: int = 3, size: int = 10_000_000_000
) -> FullSeriesDeletion:
    """Helper to build a FullSeriesDeletion."""
    return FullSeriesDeletion(
        sonarr_series_id=sonarr_id,
        title=title,
        library_path=f"/tv/{title}",
        size_bytes=size,
        season_count=season_count,
    )


def _make_season_cleanup(
    sonarr_id: int,
    title: str,
    season_numbers: list[int],
    size: int = 5_000_000_000,
) -> SeasonCleanup:
    """Helper to build a SeasonCleanup."""
    return SeasonCleanup(
        sonarr_series_id=sonarr_id,
        title=title,
        library_path=f"/tv/{title}",
        season_numbers=season_numbers,
        total_size_bytes=size,
        episode_file_count=len(season_numbers) * 10,
    )


def _make_fake_cleanup_job(run_plan: RunPlan, simulate: bool) -> object:
    """Return a minimal object that looks like a CleanupJob for response building."""

    @dataclass
    class FakeCleanupJob:
        job_id: str = "fake-job-001"
        status: JobStatus = JobStatus.queued
        simulate: bool = True
        created_at: str = "2026-03-27T00:00:00"
        completed_at: str | None = None
        error: str | None = None
        report: object | None = None

    return FakeCleanupJob(simulate=simulate)


class TestExecuteCleanupSelection:
    """Verify the execute_cleanup endpoint passes only user-selected items."""

    def test_execute_cleanup_only_processes_selected_movies(self):
        """Submit 2 of 5 possible movies. The RunPlan should contain exactly 2."""
        all_movies = [_make_movie(i, f"Movie {i}") for i in range(1, 6)]
        selected_movies = [all_movies[0], all_movies[3]]  # IDs 1 and 4

        request = CleanupExecuteRequest(
            simulate=True,
            movies=selected_movies,
            full_series=[],
            season_cleanups=[],
        )

        captured_plan: list[RunPlan] = []
        mock_manager = MagicMock()
        mock_manager.submit.side_effect = lambda run_plan, simulate: (
            captured_plan.append(run_plan)
            or _make_fake_cleanup_job(run_plan, simulate)
        )

        app = create_app()
        with patch("media_cleanup.server.routes.cleanup_manager", mock_manager):
            client = TestClient(app)
            response = client.post(
                "/api/cleanup/execute",
                content=request.model_dump_json(by_alias=True),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 202
        assert mock_manager.submit.call_count == 1

        plan = captured_plan[0]
        assert len(plan.movies) == 2
        assert plan.movies[0].radarr_id == 1
        assert plan.movies[1].radarr_id == 4
        assert plan.movies[0].title == "Movie 1"
        assert plan.movies[1].title == "Movie 4"

        assert len(plan.full_series) == 0
        assert len(plan.season_cleanups) == 0

        assert plan.summary.movie_count == 2
        assert plan.summary.full_series_count == 0
        assert plan.summary.season_cleanup_count == 0
        assert plan.summary.total_size == sum(m.size_bytes for m in selected_movies)

    def test_execute_cleanup_only_processes_selected_series_and_seasons(self):
        """Submit 1 full series and 2 season cleanups. The RunPlan should match."""
        selected_full = [_make_full_series(10, "Breaking Bad")]
        selected_seasons = [
            _make_season_cleanup(20, "Grey's Anatomy", [3, 7]),
            _make_season_cleanup(30, "The Office", [1, 2, 3]),
        ]

        request = CleanupExecuteRequest(
            simulate=True,
            movies=[],
            full_series=selected_full,
            season_cleanups=selected_seasons,
        )

        captured_plan: list[RunPlan] = []
        mock_manager = MagicMock()
        mock_manager.submit.side_effect = lambda run_plan, simulate: (
            captured_plan.append(run_plan)
            or _make_fake_cleanup_job(run_plan, simulate)
        )

        app = create_app()
        with patch("media_cleanup.server.routes.cleanup_manager", mock_manager):
            client = TestClient(app)
            response = client.post(
                "/api/cleanup/execute",
                content=request.model_dump_json(by_alias=True),
                headers={"Content-Type": "application/json"},
            )

        assert response.status_code == 202
        assert mock_manager.submit.call_count == 1

        plan = captured_plan[0]

        # Full series
        assert len(plan.full_series) == 1
        assert plan.full_series[0].sonarr_series_id == 10
        assert plan.full_series[0].title == "Breaking Bad"

        # Season cleanups
        assert len(plan.season_cleanups) == 2
        assert plan.season_cleanups[0].sonarr_series_id == 20
        assert plan.season_cleanups[0].season_numbers == [3, 7]
        assert plan.season_cleanups[1].sonarr_series_id == 30
        assert plan.season_cleanups[1].season_numbers == [1, 2, 3]

        # Movies
        assert len(plan.movies) == 0

        # Summary counts
        assert plan.summary.movie_count == 0
        assert plan.summary.full_series_count == 1
        assert plan.summary.season_cleanup_count == 2
        expected_size = (
            selected_full[0].size_bytes
            + selected_seasons[0].total_size_bytes
            + selected_seasons[1].total_size_bytes
        )
        assert plan.summary.total_size == expected_size
