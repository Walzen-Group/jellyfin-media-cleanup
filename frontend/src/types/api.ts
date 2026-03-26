/**
 * Request to start a new analysis job.
 * Mode: which media types to analyze. Thresholds in months.
 * Note: These TypeScript field names match the camelCase returned by the Python API
 * (Python uses snake_case internally but aliases to camelCase via Pydantic).
 */
/**
 * All types in this file use camelCase to match the API responses.
 * The Python backend uses Pydantic with alias_generator=to_camel, so:
 * - Python field: job_id
 * - JSON field: jobId
 * - TypeScript field: jobId (matches JSON directly, no conversion needed)
 */

export interface AnalysisRequest {
  mode: 'all' | 'movies' | 'series'
  monthThreshold: number        // Items not watched in N months are cleanup candidates
  addedThreshold: number        // Never-watched items added within N months are "new" (not deleted)
}

export interface JobResponse {
  jobId: string
  status: 'queued' | 'running' | 'complete' | 'cancelled' | 'failed'
  progressPercent: number
  progressStep: string
  stepIndex: number
  totalSteps: number
  createdAt: string
  completedAt: string | null
  error: string | null
}

export interface MovieMatch {
  title: string
  jellyfinPath: string
  libraryPath: string | null
  matchMethod: string | null
  fuzzyScore: number | null
  sizeBytes: number
  isAmbiguous: boolean
  ambiguityReason: string | null
  added: string
  status: MediaStatus
}

export interface SeasonInfo {
  seasonNumber: number
  lastPlayed: string
  episodeCount: number
  totalEpisodes: number
  sizeBytes: number
  status: MediaStatus
  isUnwatched: boolean            // True for synthetic seasons with no watch history
}

export interface SeriesGroup {
  title: string
  libraryPath: string | null
  matchMethod: string | null
  fuzzyScore: number | null
  sizeBytes: number
  status: MediaStatus
  seasons: SeasonInfo[]
  collidingNames: string[]
}

export interface MediaSection {
  movies: MovieMatch[]
  series: SeriesGroup[]
}

/**
 * Counts and sizes for a single watch category (e.g., recently watched, never watched).
 * Both raw byte counts and formatted strings (e.g., "1.2 TB") are provided.
 */
export interface CategoryStats {
  movieCount: number
  showsCount: number
  seasonsCount: number
  totalSize: number            // bytes
  movieSize: number            // bytes
  seriesSize: number           // bytes: full series where ALL seasons are in this category
  seriesSizeGreedy: number     // bytes: sum of individual season sizes in this category
  totalSizeFmt: string         // formatted e.g. "1.2 TB"
  movieSizeFmt: string
  seriesSizeFmt: string
  seriesSizeGreedyFmt: string
}

/**
 * Counts for match quality across all categories.
 * Matched = successfully found in library. Ambiguous = multiple candidates close in score.
 * Unmatched = no library entry found. Collision = multiple Jellyfin entries map to one library item.
 */
export interface MatchingStats {
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

/**
 * Episode resolution stats. Used for monitoring matching quality.
 */
export interface EpisodeStats {
  skipped: number              // Jellyfin episodes with stale IDs (couldn't resolve)
  fallback: number             // Episodes resolved via ItemName parsing (not API call)
}

/**
 * Estimated disk space that could be saved by deleting old/unmatched media.
 */
export interface SpaceSavings {
  seasonsOnlySize: number      // bytes: old movies + old seasons
  entireShowsSize: number      // bytes: old movies + entire series where all seasons are old
  seasonsOnlySizeFmt: string
  entireShowsSizeFmt: string
}

/**
 * Aggregated statistics from a completed analysis.
 * Contains counts and sizes per watch category, matching quality, episode resolution, and savings estimate.
 * Used by SummaryPanel to display the overview table.
 */
export interface Summary {
  recent: CategoryStats        // Watched within threshold
  old: CategoryStats           // Not watched within threshold (cleanup candidate)
  neverWatched: CategoryStats  // Never watched (old)
  neverNew: CategoryStats      // Never watched (recently added)
  library: CategoryStats       // All items in library
  kept: CategoryStats          // Items tagged to keep
  matching: MatchingStats      // Match quality breakdown
  episodes: EpisodeStats       // Episode resolution quality
  spaceSavings: SpaceSavings   // Estimated cleanup savings
}

/**
 * Complete analysis result from a finished job.
 * Seven MediaSection categories (each with movies and series), plus summary stats.
 * Backend categorizes; frontend flattens allMovies/allSeries for unified table display.
 */
export interface AnalysisResult {
  recentlyWatched: MediaSection  // Watched within threshold (keep)
  notRecentlyWatched: MediaSection  // Not watched within threshold (cleanup candidate)
  keep: MediaSection              // Tagged to keep (don't delete)
  collision: MediaSection         // Multiple Jellyfin entries map to one library item (ambiguous)
  unmatched: MediaSection         // No matching library entry found (ambiguous)
  neverWatched: MediaSection      // Never watched (old; cleanup candidate)
  neverNew: MediaSection          // Never watched (recently added; keep)
  summary: Summary                // Aggregated statistics
}

export interface FullJobResponse extends JobResponse {
  result?: AnalysisResult
}

export type MediaStatus = 'recent' | 'old' | 'kept' | 'unmatched' | 'mixed' | 'never' | 'never_new' | 'collision'

export interface MovieRow extends MovieMatch {
  status: MediaStatus
}

export interface SeriesRow extends SeriesGroup {
  totalEpisodes: number
}

export interface FilterRequest {
  categories: string[]  // "old" | "never" | "never_new"
  greedy: boolean
}

export interface FilteredSummary {
  movieCount: number
  seriesCount: number
  seasonCount: number
  totalSize: number
  totalSizeFmt: string
  totalMovieCount: number
  totalSeriesCount: number
  totalSeasonCount: number
  totalLibrarySize: number
  totalLibrarySizeFmt: string
}

export interface FilteredResult {
  movies: MovieMatch[]
  series: SeriesGroup[]
  summary: FilteredSummary
}

export type WebSocketMessage =
  | { type: 'job_created'; job: JobResponse }
  | { type: 'job_progress'; jobId: string; step: string; percent: number; stepIndex: number; totalSteps: number }
  | { type: 'job_complete'; jobId: string }
  | { type: 'job_cancelled'; jobId: string }
  | { type: 'job_failed'; jobId: string; error: string }
