/**
 * pageCache.ts
 * A tiny in-memory cache for API responses.
 * When a page re-mounts, it shows last known data instantly
 * while the fresh API call runs in the background.
 */

const cache: Record<string, { data: unknown; ts: number }> = {}
const TTL_MS = 0 // 0 minutes (disabled caching for testing)

export function getCached<T>(key: string): T | null {
  const entry = cache[key]
  if (!entry) return null
  if (Date.now() - entry.ts > TTL_MS) return null
  return entry.data as T
}

export function setCached(key: string, data: unknown) {
  cache[key] = { data, ts: Date.now() }
}
