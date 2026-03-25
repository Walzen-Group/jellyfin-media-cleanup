/**
 * Convert bytes to human-readable format (B, KB, MB, GB, TB).
 * Uses base-1024 (binary) sizing. Always shows one decimal place.
 */
export function formatSize(bytes: number): string {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(1024))
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`
}

/**
 * Format an ISO 8601 timestamp to the user's local date format.
 */
export function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString()
}
