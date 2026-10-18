export type WindowUsage = { calls: number | null; tokens: number | null }

/** What scripts/zai-quota.py --json prints (its cache payload, plus `stale`). */
export type Quota = {
  ts: string
  level?: string | null
  stale?: boolean
  error?: string
  five_hour?: { percentage?: number; next_reset_ms?: number | null }
  mcp?: {
    limit?: number
    used?: number
    remaining?: number
    tools?: Record<string, number>
    next_reset_ms?: number | null
  }
  day?: WindowUsage
  week?: WindowUsage
  month?: WindowUsage
  peak?: { peak: boolean; mult: string; changes_in_sec: number }
}

declare module 'claude-code' {
  interface PluginState {
    'zai-quota-band': { payload: Quota | null; minute: number }
  }
}
