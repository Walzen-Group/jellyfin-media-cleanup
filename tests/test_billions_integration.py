"""
Integration test: Billions must be matchable from Jellyfin playback history to Sonarr.

Uses VCR cassettes to cache API responses after the first run. Subsequent runs
replay from the cassette without hitting the network.

To re-record: delete tests/cassettes/test_billions_matched_from_jellyfin_to_sonarr.yaml
"""

import pytest
import yaml
from pathlib import Path

from media_cleanup.clients.jellyfin import JellyfinClient
from media_cleanup.clients.sonarr import SonarrClient
from media_cleanup.matching import build_season_summaries, match_seasons_to_sonarr


SECRETS_PATH = Path(__file__).resolve().parent.parent / "secrets.yaml"


def _load_secrets() -> dict:
    if not SECRETS_PATH.exists():
        pytest.skip("secrets.yaml not found — cannot run integration test")
    with open(SECRETS_PATH, 'r') as f:
        return yaml.safe_load(f)


@pytest.fixture(scope="module")
def vcr_config():
    """VCR config: filter out API keys from recorded cassettes."""
    return {
        "filter_headers": ["Authorization", "X-Api-Key"],
        "record_mode": "new_episodes",
    }


@pytest.mark.vcr()
def test_billions_matched_from_jellyfin_to_sonarr():
    """
    Full integration: query Jellyfin playback history for all watched episodes,
    resolve metadata (with fallback for stale IDs), build season summaries,
    fetch Sonarr library, and verify Billions is matched.
    """
    config = _load_secrets()

    jellyfin = JellyfinClient(
        root_url=config['jellyfin']['url'],
        api_key=config['jellyfin']['api_key'],
    )
    sonarr = SonarrClient(
        root_url=config['sonarr']['url'],
        api_key=config['sonarr']['api_key'],
    )

    # Step 1: Get all watched episode dates from Jellyfin playback reporting
    episode_dates = jellyfin.get_all_watched_episode_dates()
    assert len(episode_dates) > 0, "No episodes found in Jellyfin playback history"

    # Step 2: Resolve episode metadata (API + fallback for stale IDs)
    episodes = jellyfin.get_episode_metadata(episode_dates)
    assert len(episodes) > 0, "No episodes could be resolved"

    # Verify Billions episodes exist somewhere in the resolved data
    billions_episodes = [ep for ep in episodes if "Billions" in ep.series_name]
    assert len(billions_episodes) > 0, (
        "Billions not found in resolved episodes — "
        "neither API resolution nor ItemName fallback produced any results"
    )

    # Step 3: Build season summaries
    month_threshold = config.get('settings', {}).get('month_threshold', 24)
    recent_seasons, old_seasons = build_season_summaries(episodes, month_threshold)
    all_seasons = recent_seasons + old_seasons

    billions_seasons = [s for s in all_seasons if "Billions" in s.series_name]
    assert len(billions_seasons) > 0, "Billions has no season summaries"

    # Step 4: Fetch Sonarr library (without keep filter — we want to verify matching works)
    all_series = sonarr.get_all_series()
    sonarr_billions = [s for s in all_series if "Billions" in s['title']]
    assert len(sonarr_billions) > 0, "Billions not found in Sonarr library"

    # Step 5: Match seasons to Sonarr — THE CRITICAL ASSERTION
    matched, unmatched = match_seasons_to_sonarr(all_seasons, all_series)

    matched_billions = [s for s in matched if "Billions" in s.series_name]
    unmatched_billions = [s for s in unmatched if "Billions" in s.series_name]

    assert len(unmatched_billions) == 0, (
        f"Billions seasons are unmatched: {[(s.season_number, s.series_name) for s in unmatched_billions]}"
    )
    assert len(matched_billions) > 0, "No Billions seasons were matched to Sonarr"
    assert all(s.matched_sonarr_path is not None for s in matched_billions), (
        "Some Billions seasons have no Sonarr path"
    )
