import type { AnalysisRequest, FullJobResponse, JobResponse } from '../types/api'

const BASE_URL = import.meta.env.VITE_API_URL || ''

/**
 * Generic fetch wrapper. Handles 204 No Content responses (no current job).
 * Throws on non-2xx status. Returns parsed JSON on success or undefined for empty responses.
 */
async function request<T = void>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
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

  return { postAnalysis, getJob, listJobs, cancelJob, getCurrentJob, clearResults }
}
