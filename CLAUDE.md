# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Automatic media cleanup tool for Jellyfin. Cross-references watch history from Jellyfin with metadata from Sonarr/Radarr to identify media files eligible for deletion based on watch metrics (e.g., movies watched more than N months ago).

The project has two modes of operation:
- **CLI mode** (`launch.py`): Fetch, match, classify, and write a YAML report. Rich progress bars in terminal.
- **Server mode** (`media-cleanup-server`): FastAPI backend with a Vue 3 frontend. Runs analysis as background jobs, streams progress via WebSocket, exposes results via REST API.

## Running

```bash
# Install dependencies (uses uv)
uv sync

# CLI: run analysis (all media)
uv run media-cleanup

# CLI: movies or series only
uv run media-cleanup --mode movies
uv run media-cleanup --mode series

# Server: FastAPI backend (port 8000)
uv run media-cleanup-server

# Frontend: dev server (port 5173)
cd frontend && pnpm install && pnpm dev

# Run tests
uv run pytest tests/
```

## VS Code

Launch configs in `.vscode/launch.json` — always create/update these when adding new run modes or entry points. Current configs:
- **Media Cleanup: All** — default CLI mode, runs both movies + series
- **Media Cleanup: Movies Only** — `--mode movies`
- **Media Cleanup: Series Only** — `--mode series`
- **Media Cleanup: Server** — FastAPI backend with uvicorn (port 8000, auto-reload)
- **Frontend: Dev Server** — Vite dev server for Vue frontend
- **Scratchpad / Scratchpad2** — ad-hoc scripts

## Testing

Tests use **pytest** with **pytest-recording** (VCR cassettes) for caching real API responses.

- `tests/test_billions_integration.py` — integration test hitting real Jellyfin + Sonarr APIs; uses `@pytest.mark.vcr()` to cache responses in `tests/cassettes/`. To re-record, delete the cassette directory.
- `tests/test_billions_mock.py` — mock version using captured data constants, no network needed.
- `tests/test_matching.py` — unit and integration tests for the matching engine. Covers exact match, year-stripped match, watch-date disambiguation, length ratio guard, word-boundary matching, normalize_title, and end-to-end `match_seasons_to_sonarr`. No network or mocking required.

Requires `secrets.yaml` in project root for integration tests (skipped if missing).

## Architecture

### Entry Points

**`src/media_cleanup/launch.py`** — CLI orchestrator. Fetches Jellyfin watch history, resolves metadata, fetches Sonarr/Radarr libraries, runs matching, classifies results into recently/not-recently/keep/unmatched/collision/never-watched, and writes a YAML report. Uses Rich for progress bars (section headers for Movies/TV Shows, tasks added hidden and revealed as they arrive). Imports `build_summary` from `models.py`.

**`src/media_cleanup/server/`** — FastAPI server:
- `app.py` — creates the FastAPI app, registers routes, mounts the Vue frontend static files (`/dist`), sets up WebSocket broadcast hook on the `JobManager`.
- `routes.py` — REST API endpoints (see REST API section in README).
- `jobs.py` — `JobManager` class: sequential job queue with a daemon worker thread. Each job runs `CleanupService.run_analysis()`, reports progress via throttled WebSocket broadcasts, and stores the completed `AnalysisResult` on the job.

### Core Pipeline

**`src/media_cleanup/service.py`** — `CleanupService.run_analysis()`. Returns a `CleanupResult` dataclass with:
- `recent_movie_matches`, `old_movie_matches`, `kept_movie_matches`, `collision_movie_matches` — `MatchResult` lists
- `recent_seasons_matched`, `recent_seasons_unmatched`, `old_seasons_matched`, `old_seasons_unmatched`, `kept_season_matches`, `collision_season_matches` — `SeasonSummary` lists
- `all_movies`, `all_series` — full Radarr/Sonarr libraries
- `episode_dates`, `episodes` — raw vs resolved Jellyfin episodes (for stats)

Collision detection happens in `service.py` post-match: multiple Jellyfin items that map to the same library path (movie) or multiple Jellyfin series names that map to the same Sonarr path (series) are flagged as collisions.

Progress callbacks use `Callable[[str, int, int], None]` signature: `(step_name, current, total)`. Two-pass series matching uses offset-based totals so the first pass fills 0-50% and the second fills 50-100% of a shared progress bar.

### Models

**`src/media_cleanup/models.py`** — central hub for all Pydantic models. Shared between CLI and server.

All API-facing models inherit from `_Base` which sets `alias_generator=to_camel` and `populate_by_name=True`. This means Python fields like `job_id`, `progress_percent`, `size_bytes` are serialized as `jobId`, `progressPercent`, `sizeBytes` in JSON. The frontend always receives camelCase.

