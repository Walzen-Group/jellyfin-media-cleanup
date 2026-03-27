# CLAUDE.md

Automatic media cleanup tool for Jellyfin. Cross-references Jellyfin watch history with Sonarr/Radarr metadata to identify media eligible for deletion based on watch age.

Two modes: **CLI** (`launch.py`) writes a YAML report with Rich progress bars. **Server** (`media-cleanup-server`) is a FastAPI backend + Vue 3 frontend with WebSocket progress and REST API.

## Running

```bash
uv sync                                    # install deps
uv run media-cleanup                       # CLI: all media
uv run media-cleanup --mode movies         # CLI: movies only
uv run media-cleanup --mode series         # CLI: series only
uv run media-cleanup-server                # server (port 8000)
cd frontend && pnpm install && pnpm dev    # frontend dev (port 5173)
uv run pytest tests/                       # run tests
uv run pytest tests/test_matching.py -k test_exact_match  # single test
```

## VS Code

Launch configs in `.vscode/launch.json` -- always update when adding new run modes. Configs: Media Cleanup (All/Movies/Series), Server, Frontend Dev, Scratchpad 1/2.

## Testing

pytest + pytest-recording (VCR cassettes). Requires `secrets.yaml` for integration tests (skipped if missing).

- `test_billions_integration.py` -- real API calls cached via `@pytest.mark.vcr()`
- `test_billions_mock.py` -- mock version, no network
- `test_matching.py` -- matching engine unit tests, no network

## Architecture

### Entry Points

**`launch.py`** -- CLI orchestrator. Fetches watch history, resolves metadata, matches against Sonarr/Radarr, classifies into recently/not-recently/keep/unmatched/collision/never-watched, writes YAML report.

**`server/`** -- `app.py` (FastAPI app, static mount, WebSocket broadcast), `routes.py` (REST endpoints), `jobs.py` (sequential job queue, daemon worker thread, throttled WS broadcasts).

### Core Pipeline

**`service.py`** -- `CleanupService.run_analysis()` returns `CleanupResult` with categorized match lists, full libraries, and episode data. Collision detection: multiple Jellyfin items mapping to same library path.

Progress: `Callable[[str, int, int], None]` (step_name, current, total). Two-pass series matching uses offset-based totals for 0-50% / 50-100% progress.

### Models

**`models.py`** -- all Pydantic models. `_Base` sets `alias_generator=to_camel`, `populate_by_name=True` (snake_case Python, camelCase JSON).

Key models: `AnalysisRequest`, `JobResponse`, `MovieMatch`, `SeasonInfo`, `SeriesGroup`, `MediaSection`, `AnalysisResult` (sections: recently_watched/not_recently_watched/keep/collision/unmatched/never_watched/never_new/summary), `SummaryModel` (CategoryStats/MatchingStats/EpisodeStats/SpaceSavings).

`cleanup_result_to_response()` converts `CleanupResult` to `AnalysisResult`. Series unified per-show via `_build_all_series_groups()` with per-season status tags and show-level `mixed` status. Never-watched split into `never` vs `never_new` by `added_threshold`.

### Matching

**`matching.py`** -- title matching. Constants: `LENGTH_RATIO_THRESHOLD=0.65`, `FUZZY_THRESHOLD=88`, `AMBIGUITY_MARGIN=5`.

Functions: `normalize_title` (lowercase, & -> and, strip punctuation), `_strip_year` (remove trailing (YYYY) -- before normalizing), `_pick_by_watch_date` (closest year <= watch year).

`_path_match_season` 3-pass: exact normalized -> year-stripped with watch-date disambiguation -> word-boundary containment with length guard. Falls back to rapidfuzz `token_sort_ratio`.

### Clients

- `jellyfin.py` -- Playback Reporting plugin SQL queries, episode metadata via `/items` API with ItemName fallback parsing, ~200 IDs per chunk. `requests` aliased as `re` (intentional). Known typo: response field is `colums`.
- `sonarr.py` / `radarr.py` -- fetch libraries with optional "keep" tag filtering. API v3, `X-Api-Key` header.

### Other Modules

- `output.py` -- YAML report for CLI mode
- `schema/` -- TypedDict definitions for Sonarr/Radarr API responses
- `types.py` -- `EpisodeInfo` (resolved episode), `SeasonSummary` (grouped season with match results)

### Frontend

`frontend/` -- Vue 3 + Vite + TypeScript + Tailwind CSS v4 + PrimeVue 4 + Pinia. Managed with **pnpm**.

- `types/api.ts` -- TS interfaces mirroring Pydantic models
- `stores/jobStore.ts` -- Pinia store, flat arrays with status tags, WebSocket handling
- `composables/useApi.ts` -- HTTP/WS client
- `views/DashboardView.vue` -- main page
- `components/` -- AnalysisControls, ProgressBar, SummaryPanel, MovieTable, SeriesTable, SeasonDot, SelectionPanel, PreparePanel, FilteredSummaryBar

