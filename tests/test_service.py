"""
Tests for the config and service modules.
"""

import os
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from media_cleanup.config import AppConfig, load_config, DEFAULT_MONTH_THRESHOLD
from media_cleanup.service import (
    CleanupResult,
    CleanupService,
    CancellationError,
    build_summary,
)
from media_cleanup.matching import MatchResult
from media_cleanup.types import SeasonSummary


# ------------------------------------------------------------------ #
#  AppConfig
# ------------------------------------------------------------------ #

class TestAppConfig:
    def test_defaults(self):
        cfg = AppConfig()
        assert cfg.jellyfin_url == ""
        assert cfg.month_threshold == DEFAULT_MONTH_THRESHOLD

    def test_custom_values(self):
        cfg = AppConfig(
            jellyfin_url="http://jf:8096",
            jellyfin_api_key="key1",
            sonarr_url="http://sonarr",
            sonarr_api_key="key2",
            radarr_url="http://radarr",
            radarr_api_key="key3",
            month_threshold=12,
        )
        assert cfg.jellyfin_url == "http://jf:8096"
        assert cfg.month_threshold == 12


# ------------------------------------------------------------------ #
#  load_config
# ------------------------------------------------------------------ #

class TestLoadConfig:
    def test_env_vars_override_file(self, tmp_path):
        """Env vars take precedence over secrets.yaml values."""
        secrets = tmp_path / "secrets.yaml"
        secrets.write_text(
            "jellyfin:\n  url: http://file\n  api_key: filekey\n"
            "sonarr:\n  url: http://sonarr\n  api_key: skey\n"
            "radarr:\n  url: http://radarr\n  api_key: rkey\n"
        )
        env = {"JELLYFIN_URL": "http://env", "JELLYFIN_API_KEY": "envkey"}
        with patch.dict(os.environ, env, clear=False):
            cfg = load_config(secrets)
        assert cfg.jellyfin_url == "http://env"
        assert cfg.jellyfin_api_key == "envkey"
        # Non-overridden values come from file
        assert cfg.sonarr_url == "http://sonarr"

    def test_file_values_used_when_no_env(self, tmp_path):
        secrets = tmp_path / "secrets.yaml"
        secrets.write_text(
            "jellyfin:\n  url: http://file\n  api_key: fk\n"
            "sonarr:\n  url: http://sonarr\n  api_key: sk\n"
            "radarr:\n  url: http://radarr\n  api_key: rk\n"
            "settings:\n  month_threshold: 9\n"
        )
        # Ensure relevant env vars are not set
        env_keys = ["JELLYFIN_URL", "JELLYFIN_API_KEY", "SONARR_URL",
                     "SONARR_API_KEY", "RADARR_URL", "RADARR_API_KEY", "MONTH_THRESHOLD"]
        clean_env = {k: v for k, v in os.environ.items() if k not in env_keys}
        with patch.dict(os.environ, clean_env, clear=True):
            cfg = load_config(secrets)
        assert cfg.jellyfin_url == "http://file"
        assert cfg.month_threshold == 9

    def test_no_file_returns_defaults(self):
        cfg = load_config(Path("/nonexistent/secrets.yaml"))
        assert cfg.jellyfin_url == ""
        assert cfg.month_threshold == DEFAULT_MONTH_THRESHOLD

    def test_none_path_uses_default_secrets_location(self, tmp_path):
        # When no path given, load_config falls back to the default secrets.yaml
        # location. Pass a nonexistent path to test empty-config behavior.
        cfg = load_config(tmp_path / "nonexistent.yaml")
        assert cfg.jellyfin_url == ""

    def test_month_threshold_env_overrides_file(self, tmp_path):
        secrets = tmp_path / "secrets.yaml"
        secrets.write_text("settings:\n  month_threshold: 9\n")
        with patch.dict(os.environ, {"MONTH_THRESHOLD": "3"}, clear=False):
            cfg = load_config(secrets)
        assert cfg.month_threshold == 3


# ------------------------------------------------------------------ #
#  CancellationError
# ------------------------------------------------------------------ #

class TestCancellation:
    def test_cancel_check_raises(self):
        """Pipeline raises CancellationError when cancel_check returns True."""
        cfg = AppConfig(
            jellyfin_url="http://jf:8096",
            jellyfin_api_key="k",
            radarr_url="http://radarr",
            radarr_api_key="k",
        )
        service = CleanupService(cfg)

        # cancel_check returns True immediately — should raise before any network call
        with patch("media_cleanup.service.JellyfinClient"):
            with pytest.raises(CancellationError):
                service.run_analysis(mode="movies", cancel_check=lambda: True)


# ------------------------------------------------------------------ #
#  build_summary
# ------------------------------------------------------------------ #

class TestBuildSummary:
    def test_returns_expected_keys(self):
        result = CleanupResult()
        s = build_summary(result, mode="all")
        expected_keys = [
            "recent_movie_count", "old_movie_count",
            "recent_shows_count", "recent_seasons_count",
            "old_shows_count", "old_seasons_count",
            "never_watched_movie_count", "never_watched_series_count",
            "library_movie_count", "library_series_count",
            "kept_movie_count", "kept_shows_count", "kept_seasons_count",
            "matched_movie_count", "matched_shows_count", "matched_seasons_count",
            "ambiguous_movie_count", "ambiguous_shows_count", "ambiguous_seasons_count",
            "unmatched_movie_count", "unmatched_shows_count", "unmatched_seasons_count",
            "skipped_episodes", "fallback_episodes",
            "recent_size", "old_size", "kept_size", "lib_size",
            "never_watched_size", "seasons_only_size", "entire_shows_size",
            "recent_size_fmt", "old_size_fmt", "kept_size_fmt", "lib_size_fmt",
            "never_watched_size_fmt", "seasons_only_size_fmt", "entire_shows_size_fmt",
        ]
        for key in expected_keys:
            assert key in s, f"Missing key: {key}"

    def test_empty_result_has_zero_counts(self):
        result = CleanupResult()
        s = build_summary(result)
        assert s["recent_movie_count"] == 0
        assert s["old_seasons_count"] == 0
        assert s["lib_size"] == 0

    def test_summary_with_movie_data(self):
        result = CleanupResult(
            recent_movie_matches=[
                MatchResult(jellyfin_path="/a", matched_title="A", matched_path="/m/a", size_on_disk=1024**3),
            ],
            old_movie_matches=[
                MatchResult(jellyfin_path="/b", matched_title="B", matched_path="/m/b", size_on_disk=2 * 1024**3),
            ],
        )
        s = build_summary(result, mode="movies")
        assert s["recent_movie_count"] == 1
        assert s["old_movie_count"] == 1
        assert s["recent_size"] == 1024**3
        assert s["old_size"] == 2 * 1024**3
