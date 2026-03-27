"""Tests for matching logic — covers the scenarios discussed during development."""

import pytest

from media_cleanup.matching import (
    _title_match_season,
    _pick_by_watch_date,
    _length_ratio,
    _strip_year,
    normalize_title,
    match_seasons_to_sonarr,
    build_season_summaries,
)
from media_cleanup.schema.sonarr_schema import Series
from media_cleanup.types import EpisodeInfo, SeasonSummary


def _series(title: str, path: str | None = None) -> Series:
    """Minimal Series for testing."""
    return Series(id=0, title=title, path=path or f"/tv/{title}")


def _season(name: str, last_played: str = "2025-06-01 12:00:00") -> SeasonSummary:
    """Minimal SeasonSummary for testing."""
    return SeasonSummary(series_name=name, season_number=1, last_played=last_played, episode_count=1)


# ------------------------------------------------------------------ #
#  Exact match (Pass 1)
# ------------------------------------------------------------------ #

def test_exact_match():
    sonarr = [_series("Billions")]
    result = _title_match_season(_season("Billions"), sonarr)
    assert result is not None
    assert result.title == "Billions"


def test_exact_match_case_insensitive():
    sonarr = [_series("billions")]
    result = _title_match_season(_season("Billions"), sonarr)
    assert result is not None


# ------------------------------------------------------------------ #
#  Year-stripped match (Pass 2)
# ------------------------------------------------------------------ #

def test_year_stripped_single_candidate():
    """'Dark Matter' matches 'Dark Matter (2024)' when it's the only option."""
    sonarr = [_series("Dark Matter (2024)")]
    result = _title_match_season(_season("Dark Matter"), sonarr)
    assert result is not None
    assert result.title == "Dark Matter (2024)"


def test_year_stripped_prefers_exact_over_stripped():
    """If both 'Foo' and 'Foo (2024)' exist, 'Foo' matches 'Foo' exactly."""
    sonarr = [_series("Foo (2024)"), _series("Foo")]
    result = _title_match_season(_season("Foo"), sonarr)
    assert result is not None
    assert result.title == "Foo"


# ------------------------------------------------------------------ #
#  Watch-date disambiguation (Pass 2 with multiple candidates)
# ------------------------------------------------------------------ #

def test_pick_by_watch_date_picks_older():
    """Watched in 2025 -> picks (2024), not (2026)."""
    sonarr = [_series("Dark Matter (2024)"), _series("Dark Matter (2026)")]
    result = _title_match_season(_season("Dark Matter", last_played="2025-06-01 12:00:00"), sonarr)
    assert result is not None
    assert result.title == "Dark Matter (2024)"


def test_pick_by_watch_date_picks_newer_when_after():
    """Watched in 2027 -> picks (2026) as the most recent year <= watch year."""
    sonarr = [_series("Dark Matter (2024)"), _series("Dark Matter (2026)")]
    result = _title_match_season(_season("Dark Matter", last_played="2027-01-15 20:00:00"), sonarr)
    assert result is not None
    assert result.title == "Dark Matter (2026)"


def test_pick_by_watch_date_all_newer_picks_earliest():
    """Watched in 2020 but both series are newer -> picks earliest (2024)."""
    sonarr = [_series("Dark Matter (2026)"), _series("Dark Matter (2024)")]
    result = _title_match_season(_season("Dark Matter", last_played="2020-01-01 00:00:00"), sonarr)
    assert result is not None
    assert result.title == "Dark Matter (2024)"


# ------------------------------------------------------------------ #
#  Length ratio blocks short-title false matches (Pass 3)
# ------------------------------------------------------------------ #

def test_short_title_does_not_match_long_name():
    """'House' must NOT match 'House of Guinness' (ratio 5/17 = 0.29)."""
    sonarr = [_series("House")]
    result = _title_match_season(_season("House of Guinness"), sonarr)
    assert result is None


def test_similar_length_word_boundary_matches():
    """'The Office' matches 'The Office US' (ratio 10/13 = 0.77, above threshold)."""
    sonarr = [_series("The Office")]
    result = _title_match_season(_season("The Office US"), sonarr)
    assert result is not None
    assert result.title == "The Office"


# ------------------------------------------------------------------ #
#  Length ratio helpers
# ------------------------------------------------------------------ #

def test_length_ratio_strips_years():
    """'Dark Matter' vs 'Dark Matter (2024)' should have ratio 1.0 after stripping."""
    assert _length_ratio("Dark Matter", "Dark Matter (2024)") == 1.0


def test_length_ratio_without_years():
    assert _length_ratio("House", "House of Guinness") == pytest.approx(5 / 17, abs=0.01)


def test_strip_year():
    assert _strip_year("Dark Matter (2024)") == "Dark Matter"
    assert _strip_year("Billions") == "Billions"
    assert _strip_year("2012 (2009)") == "2012"


# ------------------------------------------------------------------ #
#  Integration: match_seasons_to_sonarr end-to-end
# ------------------------------------------------------------------ #

