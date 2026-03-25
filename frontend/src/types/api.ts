export interface AnalysisRequest {
  mode: 'all' | 'movies' | 'series'
  monthThreshold: number
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
}

export interface SeasonInfo {
  seasonNumber: number
  lastPlayed: string
  episodeCount: number
  sizeBytes: number
}

export interface SeriesGroup {
  title: string
  libraryPath: string | null
  matchMethod: string | null
  fuzzyScore: number | null
  sizeBytes: number
  seasons: SeasonInfo[]
}

export interface MediaSection {
  movies: MovieMatch[]
  series: SeriesGroup[]
}

export interface AnalysisResult {
  recentlyWatched: MediaSection
  notRecentlyWatched: MediaSection
  keep: MediaSection
  unmatched: MediaSection
  neverWatched: MediaSection
  summary: Record<string, unknown>
}

export interface FullJobResponse extends JobResponse {
  result?: AnalysisResult
}

export type MediaStatus = 'recent' | 'old' | 'kept' | 'unmatched' | 'mixed' | 'never'

export interface MovieRow extends MovieMatch {
  status: MediaStatus
}

export interface SeriesRow extends SeriesGroup {
  status: MediaStatus
  totalEpisodes: number
}

export type WebSocketMessage =
  | { type: 'job_created'; job: JobResponse }
  | { type: 'job_progress'; jobId: string; step: string; percent: number; stepIndex: number; totalSteps: number }
  | { type: 'job_complete'; jobId: string }
  | { type: 'job_cancelled'; jobId: string }
  | { type: 'job_failed'; jobId: string; error: string }
