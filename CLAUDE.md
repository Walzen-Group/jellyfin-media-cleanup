# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automatic media cleanup tool for Jellyfin. Cross-references watch history from Jellyfin with metadata from Sonarr/Radarr to identify media files eligible for deletion based on watch metrics (e.g., movies watched more than N months ago). Currently implements **Stage 1** (read-only): fetch data, match, and produce a YAML report.

## Running

```bash
# Install dependencies (uses uv)
uv sync

# Run via entry point
uv run media-cleanup

# Or run the module directly
uv run python src/media_cleanup/launch.py

# Run tests
uv run pytest tests/
```

## Testing

Tests use **pytest** with **pytest-recording** (VCR cassettes) for caching real API responses.

- `tests/test_billions_integration.py` — integration test hitting real Jellyfin + Sonarr APIs; uses `@pytest.mark.vcr()` to cache responses in `tests/cassettes/`. To re-record, delete the cassette directory.
- `tests/test_billions_mock.py` — mock version using captured data constants, no network needed.

Requires `secrets.yaml` in project root for integration tests (skipped if missing).

## Architecture

**Entry point**: `src/media_cleanup/launch.py` — full Stage 1 orchestrator: fetch Jellyfin watch history, resolve metadata, fetch Sonarr/Radarr libraries, match, classify into recently/not-recently/keep/unmatched, and write YAML report.

**API Clients** (`src/media_cleanup/clients/`):
- `jellyfin.py` — `JellyfinClient`: Queries Jellyfin's Playback Reporting plugin via custom SQL. Gets movies (recently/not-recently watched) and all watched episode dates with ItemName for fallback. Resolves episode metadata via `/items` API, falling back to parsing ItemName (format: `"Series - s01e05 - Episode Title"`) for stale IDs. Chunks item IDs (~200 per request) due to URI length limits. Uses `MediaBrowser Token` auth header.
- `sonarr.py` — `SonarrClient`: Fetches all series, supports "keep" tag filtering. Uses Sonarr API v3 with `X-Api-Key` header.
- `radarr.py` — `RadarrClient`: Fetches all movies, supports "keep" tag filtering. Same pattern as SonarrClient.

**Matching** (`src/media_cleanup/matching.py`):
- Movies: path prefix matching first, then rapidfuzz fallback (threshold 80, ambiguity margin 5).
- Series: season-level matching — groups episodes by (series_name, season_number), classifies by MAX(last_played) vs threshold, matches to Sonarr via title-in-title check then fuzzy fallback.
- Matching runs against ALL library items (including keep-tagged), then post-match splits into eligible vs kept.

**Types** (`src/media_cleanup/types.py`):
- `EpisodeInfo` — resolved episode with series_name, season_number, file_path, last_played.
- `SeasonSummary` — grouped season with match results, ambiguity info.

**Output** (`src/media_cleanup/output.py`):
- Generates YAML report with sections: recently_watched, not_recently_watched, keep, unmatched, ambiguous_matches.
- Series grouped by title with sorted season lists.

**Schemas** (`src/media_cleanup/schema/`):
- `sonarr_schema.py` — TypedDict definitions for Sonarr API v3 responses.
- `radarr_schema.py` — TypedDict definitions for Radarr API v3 responses.

**Key patterns**:
- All clients take `root_url` and `api_key` in constructor; credentials come from `secrets.yaml` (gitignored).
- Jellyfin client aliases `requests` as `re` — this is intentional, not a bug.
- The Jellyfin Playback Reporting plugin has a known typo: the response field is `colums` (not `columns`).
- Clients use `requests` library directly with `raise_for_status()` for error handling.
- Rich library used for CLI progress bars (spinner, bar, ETA) and summary table.

## Dependencies

Managed via `uv` with `pyproject.toml`. Dependencies: `requests`, `pyyaml`, `rapidfuzz`, `rich`. Dev: `pytest`, `pytest-recording`, `vcrpy`.