Key models:
- `AnalysisRequest` — mode, month_threshold, added_threshold
- `JobResponse` — job status/progress for the REST API
- `MovieMatch` — single movie result (jellyfin_path, library_path, match_method, fuzzy_score, size_bytes, is_ambiguous, added, status)
- `SeasonInfo` — per-season data (season_number, last_played, episode_count, total_episodes, size_bytes, status)
- `SeriesGroup` — per-show data (title, library_path, match_method, status, seasons list, colliding_names)
- `MediaSection` — `{movies: [], series: []}` container for one category
- `AnalysisResult` — top-level result with sections: recently_watched, not_recently_watched, keep, collision, unmatched, never_watched, never_new, summary
- `SummaryModel` — composed of CategoryStats, MatchingStats, EpisodeStats, SpaceSavings sub-models
- `CategoryStats` — per-category counts and sizes (movie_count, shows_count, seasons_count, total_size, movie_size, series_size, *_fmt formatted strings)
- `MatchingStats` — matched/ambiguous/unmatched/collision counts
- `EpisodeStats` — skipped and fallback episode counts
- `SpaceSavings` — estimated disk savings

`cleanup_result_to_response()` converts a `CleanupResult` into an `AnalysisResult`:
- Movies are tagged by category from `CleanupResult` fields.
- Series are unified into one `SeriesGroup` per show via `_build_all_series_groups()`, which merges all seasons across all categories, annotates each season with a status tag, derives a show-level status (`mixed` if seasons have different statuses), and populates `colliding_names` when a show has multiple Jellyfin names mapping to the same Sonarr path.
- Never-watched series are appended from the full Sonarr library, split into `never` vs `never_new` based on `added_threshold`.

`build_summary()` computes `SummaryModel` statistics from a `CleanupResult`.

### Matching

**`src/media_cleanup/matching.py`** — title matching logic. All functions accept a `ProgressCallback = Callable[[str, int, int], None]` instead of Rich objects.

Key functions and constants:
- `LENGTH_RATIO_THRESHOLD = 0.65` — minimum ratio of shorter/longer title length (after year-stripping) required for any fuzzy or word-boundary match to proceed. Prevents short titles (e.g., "House") from matching long ones (e.g., "House of Guinness").
- `FUZZY_THRESHOLD = 88` — minimum rapidfuzz `token_sort_ratio` score for a fuzzy match.
- `AMBIGUITY_MARGIN = 5` — if two candidates score within this margin of each other, the match is flagged ambiguous.
- `normalize_title(title)` — lowercases, replaces `&` with `and`, strips punctuation, collapses whitespace. Used for grouping Jellyfin episode data by series name (so "Avatar: The Last Airbender" and "Avatar The Last Airbender" merge correctly).
- `_strip_year(title)` — removes trailing ` (YYYY)` suffix using regex. Years must be stripped BEFORE normalizing (normalize removes parentheses).
- `_extract_year(title)` — returns the year integer from a ` (YYYY)` suffix, or None.
- `_length_ratio(a, b)` — ratio of `min/max` lengths after year-stripping both titles.
- `_pick_by_watch_date(candidates, watch_year)` — for multiple series with the same base title but different years, picks the series whose year is closest to (but not after) the watch year. Fallback: the series with the earliest year.
- `_path_match_season(season, sonarr_series)` — 3-pass matching:
  1. Exact normalized title match
  2. Year-stripped normalized match, with `_pick_by_watch_date` disambiguation when multiple candidates remain
  3. Word-boundary containment check (one title contains all words of the other) with length ratio guard
  Falls back to rapidfuzz `token_sort_ratio` if no pass succeeds.

### API Clients

**`src/media_cleanup/clients/`**:
- `jellyfin.py` — `JellyfinClient`: Queries Jellyfin's Playback Reporting plugin via custom SQL. Gets movies (recently/not-recently watched) and all watched episode dates with ItemName for fallback. Resolves episode metadata via `/items` API, falling back to parsing ItemName (format: `"Series - s01e05 - Episode Title"`) for stale IDs. Chunks item IDs (~200 per request) due to URI length limits. Uses `MediaBrowser Token` auth header. Note: `requests` is aliased as `re` — intentional, not a bug.
- `sonarr.py` — `SonarrClient`: Fetches all series, supports "keep" tag filtering. Uses Sonarr API v3 with `X-Api-Key` header.
- `radarr.py` — `RadarrClient`: Fetches all movies, supports "keep" tag filtering. Same pattern as SonarrClient.

