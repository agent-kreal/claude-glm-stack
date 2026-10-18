import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Quota } from '../types'

const payload = atom({ plugin: 'zai-quota-band', key: 'payload' } as const, null)
const minute = atom({ plugin: 'zai-quota-band', key: 'minute' } as const, 0)

// The script owns the key chain and a 5-minute cache (~/.cache/zai-quota.json);
// a cached run is ~0.15 s, so running it on every main-loop turn is free and
// the band never waits on the network. It ships two levels above this mod
// (claude-glm-stack/mod/zai-quota-band → claude-glm-stack/scripts/zai-quota.py);
// $.plugin.root keeps that working wherever the repo is cloned.
function scriptArgv(root: string): readonly string[] {
  return ['/usr/bin/python3', `${root}/../../scripts/zai-quota.py`, '--json']
}

function fmtTokens(n: number | null | undefined): string {
  if (n == null) return '?'
  if (n >= 1_000_000_000) {
    const v = n / 1_000_000_000
    return `${v < 100 ? v.toFixed(1) : Math.round(v)}b`
  }
  if (n >= 1_000_000) {
    const v = n / 1_000_000
    return `${v < 100 ? v.toFixed(1) : Math.round(v)}m`
  }
  if (n >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return String(n)
}

function fmtDur(sec: number): string {
  if (sec <= 0) return ''
  const h = Math.floor(sec / 3600)
  const m = Math.floor((sec % 3600) / 60)
  return `${h}h${String(m).padStart(2, '0')}m`
}

function hhmm(d: Date): string {
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

// Top-level so `$` may be passed to it (the sandbox only allows $ into
// functions declared at the top of this file, or imported from its own files).
async function refresh($: any, script: readonly string[]): Promise<void> {
  try {
    const { exitCode, stdout, stderr } = await $.process.run(script, { timeoutMs: 30_000 })
    if (exitCode === 0 && stdout.trim()) {
      await update($, payload, () => JSON.parse(stdout) as Quota)
    } else {
      // surface script failures in the band instead of hiding them
      await update($, payload, () => ({
        ts: new Date().toISOString(),
        error: `exit ${exitCode}: ${(stderr || 'no output').trim().slice(0, 120)}`,
      } as Quota))
    }
  } catch (e) {
    await update($, payload, () => ({
      ts: new Date().toISOString(),
      error: String(e).slice(0, 160),
    } as Quota))
  }
}

export const register: Register = on => {
  on('session.start', ($, e, next) => {
    void refresh($, scriptArgv($.plugin.root))
    // redraw once a minute so the ↻ countdown and the peak badge stay live
    $.clock.every(60_000, () => void update($, minute, m => m + 1))
    return next(e)
  })

  on('turn.start', ($, e, next) => {
    if (!e.agentId) void refresh($, scriptArgv($.plugin.root)) // main loop only; subagents keep the cache
    return next(e)
  })

  on('ui.render', { component: 'AbovePrompt' }, async ($, e, next) => {
    // Coexistence: let the rest of the band chain (other mods, the engine)
    // draw first, then stack our row on top. Answering without next() would
    // suppress every band plugin below this one.
    const beneath = await next(e)

    const q = await read($, payload)
    await read($, minute) // reading it ties the band to the minute tick
    if (e.props.hasSurvey) return beneath

    const { Box, Text } = $.ui.resolve(e)

    if (!q) {
      return (
        <Box flexDirection="column">
          <Text color="inactive">GLM …</Text>
          {beneath}
        </Box>
      )
    }

    if (q.error) {
      return (
        <Box flexDirection="column">
          <Text color="error">GLM ERR: {q.error}</Text>
          {beneath}
        </Box>
      )
    }

    const now = await $.clock.now()

    const isPeak = q.peak?.peak === true
    const pct = q.five_hour?.percentage ?? 0
    const pctColor = pct >= 80 ? 'error' : pct >= 50 ? 'warning' : 'success'
    const resetMs = q.five_hour?.next_reset_ms ?? 0

    let window: string | null = null
    let left: string | null = null
    if (resetMs > now) {
      const reset = new Date(resetMs)
      const start = new Date(resetMs - 5 * 3_600_000)
      window = `${hhmm(start)}-${hhmm(reset)}`
      left = fmtDur(Math.floor((resetMs - now) / 1000))
    }

    return (
      <Box flexDirection="column">
        <Box>
          <Text color={isPeak ? 'warning' : 'subtle'}>{isPeak ? 'x3' : 'x1'} · </Text>
          <Text color={pctColor}>5h:{pct}% </Text>
          {window && <Text color="subtle">[{window}]</Text>}
          {left && <Text color="subtle">[↻{left}] · </Text>}
          <Text>
            D:{fmtTokens(q.day?.tokens)} · W:{fmtTokens(q.week?.tokens)} · M:
            {fmtTokens(q.month?.tokens)}
          </Text>
          {q.mcp?.used ? (
            <Text color="subtle"> · MCP {q.mcp.used}/{q.mcp.limit ?? '?'}</Text>
          ) : null}
          {q.stale ? <Text color="inactive"> (stale)</Text> : null}
        </Box>
        {beneath}
      </Box>
    )
  })
}
