import type { AnalysisRequest, FullJobResponse, JobResponse } from '../types/api'

const BASE_URL = import.meta.env.VITE_API_URL || ''

async function request<T = void>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE_URL}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!res.ok) {
    throw new Error(`API error: ${res.status} ${res.statusText}`)
  }
  if (res.status === 204 || res.headers.get('content-length') === '0') {
    return undefined as T
  }
  return res.json()
}

export function useApi() {
  async function postAnalysis(req: AnalysisRequest): Promise<{ jobId: string }> {
    return request('/api/analysis', {
      method: 'POST',
      body: JSON.stringify(req),
    })
  }

  async function getJob(jobId: string): Promise<FullJobResponse> {
    return request(`/api/analysis/${jobId}`)
  }

  async function listJobs(): Promise<JobResponse[]> {
    return request('/api/analysis')
  }

  async function cancelJob(jobId: string): Promise<void> {
    await request(`/api/analysis/${jobId}`, { method: 'DELETE' })
  }

  async function getCurrentJob(): Promise<FullJobResponse | null> {
    try {
      return await request<FullJobResponse>('/api/analysis/current')
    } catch {
      return null  // 204 or error — no current job
    }
  }

  async function clearResults(): Promise<void> {
    await request('/api/analysis', { method: 'DELETE' })
  }

  return { postAnalysis, getJob, listJobs, cancelJob, getCurrentJob, clearResults }
}