The Jellyfin Playback Reporting plugin has a known typo: the response field is `colums` (not `columns`).

### Output

**`src/media_cleanup/output.py`** — Generates a YAML report for CLI mode with sections: recently_watched, not_recently_watched, keep, collision, unmatched, ambiguous_matches. Series grouped by title with sorted season lists. Includes `colliding_names` key when a show has multiple Jellyfin names mapping to the same library path.

### Schemas

**`src/media_cleanup/schema/`**:
- `sonarr_schema.py` — TypedDict definitions for Sonarr API v3 responses.
- `radarr_schema.py` — TypedDict definitions for Radarr API v3 responses.

### Types

**`src/media_cleanup/types.py`**:
- `EpisodeInfo` — resolved episode with series_name, season_number, file_path, last_played.
- `SeasonSummary` — grouped season with match results (series_name, season_number, last_played, episode_count, size_on_disk, matched_sonarr_path, match_method, fuzzy_score, is_ambiguous).

### Frontend

**`frontend/`** — Vue 3 + Vite + TypeScript + Tailwind CSS + PrimeVue. Managed with **pnpm**.

- `src/types/api.ts` — TypeScript interfaces mirroring the Python Pydantic models (camelCase). All API data flows through these types.
- `src/stores/jobStore.ts` — Pinia store. Holds the current job and all results. Computes `allMovies` and `allSeries` as flat arrays with status tags (see Data Wrangling section in README). Handles WebSocket messages for live progress updates.
- `src/composables/useApi.ts` — thin HTTP/WS client composable.
- `src/views/DashboardView.vue` — main page: shows AnalysisControls, ProgressBar, SummaryPanel, MovieTable, SeriesTable.
- `src/components/`:
  - `AnalysisControls.vue` — start/cancel analysis form
  - `ProgressBar.vue` — live progress display
  - `SummaryPanel.vue` — summary statistics grid
  - `MovieTable.vue` — filterable/sortable movie table
  - `SeriesTable.vue` — filterable/sortable series table with expandable season rows and collision info
  - `SeasonDot.vue` — colored dot indicating season watch status

## Docker

A multi-stage `Dockerfile` is provided:
- Stage 1 (node:22-alpine): installs pnpm via corepack, builds the Vue frontend to `/app/dist`.
- Stage 2 (python:3.11-slim): installs uv from ghcr, syncs Python deps, copies the built frontend dist into the image.

All secrets (Jellyfin URL/token, Sonarr/Radarr URL/key) are passed as environment variables. Port 8000 exposed. `docker-compose.yml` is provided as a reference.

## Key Patterns

- All clients take `root_url` and `api_key` in constructor; credentials come from `secrets.yaml` (gitignored) or environment variables.
- Clients use `requests` library directly with `raise_for_status()` for error handling.
- Rich library used for CLI progress bars (spinner, bar, ETA) and summary table.
- Pydantic v2 with `alias_generator=to_camel` for all API-facing models -- Python snake_case, JSON camelCase.
- `ProgressCallback = Callable[[str, int, int], None]` threading throughout service/matching (no Rich dependency in matching layer).
- `CancelCheck = Callable[[], bool]` is passed into long-running chunked operations (`get_episode_metadata`, `get_file_paths`) so cancellation is responsive even mid-step, not just between pipeline steps.
- WebSocket connection uses a grace period (2s retries for the first 10s) then exponential backoff (capped at 30s). A 5s handshake timeout prevents stuck connections (Docker Desktop on Windows has slow WebSocket upgrades).
- The Run Analysis button is disabled when WebSocket is not connected (`wsConnected` is provided from App.vue via provide/inject).
- Cancellation UI shows "Cancelling..." for a minimum of 1.5s so the user always sees feedback, even if the API responds instantly.
- Frontend async state flags (submitting, cancelling, loading) use `try/finally` for resets, not Vue watchers. Watchers can fire during Vue's pre-flush cycle and reset flags before the DOM updates, making spinners invisible.
- `startAnalysis` in the job store guards against overwriting `currentJob` if WebSocket messages have already updated it (race condition where `job_failed` arrives before the HTTP 202 response).
- Docker secrets are passed via `secrets.env` file (see `secrets.example.env`). Never committed to git.

## Dependencies

Managed via `uv` with `pyproject.toml`.

Backend: `fastapi`, `uvicorn`, `websockets`, `requests`, `pydantic`, `pyyaml`, `rapidfuzz`, `rich`.
Dev: `pytest`, `pytest-recording`, `vcrpy`.

Frontend: Vue 3, Vite, TypeScript, Tailwind CSS v4, PrimeVue 4, Pinia.
Frontend package manager: **pnpm** (not npm).