def test_match_seasons_end_to_end():
    """Mix of exact, year-stripped, and unmatched in one call."""
    sonarr = [
        _series("Billions"),
        _series("Dark Matter (2024)"),
        _series("House"),
    ]
    seasons = [
        _season("Billions"),                # exact match
        _season("Dark Matter"),             # year-stripped match
        _season("House of Guinness"),       # should NOT match House
    ]

    matched, unmatched = match_seasons_to_sonarr(seasons, sonarr)

    matched_names = {s.series_name for s in matched}
    unmatched_names = {s.series_name for s in unmatched}

    assert matched_names == {"Billions", "Dark Matter"}
    assert unmatched_names == {"House of Guinness"}

    # Verify match details
    dm = next(s for s in matched if s.series_name == "Dark Matter")
    assert dm.matched_sonarr_path == "/tv/Dark Matter (2024)"
    assert dm.match_method == "path"


# ------------------------------------------------------------------ #
#  Title normalization
# ------------------------------------------------------------------ #

def test_normalize_title():
    assert normalize_title("Adventure Time: Fionna & Cake") == "adventure time fionna and cake"
    assert normalize_title("Adventure Time: Fionna and Cake") == "adventure time fionna and cake"
    assert normalize_title("Dark Matter (2024)") == "dark matter 2024"
    assert normalize_title("Mr. Robot") == "mr robot"


def test_ampersand_vs_and_matches():
    """'Fionna & Cake' matches 'Fionna and Cake' in Sonarr via normalization."""
    sonarr = [_series("Adventure Time: Fionna and Cake")]
    result = _title_match_season(_season("Adventure Time: Fionna & Cake"), sonarr)
    assert result is not None


def test_ampersand_vs_and_groups_episodes():
    """Episodes with '&' and 'and' variants merge into one season."""
    episodes = [
        EpisodeInfo(item_id="1", series_name="Fionna & Cake", season_number=1,
last_played="2025-01-01 12:00:00"),
        EpisodeInfo(item_id="2", series_name="Fionna and Cake", season_number=1,
last_played="2025-06-01 12:00:00"),
    ]
    recent, old = build_season_summaries(episodes, month_threshold=12)
    all_seasons = recent + old
    # Should produce ONE season, not two
    assert len(all_seasons) == 1
    assert all_seasons[0].episode_count == 2


# ------------------------------------------------------------------ #
#  Collision prevention: exact match trumps loose match
# ------------------------------------------------------------------ #

def test_exact_match_prevents_loose_collision():
    """
    'The Office (US)' should match Sonarr's 'The Office (US)' exactly.
    'The Office' should NOT also match via word-boundary/fuzzy, since
    a more specific name already claimed that Sonarr entry.
    """
    sonarr = [_series("The Office (US)")]
    seasons = [
        _season("The Office (US)"),   # exact match
        _season("The Office"),        # should NOT match (would cause collision)
    ]

    matched, unmatched = match_seasons_to_sonarr(seasons, sonarr)

    matched_names = {s.series_name for s in matched}
    unmatched_names = {s.series_name for s in unmatched}

    assert "The Office (US)" in matched_names
    assert "The Office" in unmatched_names


def test_both_exact_matches_no_collision():
    """
    When Sonarr has both 'The Office' and 'The Office (US)', each
    Jellyfin name should match its exact counterpart -- no collision.
    """
    sonarr = [_series("The Office"), _series("The Office (US)")]
    seasons = [
        _season("The Office"),
        _season("The Office (US)"),
    ]

    matched, unmatched = match_seasons_to_sonarr(seasons, sonarr)

    assert len(matched) == 2
    assert len(unmatched) == 0

    office = next(s for s in matched if s.series_name == "The Office")
    office_us = next(s for s in matched if s.series_name == "The Office (US)")
    assert office.matched_sonarr_path == "/tv/The Office"
    assert office_us.matched_sonarr_path == "/tv/The Office (US)"


def test_loose_match_kept_when_no_exact_competitor():
    """
    When only 'The Office' exists in Jellyfin (no 'The Office (US)'),
    it should still match Sonarr's 'The Office (US)' via loose matching.
    """
    sonarr = [_series("The Office (US)")]
    seasons = [_season("The Office")]

    matched, unmatched = match_seasons_to_sonarr(seasons, sonarr)

    assert len(matched) == 1
    assert matched[0].series_name == "The Office"
    assert matched[0].matched_sonarr_path == "/tv/The Office (US)"


def test_cross_list_dedup_prevents_collision():
    """
    Simulates the service-level scenario: 'The Office (US)' is in one
    match_seasons_to_sonarr call (recent) and 'The Office' is in another
    (old). The cross-list _deduplicate_matches in service.py handles this,
    but we test the underlying function directly here.
    """
    from media_cleanup.matching import _deduplicate_matches

    sonarr = [_series("The Office (US)")]

    # Simulate: "The Office (US)" matched in recent call, "The Office" matched in old call
    recent_season = _season("The Office (US)")
    recent_season.matched_sonarr_path = "/tv/The Office (US)"
    recent_season.match_method = "path"

    old_season = _season("The Office")
    old_season.matched_sonarr_path = "/tv/The Office (US)"
    old_season.match_method = "path"

    combined = [recent_season, old_season]
    unmatched: list[SeasonSummary] = []

    new_matched, new_unmatched = _deduplicate_matches(combined, unmatched, sonarr)

    matched_names = {s.series_name for s in new_matched}
    unmatched_names = {s.series_name for s in new_unmatched}

    assert "The Office (US)" in matched_names, "exact match should be kept"
    assert "The Office" in unmatched_names, "weaker match should be demoted"
