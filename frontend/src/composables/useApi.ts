import type {
  AnalysisRequest, FilterRequest, FilteredResult, FullJobResponse, JobResponse, RunPlan,
  CleanupExecuteRequest, CleanupJobResponse, CleanupReport, HistoryEntry,
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
   * Fetch all deletion history entries.
   */
  async function getCleanupHistory(): Promise<HistoryEntry[]> {
    return request('/api/cleanup/history')
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
   * Returns the URL for downloading the YAML report. Navigate directly.
   */
  function getCleanupReportDownloadUrl(jobId: string): string {
    return `${BASE_URL}/api/cleanup/report/${jobId}/download`
  }

  return {
    postAnalysis, getJob, listJobs, cancelJob, getCurrentJob, clearResults, filterAnalysis, prepareRunPlan,
    executeCleanup, getCleanupCurrent, getCleanupJob, cancelCleanupJob,
    getCleanupHistory, getCleanupHistoryHasData, deleteHistoryEntry, clearCleanupHistory,
    getCleanupReport, getCleanupReportDownloadUrl,
  }
}
