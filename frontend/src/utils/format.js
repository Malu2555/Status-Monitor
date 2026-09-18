// Time/format helpers for display.

export function timeAgo(iso) {
  // "3m ago" style relative time; 'never' when nothing was recorded yet.
  if (!iso) return 'never'
  const seconds = Math.floor((Date.now() - new Date(iso).getTime()) / 1000)
  if (seconds < 0) return 'just now'
  if (seconds < 60) return `${seconds}s ago`
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  return `${days}d ago`
}

export function formatMs(ms) {
  // Response latency; — when unknown.
  return ms == null ? '—' : `${ms} ms`
}

export function formatUptime(value) {
  // Uptime percentage; — when no data yet.
  return value == null ? '—' : `${value}%`
}

export function statusLabel(status) {
  // Human name for the API's status value.
  return { up: 'Operational', down: 'Down', unknown: 'Pending' }[status] ?? 'Unknown'
}
