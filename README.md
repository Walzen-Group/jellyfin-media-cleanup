# jellyfin-media-cleanup

Automatic media cleanup based on watch metrics. Cross-references Jellyfin watch history with Sonarr/Radarr libraries to identify movies and TV seasons eligible for deletion.

## Features

- Matches Jellyfin play history to Sonarr/Radarr library entries using multi-pass title matching with fuzzy fallback
- Classifies media as: recently watched, not recently watched, never watched, kept (tagged), collision, or unmatched
- Detects "new" never-watched items added within a configurable threshold (skips them from cleanup candidates)
- Detects collisions where multiple Jellyfin entries point to the same library path
- CLI mode: Rich progress bars, YAML report output
- Server mode: FastAPI backend + Vue 3 frontend with live WebSocket progress

## Setup

```bash
# Install Python dependencies
uv sync

# Install frontend dependencies
cd frontend && pnpm install
```

Create `secrets.yaml` in the project root:

```yaml
jellyfin:
  root_url: "http://your-jellyfin:8096"
  api_key: "your-jellyfin-token"
  user_id: "your-user-id"

sonarr:
  root_url: "http://your-sonarr:8989"
  api_key: "your-sonarr-key"
  keep_tag: "keep"        # optional: tag name for items to exclude from cleanup

radarr:
  root_url: "http://your-radarr:7878"
  api_key: "your-radarr-key"
  keep_tag: "keep"        # optional
```

## Running

### CLI

```bash
uv run media-cleanup              # all media
uv run media-cleanup --mode movies
uv run media-cleanup --mode series
```

### Server

```bash
uv run media-cleanup-server       # FastAPI on port 8000
cd frontend && pnpm dev           # Vite dev server on port 5173
```

### Docker

```bash
docker compose up
```

All secrets are passed as environment variables in Docker (see `docker-compose.yml`).

---

## REST API

Base URL: `http://localhost:8000/api`

### Submit analysis

```
POST /api/analysis
```

Request body:

```json
{
  "mode": "all",            // "all" | "movies" | "series"
  "monthThreshold": 6,      // months since last watched before eligible for cleanup
  "addedThreshold": 12      // months since added; never-watched items added more recently are tagged "never_new"
}
```

Response `202 Accepted`:

```json
{
  "jobId": "uuid",
  "status": "queued",
  "progressPercent": 0,
  "progressStep": "Queued",
  "stepIndex": 0,
  "totalSteps": 0,
  "createdAt": "2025-01-01T00:00:00Z",
  "completedAt": null,
  "error": null
}
```

### Get current job

```
GET /api/analysis/current
```

Returns the active (running/queued) job, or the most recent completed job. Returns `204` if no jobs exist. When the job is complete, the full `result` object is included alongside the job fields.

### Get job by ID

```
GET /api/analysis/{jobId}
```

Returns job status. When complete, includes `result`.

### List all jobs

```
GET /api/analysis
```

Returns array of job responses (recent first, no results).

### Cancel job

```
DELETE /api/analysis/{jobId}
```

Cancels a queued or running job. Returns `404` if not found or already finished.

### Clear completed jobs

```
DELETE /api/analysis
```

Removes all completed/cancelled/failed jobs from memory.

### Health check

```
GET /api/health
```

Returns `{"status": "ok"}`.

---

## WebSocket

```
WS /ws
```

Connect to receive live job events. All messages are JSON.

### `job_created`

```json
{
  "type": "job_created",
  "job": { /* JobResponse fields */ }
}
```

### `job_progress`

```json
{
  "type": "job_progress",
  "jobId": "uuid",
  "step": "Matching seasons: 42/100",
  "percent": 42.0,
  "stepIndex": 4,
  "totalSteps": 8
}
```

`stepIndex` and `totalSteps` reflect the pipeline step number (e.g., step 4 of 8 for full mode). `percent` is within the current step (0-100).

### `job_complete`

```json
{ "type": "job_complete", "jobId": "uuid" }
```

After receiving this, fetch `GET /api/analysis/{jobId}` to get the full result.

### `job_cancelled`

```json
{ "type": "job_cancelled", "jobId": "uuid" }
```

### `job_failed`

```json
{ "type": "job_failed", "jobId": "uuid", "error": "error message" }
```

---

## Analysis Result Shape

The `result` field on a completed job has this structure:

```typescript
interface AnalysisResult {
  recentlyWatched: MediaSection
  notRecentlyWatched: MediaSection
  keep: MediaSection
  collision: MediaSection
  unmatched: MediaSection
  neverWatched: MediaSection
  neverNew: MediaSection
  summary: Summary
}

interface MediaSection {
  movies: MovieMatch[]
  series: SeriesGroup[]
}
```

Each category section contains the movies and series that fall into that classification.

**Status values** for movies and series: `recent` | `old` | `kept` | `collision` | `unmatched` | `mixed` | `never` | `never_new`

`mixed` only appears on series where different seasons have different statuses (e.g., one season recently watched, another not).

### MovieMatch

```typescript
interface MovieMatch {
  title: string
  jellyfinPath: string
  libraryPath: string | null    // Radarr library path; null if unmatched
  matchMethod: string | null    // "path", "fuzzy", or null
  fuzzyScore: number | null
  sizeBytes: number
  isAmbiguous: boolean
  ambiguityReason: string | null
  added: string                 // ISO 8601 from Radarr
  status: MediaStatus
}
```

### SeriesGroup

