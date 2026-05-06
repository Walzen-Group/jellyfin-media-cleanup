import type {
  AnalysisRequest, FilterRequest, FilteredResult, FullJobResponse, JobResponse, RunPlan,
  CleanupExecuteRequest, CleanupJobResponse, CleanupReport, HistoryPage, WizardState,
} from '../types/api'
import { useAuth } from './useAuth'

const BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Generic fetch wrapper. Handles 204 No Content responses (no current job).
 * Throws on non-2xx status. Returns parsed JSON on success or undefined for empty responses.
 * Automatically attaches OIDC Bearer token when available.
 */
async function request<T = void>(path: string, options?: RequestInit): Promise<T> {
  const { getAccessToken } = useAuth()
  const token = getAccessToken()
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string>),
  }
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${BASE_URL}${path}`, {
    ...options,
    headers,
  })
  // 401 means the token is expired or invalid on the backend.
  // Clear local session state (without redirecting to the OIDC provider, which
  // may loop if the provider session is also dead) so the login screen appears.
  if (res.status === 401) {
    const { clearSession } = useAuth()
    await clearSession()
    throw new Error('Authentication expired. Please log in again.')
  }
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  // Handle 204 No Content (e.g. GET /api/analysis/current when no jobs exist)
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }
  return res.json()
}

export function useApi() {
  /**
   * Submit a new analysis job. Returns immediately with 202 Accepted and a jobId.
   * The job status can be polled or monitored via WebSocket.
   */
  async function postAnalysis(req: AnalysisRequest): Promise<{ jobId: string }> {
    return request('/api/analysis', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  /**
   * Fetch full job details by ID. When complete, includes the AnalysisResult.
   */
  async function getJob(jobId: string): Promise<FullJobResponse> {
    return request(`/api/analysis/${jobId}`)
  }

  /**
   * List all jobs (recent first). Does not include results to avoid large responses.
   */
  async function listJobs(): Promise<JobResponse[]> {
    return request('/api/analysis')
  }

  /**
   * Cancel a queued or running job. No-op if already completed/failed.
   */
  async function cancelJob(jobId: string): Promise<void> {
    await request(`/api/analysis/${jobId}`, { method: 'DELETE' })
  }

  /**
   * Get the active job (running/queued) or most recent completed result.
   * Returns null if no jobs exist or request fails (e.g., 204 No Content).
   */
  async function getCurrentJob(): Promise<FullJobResponse | null> {
    try {
      return await request<FullJobResponse>('/api/analysis/current')
    } catch {
      return null  // No current job (204) or network error
    }
  }

  /**
   * Clear all completed/failed jobs from memory. Keeps running/queued jobs.
   */
  async function clearResults(): Promise<void> {
    await request('/api/analysis', { method: 'DELETE' })
  }

  /**
   * Filter a completed analysis by categories and greedy mode.
   * Returns a flat list of movies/series that match the selected categories.
   */
  async function filterAnalysis(jobId: string, req: FilterRequest): Promise<FilteredResult> {
    return request(`/api/analysis/${jobId}/filter`, {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  /**
   * Build a dry-run deletion plan from a filtered analysis result.
   * Returns which Radarr movies and Sonarr series/seasons would be deleted.
   */
  async function prepareRunPlan(jobId: string, req: FilterRequest): Promise<RunPlan> {
    return request(`/api/analysis/${jobId}/prepare`, {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  /**
   * Execute a cleanup job for a given analysis job ID. simulate=true = dry run.
   */
  async function executeCleanup(req: CleanupExecuteRequest): Promise<CleanupJobResponse> {
    return request('/api/cleanup/execute', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  /**
   * Get the currently active cleanup job, or null if none (204).
   */
  async function getCleanupCurrent(): Promise<CleanupJobResponse | null> {
    try {
      return await request<CleanupJobResponse>('/api/cleanup/current')
    } catch {
      return null
    }
  }

  /**
   * Get a specific cleanup job by ID.
   */
  async function getCleanupJob(id: string): Promise<CleanupJobResponse> {
    return request(`/api/cleanup/jobs/${id}`)
  }

  /**
   * Cancel a running cleanup job.
   */
  async function cancelCleanupJob(id: string): Promise<void> {
    await request(`/api/cleanup/jobs/${id}/cancel`, { method: 'POST' })
  }

  /**
   * Fetch a paginated page of deletion history entries.
   * q: optional case-insensitive title substring filter (omit or empty = no filter).
   * Backend strips empty strings to None, so omitting and passing "" are equivalent.
   * limit: page size (1-500, default 50). offset: zero-based row offset (default 0).
   */
  async function getCleanupHistory(limit = 50, offset = 0, q = ''): Promise<HistoryPage> {
    const params = new URLSearchParams()
    params.set('limit', String(limit))
    params.set('offset', String(offset))
    // Only send q when non-empty - backend accepts empty string too, but omitting is cleaner
    if (q.trim()) params.set('q', q.trim())
    return request(`/api/cleanup/history?${params.toString()}`)
  }

  /**
   * Check if any deletion history data exists (for the indicator in AnalysisControls).
   */
  async function getCleanupHistoryHasData(): Promise<{ hasData: boolean }> {
    return request('/api/cleanup/history/has-data')
  }

  /**
   * Delete a single history entry by DB id.
   */
  async function deleteHistoryEntry(id: number): Promise<void> {
    await request(`/api/cleanup/history/${id}`, { method: 'DELETE' })
  }

  /**
   * Clear all history entries.
   */
  async function clearCleanupHistory(): Promise<void> {
    await request('/api/cleanup/history', { method: 'DELETE' })
  }

  /**
   * Fetch the full cleanup report for a job.
   */
  async function getCleanupReport(jobId: string): Promise<CleanupReport> {
    return request(`/api/cleanup/report/${jobId}`)
  }

  /**
   * Fetch the YAML cleanup report as a Blob for programmatic download.
   * Uses the same auth-bearing request wrapper so the Authorization header
   * is attached - unlike window.location.href which cannot carry custom headers.
   * Throws with a user-readable message on 401/non-2xx so callers can surface the error.
   */
  async function fetchCleanupReportBlob(jobId: string): Promise<Blob> {
    const { getAccessToken } = useAuth()
    const token = getAccessToken()
    const headers: Record<string, string> = {
      'Accept': 'application/x-yaml, text/yaml, */*',
    }
    if (token) {
      headers['Authorization'] = `Bearer ${token}`
    }
    const res = await fetch(`${BASE_URL}/api/cleanup/report/${jobId}/download`, { headers })
    if (res.status === 401) {
      const { clearSession } = useAuth()
      await clearSession()
      throw new Error('Authentication expired. Please log in again.')
    }
    if (!res.ok) {
      throw new Error(`Download failed: ${res.status} ${res.statusText}`)
    }
    return res.blob()
  }

  /**
   * Fetch the current wizard state from the backend.
   * Returns null if no state exists yet or the request fails.
   */
  async function getWizardState(): Promise<WizardState | null> {
    try {
      return await request<WizardState>('/api/wizard')
    } catch {
      return null
    }
  }

  /**
   * Partially update the wizard state on the backend.
   * Merges the given fields into the existing state and returns the updated state.
   */
  async function updateWizardState(update: Partial<WizardState>): Promise<WizardState> {
    return request('/api/wizard', {
      method: 'PATCH',
      body: JSON.stringify(update),
    })
  }

  return {
    postAnalysis, getJob, listJobs, cancelJob, getCurrentJob, clearResults, filterAnalysis, prepareRunPlan,
    executeCleanup, getCleanupCurrent, getCleanupJob, cancelCleanupJob,
    getCleanupHistory, getCleanupHistoryHasData, deleteHistoryEntry, clearCleanupHistory,
    getCleanupReport, fetchCleanupReportBlob,
    getWizardState, updateWizardState,
  }
}