## Docker

Multi-stage: node:22-alpine builds frontend, python:3.11-slim runs backend. Secrets via env vars. Port 8000. `docker-compose.yml` provided.

## Key Patterns

- Credentials from `secrets.yaml` (gitignored) or env vars
- `requests` with `raise_for_status()` for error handling
- Pydantic v2 camel aliases on all API models
- `ProgressCallback` / `CancelCheck` callables throughout service/matching (no Rich dependency)
- WebSocket: grace period (2s retries for 10s) then exponential backoff (cap 30s), 5s handshake timeout
- Run Analysis button disabled when WS disconnected
- Cancellation UI shows "Cancelling..." for minimum 1.5s
- Async state flags use `try/finally`, not watchers (watchers can fire during pre-flush)
- `startAnalysis` guards against WS race conditions
- Docker secrets via `secrets.env` (never committed)

## Dependencies

Backend (uv): fastapi, uvicorn, websockets, requests, pydantic, pyyaml, rapidfuzz, rich. Dev: pytest, pytest-recording, vcrpy.
Frontend (pnpm): Vue 3, Vite, TypeScript, Tailwind CSS v4, PrimeVue 4, Pinia.


# context-mode -- MANDATORY routing rules

You have context-mode MCP tools available. These rules are NOT optional -- they protect your context window from flooding. A single unrouted command can dump 56 KB into context and waste the entire session.

## BLOCKED commands -- do NOT attempt these

### curl / wget -- BLOCKED
Any Bash command containing `curl` or `wget` is intercepted and replaced with an error message. Do NOT retry.
Instead use:
- `ctx_fetch_and_index(url, source)` to fetch and index web pages
- `ctx_execute(language: "javascript", code: "const r = await fetch(...)")` to run HTTP calls in sandbox

### Inline HTTP -- BLOCKED
Any Bash command containing `fetch('http`, `requests.get(`, `requests.post(`, `http.get(`, or `http.request(` is intercepted and replaced with an error message. Do NOT retry with Bash.
Instead use:
- `ctx_execute(language, code)` to run HTTP calls in sandbox -- only stdout enters context

### WebFetch -- BLOCKED
WebFetch calls are denied entirely. The URL is extracted and you are told to use `ctx_fetch_and_index` instead.
Instead use:
- `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` to query the indexed content

## REDIRECTED tools -- use sandbox equivalents

### Bash (>20 lines output)
Bash is ONLY for: `git`, `mkdir`, `rm`, `mv`, `cd`, `ls`, `npm install`, `pip install`, and other short-output commands.
For everything else, use:
- `ctx_batch_execute(commands, queries)` -- run multiple commands + search in ONE call
- `ctx_execute(language: "shell", code: "...")` -- run in sandbox, only stdout enters context

### Read (for analysis)
If you are reading a file to **Edit** it -> Read is correct (Edit needs content in context).
If you are reading to **analyze, explore, or summarize** -> use `ctx_execute_file(path, language, code)` instead. Only your printed summary enters context. The raw file content stays in the sandbox.

### Grep (large results)
Grep results can flood context. Use `ctx_execute(language: "shell", code: "grep ...")` to run searches in sandbox. Only your printed summary enters context.

## Tool selection hierarchy

1. **GATHER**: `ctx_batch_execute(commands, queries)` -- Primary tool. Runs all commands, auto-indexes output, returns search results. ONE call replaces 30+ individual calls.
2. **FOLLOW-UP**: `ctx_search(queries: ["q1", "q2", ...])` -- Query indexed content. Pass ALL questions as array in ONE call.
3. **PROCESSING**: `ctx_execute(language, code)` | `ctx_execute_file(path, language, code)` -- Sandbox execution. Only stdout enters context.
4. **WEB**: `ctx_fetch_and_index(url, source)` then `ctx_search(queries)` -- Fetch, chunk, index, query. Raw HTML never enters context.
5. **INDEX**: `ctx_index(content, source)` -- Store content in FTS5 knowledge base for later search.

## Subagent routing

When spawning subagents (Agent/Task tool), the routing block is automatically injected into their prompt. Bash-type subagents are upgraded to general-purpose so they have access to MCP tools. You do NOT need to manually instruct subagents about context-mode.

## Output constraints

- Keep responses under 500 words.
- Write artifacts (code, configs, PRDs) to FILES -- never return them as inline text. Return only: file path + 1-line description.
- When indexing content, use descriptive source labels so others can `ctx_search(source: "label")` later.

## ctx commands

| Command | Action |
|---------|--------|
| `ctx stats` | Call the `ctx_stats` MCP tool and display the full output verbatim |
| `ctx doctor` | Call the `ctx_doctor` MCP tool, run the returned shell command, display as checklist |
| `ctx upgrade` | Call the `ctx_upgrade` MCP tool, run the returned shell command, display as checklist |
