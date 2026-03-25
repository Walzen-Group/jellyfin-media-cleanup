export interface AnalysisRequest {
  mode: 'all' | 'movies' | 'series'
  monthThreshold: number
  addedThreshold: number
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

export interface CategoryStats {
  movieCount: number
  showsCount: number
  seasonsCount: number
  totalSize: number
  movieSize: number
  seriesSize: number
  totalSizeFmt: string
  movieSizeFmt: string
  seriesSizeFmt: string
}

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

export interface EpisodeStats {
  skipped: number
  fallback: number
}

export interface SpaceSavings {
  seasonsOnlySize: number
  entireShowsSize: number
  seasonsOnlySizeFmt: string
  entireShowsSizeFmt: string
}

export interface Summary {
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

export interface AnalysisResult {
  recentlyWatched: MediaSection
  notRecentlyWatched: MediaSection
  keep: MediaSection
  collision: MediaSection
  unmatched: MediaSection
  neverWatched: MediaSection
  neverNew: MediaSection
  summary: Summary
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

export type WebSocketMessage =
  | { type: 'job_created'; job: JobResponse }
  | { type: 'job_progress'; jobId: string; step: string; percent: number; stepIndex: number; totalSteps: number }
  | { type: 'job_complete'; jobId: string }
  | { type: 'job_cancelled'; jobId: string }
  | { type: 'job_failed'; jobId: string; error: string }
