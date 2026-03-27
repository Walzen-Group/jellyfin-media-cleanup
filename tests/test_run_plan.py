"""
Tests for build_run_plan() to verify correct classification of series
into full deletions vs season cleanups.

Key scenarios:
- Series with only 1 season on disk should be a full deletion (House of Cards case)
- Series with all on-disk seasons selected should be a full deletion
- Series with only some on-disk seasons selected should be a season cleanup
- Series with total_season_count=0 (lookup miss) should fall back to full deletion
"""

import pytest

from media_cleanup.models import (
    build_run_plan,
    FilteredResult,
    FilteredSummary,
    SeriesGroup,
    SeasonInfo,
    MovieMatch,
)


def _make_series(
    title: str,
    sonarr_id: int,
    seasons: list[tuple[int, str, int]],  # (season_number, status, size_bytes)
    total_season_count: int = 0,
    path: str | None = None,
) -> SeriesGroup:
    """Helper to build a SeriesGroup with the given seasons."""
    return SeriesGroup(
        title=title,
        library_path=path or f"/tv/{title}",
        sonarr_series_id=sonarr_id,
        total_season_count=total_season_count,
        status="old",
        seasons=[
            SeasonInfo(
                season_number=sn,
                last_played="",
                episode_count=0,
                total_episodes=13,
                size_bytes=size,
                status=status,
            )
            for sn, status, size in seasons
        ],
        size_bytes=sum(s for _, _, s in seasons),
    )


def _make_filtered(series: list[SeriesGroup]) -> FilteredResult:
    """Wrap series in a FilteredResult."""
    return FilteredResult(
        movies=[],
        series=series,
        summary=FilteredSummary(),
    )


class TestBuildRunPlan:
    """Tests for build_run_plan classification logic."""

    def test_single_season_on_disk_is_full_deletion(self):
        """House of Cards (US): Sonarr has 6 seasons listed but only season 2
        has files on disk. With total_season_count=1 (1 on-disk season) and
        1 filtered season, this should be a full series deletion, not a
        season cleanup."""
        sg = _make_series(
            "House of Cards (US)",
            sonarr_id=42,
            seasons=[(2, "old", 5_000_000_000)],
            total_season_count=1,  # only 1 season has files on disk
        )
        plan = build_run_plan(_make_filtered([sg]))

        assert len(plan.full_series) == 1
        assert len(plan.season_cleanups) == 0
        assert plan.full_series[0].title == "House of Cards (US)"
        assert plan.full_series[0].sonarr_series_id == 42
        assert plan.full_series[0].season_count == 1

    def test_all_on_disk_seasons_selected_is_full_deletion(self):
        """A show with 3 seasons on disk, all 3 in the filtered set.
        Should be a full series deletion."""
        sg = _make_series(
            "Breaking Bad",
            sonarr_id=10,
            seasons=[
                (1, "old", 10_000_000_000),
                (2, "old", 12_000_000_000),
                (3, "old", 11_000_000_000),
            ],
            total_season_count=3,
        )
        plan = build_run_plan(_make_filtered([sg]))

        assert len(plan.full_series) == 1
        assert len(plan.season_cleanups) == 0
        assert plan.full_series[0].season_count == 3

    def test_partial_seasons_selected_is_season_cleanup(self):
        """A show with 5 on-disk seasons but only 2 in the filtered set
        (greedy mode). Should be a season cleanup with the 2 specific seasons."""
        sg = _make_series(
            "Grey's Anatomy",
            sonarr_id=99,
            seasons=[
                (3, "old", 8_000_000_000),
                (7, "old", 9_000_000_000),
            ],
            total_season_count=5,  # 5 seasons on disk total
        )
        plan = build_run_plan(_make_filtered([sg]))

        assert len(plan.full_series) == 0
        assert len(plan.season_cleanups) == 1
        cleanup = plan.season_cleanups[0]
        assert cleanup.title == "Grey's Anatomy"
        assert cleanup.season_numbers == [3, 7]
        assert cleanup.sonarr_series_id == 99

    def test_total_season_count_zero_falls_back_to_full_deletion(self):
        """If total_season_count is 0 (lookup miss), treat as full deletion
        when there are filtered seasons present."""
        sg = _make_series(
            "Marco Polo",
            sonarr_id=55,
            seasons=[(2, "old", 4_000_000_000)],
            total_season_count=0,  # lookup missed
        )
        plan = build_run_plan(_make_filtered([sg]))

        assert len(plan.full_series) == 1
        assert len(plan.season_cleanups) == 0
        assert plan.full_series[0].title == "Marco Polo"

    def test_series_without_sonarr_id_is_skipped(self):
        """Series with no sonarr_series_id should not appear in the plan."""
        sg = SeriesGroup(
            title="Unknown Show",
            library_path=None,
            sonarr_series_id=None,
            status="old",
            seasons=[
                SeasonInfo(
                    season_number=1, last_played="", episode_count=0,
                    total_episodes=10, size_bytes=1_000_000, status="old",
                )
            ],
            size_bytes=1_000_000,
        )
        plan = build_run_plan(_make_filtered([sg]))

        assert len(plan.full_series) == 0
        assert len(plan.season_cleanups) == 0

    def test_movie_deletion(self):
        """Movies with radarr_id should become MovieDeletion entries."""
        movie = MovieMatch(
            title="Inception",
            jellyfin_path="/movies/Inception/Inception.mkv",
            library_path="/movies/Inception",
            radarr_id=123,
            size_bytes=2_000_000_000,
            status="old",
        )
        plan = build_run_plan(FilteredResult(
            movies=[movie],
            series=[],
            summary=FilteredSummary(),
        ))

        assert len(plan.movies) == 1
        assert plan.movies[0].radarr_id == 123
        assert plan.movies[0].title == "Inception"

    def test_summary_counts_and_size(self):
        """Summary should correctly count items and sum sizes."""
        sg_full = _make_series(
            "Show A", sonarr_id=1,
            seasons=[(1, "old", 5_000_000_000)],
            total_season_count=1,
        )
        sg_partial = _make_series(
            "Show B", sonarr_id=2,
            seasons=[(2, "old", 3_000_000_000)],
            total_season_count=4,
        )
        movie = MovieMatch(
            title="Movie X",
            jellyfin_path="/m/x.mkv",
            library_path="/m/x",
            radarr_id=10,
            size_bytes=1_000_000_000,
            status="old",
        )
        plan = build_run_plan(FilteredResult(
            movies=[movie],
            series=[sg_full, sg_partial],
            summary=FilteredSummary(),
        ))

        assert plan.summary.movie_count == 1
        assert plan.summary.full_series_count == 1
        assert plan.summary.season_cleanup_count == 1
        assert plan.summary.total_size == 9_000_000_000  # 5 + 3 + 1 GB
