import { RULE_NAMES, type EvalResult, type EvalRun, type RuleName } from './types'

export function caseScore(r: EvalResult): number | null {
  return r.judge ? (r.judge.groundedness + r.judge.coverage) / 2 : null
}

export type CaseDelta = {
  score: number | null
  ruleChanges: { rule: RuleName; from: boolean; to: boolean }[]
}

export function caseDelta(current: EvalResult, previous: EvalResult | undefined): CaseDelta {
  if (!previous) return { score: null, ruleChanges: [] }
  const a = caseScore(current)
  const b = caseScore(previous)
  return {
    score: a !== null && b !== null ? a - b : null,
    ruleChanges: RULE_NAMES.filter(n => current.rules[n] !== previous.rules[n]).map(n => ({
      rule: n,
      from: previous.rules[n],
      to: current.rules[n],
    })),
  }
}

export function formatDelta(d: number | null): string {
  if (d === null) return 'not graded'
  if (Math.abs(d) < 0.05) return '● no change'
  return `${d > 0 ? '▲ +' : '▼ −'}${Math.abs(d).toFixed(1)}`
}

export function overallPassRate(run: EvalRun): number {
  const v = Object.values(run.summary.rulePassRate)
  return v.reduce((s, x) => s + x, 0) / (v.length || 1)
}

export const pct = (x: number) => `${Math.round(x * 100)}%`

export const formatDate = (ms: number) =>
  new Date(ms).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric', timeZone: 'UTC' })

export function trendWord(first: number, last: number, eps: number): 'up' | 'down' | 'flat' {
  if (last - first > eps) return 'up'
  if (first - last > eps) return 'down'
  return 'flat'
}