```typescript
interface SeriesGroup {
  title: string
  libraryPath: string | null    // Sonarr series path
  matchMethod: string | null
  fuzzyScore: number | null
  sizeBytes: number             // sum of all matched season sizes
  status: MediaStatus
  added: string                 // ISO 8601 from Sonarr (never-watched only)
  seasons: SeasonInfo[]
  collidingNames: string[]      // when multiple Jellyfin names map to this library path
}

interface SeasonInfo {
  seasonNumber: number
  lastPlayed: string            // ISO 8601; empty string for never-watched
  episodeCount: number          // episodes seen in Jellyfin history
  totalEpisodes: number         // total episodes from Sonarr
  sizeBytes: number
  status: MediaStatus
}
```

### Summary

```typescript
interface Summary {
  recent: CategoryStats
  old: CategoryStats
  neverWatched: CategoryStats
  neverNew: CategoryStats
  library: CategoryStats
  kept: CategoryStats
  matching: MatchingStats
  episodes: EpisodeStats
  spaceSavings: SpaceSavings
}

interface CategoryStats {
  movieCount: number
  showsCount: number
  seasonsCount: number
  totalSize: number             // bytes
  movieSize: number
  seriesSize: number
  totalSizeFmt: string          // human-readable e.g. "1.2 TB"
  movieSizeFmt: string
  seriesSizeFmt: string
}

interface MatchingStats {
  matchedMovieCount: number
  matchedShowsCount: number
  matchedSeasonsCount: number
  ambiguousMovieCount: number
  ambiguousShowsCount: number
  ambiguousSeasonsCount: number
  unmatchedMovieCount: number
  unmatchedShowsCount: number
  unmatchedSeasonsCount: number
  collisionMovieCount: number
  collisionSeasonCount: number
}

interface EpisodeStats {
  skipped: number               // episodes with stale Jellyfin IDs that couldn't be resolved
  fallback: number              // episodes resolved via ItemName parsing (not API)
}

interface SpaceSavings {
  seasonsOnlySize: number       // bytes: old movies + old seasons
  entireShowsSize: number       // bytes: old movies + entire shows where all seasons are old
  seasonsOnlySizeFmt: string
  entireShowsSizeFmt: string
}
```

---

## Frontend Data Wrangling

The Vue frontend (Pinia `jobStore`) receives the categorized `AnalysisResult` from the API and flattens it into two unified arrays: `allMovies` and `allSeries`. Here is why and how.

### Why flatten?

The API categorizes results into separate sections (`recentlyWatched`, `notRecentlyWatched`, etc.) because that separation is useful for summary stats and the YAML report. But the frontend shows a single table for all movies and a single table for all series, with a status column and filter. Having one flat array per media type makes this trivial: the PrimeVue DataTable handles filtering, sorting, and pagination in memory.

### How it works

**Movies** (`allMovies: MovieRow[]`):

The store iterates over each `MediaSection` in the result and tags every movie with its status:

```typescript
// jobStore.ts
const allMovies = computed<MovieRow[]>(() => {
  const r = currentJob.value?.result
  if (!r) return []
  return [
    ...tagMovies(r.recentlyWatched.movies, 'recent'),
    ...tagMovies(r.notRecentlyWatched.movies, 'old'),
    ...tagMovies(r.keep.movies, 'kept'),
    ...tagMovies(r.collision.movies, 'collision'),
    ...tagMovies(r.unmatched.movies, 'unmatched'),
    ...tagMovies(r.neverWatched.movies, 'never'),
    ...tagMovies(r.neverNew.movies, 'never_new'),
  ]
})
```

`tagMovies` spreads the movie object and adds a `status` field. The `MovieRow` type extends `MovieMatch` with `status: MediaStatus`.

**Series** (`allSeries: SeriesRow[]`):

Series are already grouped per show by the backend (one `SeriesGroup` per show, not one per season). The store spreads all series from all sections into a flat array, and adds a computed `totalEpisodes` field (sum of `totalEpisodes` across all seasons):

```typescript
const allSeries = computed<SeriesRow[]>(() => {
  const r = currentJob.value?.result
  if (!r) return []
  const all = [
    ...r.recentlyWatched.series,
    ...r.notRecentlyWatched.series,
    ...r.keep.series,
    ...r.collision.series,
    ...r.unmatched.series,
    ...r.neverWatched.series,
    ...r.neverNew.series,
  ]
  return all.map(s => ({
    ...s,
    totalEpisodes: s.seasons.reduce((sum, sn) => sum + (sn.totalEpisodes || 0), 0),
  }))
})
```

`SeriesRow` extends `SeriesGroup` with `totalEpisodes: number`.

### camelCase convention

All API responses use camelCase because the Python Pydantic models use `alias_generator=to_camel`. The TypeScript types in `src/types/api.ts` match this convention directly. No field name transformation is needed in the frontend -- what comes from the API is used as-is.

### In-memory filtering

`MovieTable.vue` and `SeriesTable.vue` use PrimeVue's `DataTable` with `filterDisplay="row"`. Filters are applied in memory:
- A global text filter matches against `title` and `libraryPath`.
- A `MultiSelect` filter on the status column uses PrimeVue's `in` match mode.
- A `filteredCount` computed property manually applies the same logic to display "N of M" counts (since PrimeVue doesn't expose the filtered row count directly as a reactive value).

The series table adds expandable rows that show a nested DataTable of seasons for that show, plus a collision info box (`collidingNames`) shown when the show has multiple Jellyfin names mapped to the same library path.
