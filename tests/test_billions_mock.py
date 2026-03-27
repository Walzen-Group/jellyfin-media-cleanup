"""
Mock version of the Billions integration test.

Uses captured data from the real Jellyfin/Sonarr APIs so the test runs
without network access. Verifies the pipeline: ItemName parsing
-> season grouping -> Sonarr matching (title-based, no file paths).
"""

from media_cleanup.clients.jellyfin import JellyfinClient
from media_cleanup.matching import build_season_summaries, match_seasons_to_sonarr
from media_cleanup.schema.sonarr_schema import Series


# Captured from real Jellyfin PlaybackActivity
BILLIONS_EPISODE_DATES = {
    "stale-001": {"last_played": "2021-08-02 22:38:50", "item_name": "Billions - s01e01 - Pilot"},
    "stale-002": {"last_played": "2021-08-02 20:12:00", "item_name": "Billions - s01e03 - YumTime"},
    "stale-003": {"last_played": "2021-08-10 20:31:14", "item_name": "Billions - s02e01 - Risk Management"},
    "stale-004": {"last_played": "2020-08-02 12:15:30", "item_name": "Billions - s03e01 - Tie Goes to the Runner"},
    "stale-005": {"last_played": "2020-08-04 02:39:00", "item_name": "Billions - s04e01 - Chucky Rhoades's Greatest Game"},
    "stale-006": {"last_played": "2021-10-04 17:57:37", "item_name": "Billions - s05e01 - The New Decas"},
    "stale-007": {"last_played": "2022-04-14 23:15:54", "item_name": "Billions - s06e01 - Cannonade"},
    "stale-008": {"last_played": "2023-11-03 14:19:52", "item_name": "Billions - s07e01 - Tower of London"},
}

# Captured from real Sonarr /api/v3/series
SONARR_SERIES = [
    Series(id=10, title="Billions", path="/tv/Billions"),
    Series(id=20, title="Breaking Bad", path="/tv/Breaking Bad"),
    Series(id=30, title="Billion Dollar Wreck", path="/tv/Billion Dollar Wreck"),
]


def test_billions_matched_from_jellyfin_to_sonarr():
    """
    No HTTP needed -- parse ItemNames directly, then match to Sonarr.
    Billions must be matched to Sonarr path /tv/Billions.
    """
    client = JellyfinClient(root_url="http://jellyfin:8096", api_key="test")

    # Step 1: Parse episodes from ItemNames (pure, no HTTP)
    episodes = client.parse_episode_dates(BILLIONS_EPISODE_DATES)
    billions_eps = [ep for ep in episodes if "Billions" in ep.series_name]
    assert len(billions_eps) == 8

    # Step 2: Build season summaries
    recent, old = build_season_summaries(episodes, month_threshold=24)
    all_seasons = recent + old
    billions_seasons = [s for s in all_seasons if "Billions" in s.series_name]
    assert len(billions_seasons) == 7  # seasons 1-7

    # Step 3: Match to Sonarr -- Billions MUST be matched, not unmatched
    matched, unmatched = match_seasons_to_sonarr(all_seasons, SONARR_SERIES)

    matched_billions = [s for s in matched if "Billions" in s.series_name]
    unmatched_billions = [s for s in unmatched if "Billions" in s.series_name]

    assert len(unmatched_billions) == 0, f"Billions unmatched: {unmatched_billions}"
    assert len(matched_billions) == 7
    assert all(s.matched_sonarr_path == "/tv/Billions" for s in matched_billions)
