import { useQuery } from 'convex/react'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'
import type { EvalRun, RunDetail } from './types'

const bypassAuth = import.meta.env.VITE_TEST_BYPASS_AUTH === 'true'

export type E2ESeed = { runs: EvalRun[]; details: Record<string, RunDetail> }

// E2E seam, mirroring useHistory.ts: in test-bypass builds only, Playwright seeds
// window.__GOLEM_E2E_EVALS__ and the viewer is treated as admin. Vite inlines the
// flag at build time, so production bundles drop this branch.
function seed(): E2ESeed {
  return (window as { __GOLEM_E2E_EVALS__?: E2ESeed }).__GOLEM_E2E_EVALS__ ?? { runs: [], details: {} }
}

/** undefined while loading. */
export function useIsAdmin(): boolean | undefined {
  const admin = useQuery(api.evals.amIAdmin, bypassAuth ? 'skip' : {})
  return bypassAuth ? true : admin
}

// Only call these once admin is confirmed: they pass 'skip' otherwise, so a
// non-admin never issues a data query.
export function useRuns(enabled: boolean, opts: { limit?: number; label?: 'scheduled' | 'manual' }): EvalRun[] | undefined {
  const live = useQuery(api.evals.listRuns, enabled && !bypassAuth ? opts : 'skip') as EvalRun[] | undefined
  if (!bypassAuth) return live
  if (!enabled) return undefined
  const rows = seed().runs.filter(r => !opts.label || r.label === opts.label)
  return opts.limit ? rows.slice(0, opts.limit) : rows
}

export function useRunDetail(enabled: boolean, runId: string | null): RunDetail | undefined {
  const live = useQuery(
    api.evals.getRun,
    enabled && !bypassAuth && runId ? { runId: runId as Id<'evalRuns'> } : 'skip',
  ) as RunDetail | undefined
  if (!bypassAuth) return live
  return runId ? seed().details[runId] : undefined
}
