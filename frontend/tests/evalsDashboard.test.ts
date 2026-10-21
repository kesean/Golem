import { createElement } from 'react'
import { cleanup, render, screen, within, fireEvent } from '@testing-library/react'
import { afterEach, beforeEach, describe, it, expect, vi } from 'vitest'

const queryMock = vi.fn()
vi.mock('convex/react', () => ({
  useQuery: (ref: string, args: unknown) => queryMock(ref, args),
}))
vi.mock('../convex/_generated/api', () => ({
  api: { evals: { amIAdmin: 'amIAdmin', listRuns: 'listRuns', getRun: 'getRun' } },
}))

import { EvalsApp } from '../src/evals/EvalsApp'
import { caseScore, caseDelta } from '../src/evals/format'

const rules = { completed: true, format: true, productTag: true, citations: true, retrieval: true }
const rate = { completed: 1, format: 1, productTag: 1, citations: 1, retrieval: 0.8 }
const summary = (meanScore: number) => ({
  caseCount: 1, gradedCount: 1, errorCount: 0, meanGroundedness: meanScore, meanCoverage: meanScore,
  meanScore, rulePassRate: rate, p50LatencyMs: 1, p95LatencyMs: 2, totalInputTokens: 1, totalOutputTokens: 1,
})
const mkRun = (id: string, startedAt: number, meanScore: number, regressions: unknown[] = []) => ({
  _id: id, _creationTime: startedAt, label: 'scheduled', gitSha: 'abc1234def', gitRef: 'main',
  appModel: 'm', judgeModel: 'j', casesVersion: 1, startedAt, finishedAt: startedAt + 1,
  status: 'completed', summary: summary(meanScore), regressions,
})
const mkResult = (runId: string, g: number, c: number, over: Record<string, unknown> = {}) => ({
  _id: `${runId}-r`, runId, caseId: 'clerk-401', question: 'Why 401?', response: 'Because the token expired.',
  retrievedUrls: [], rules, judge: { groundedness: g, coverage: c, keyPointsMissed: ['rotate the key'], reason: 'Mostly grounded.' },
  latencyMs: 1, inputTokens: 1, outputTokens: 1, ...over,
})

const runs = [mkRun('r2', Date.UTC(2026, 8, 20), 3.5, [{ kind: 'caseScoreDrop', caseId: 'clerk-401', baseline: 4.5, current: 3.5 }]),
  mkRun('r1', Date.UTC(2026, 8, 13), 4.5)]

function wireDetails(runList: unknown[]) {
  queryMock.mockImplementation((ref: string, args: unknown) => {
    if (ref === 'amIAdmin') return true
    if (args === 'skip') return undefined
    if (ref === 'listRuns') return runList
    if (ref === 'getRun') {
      const id = (args as { runId: string }).runId
      const run = (runList as { _id: string }[]).find(r => r._id === id)
      return { run, results: [mkResult(id, 3, 4, { caseId: `case-of-${id}` })], previous: null }
    }
  })
}

function wire(admin: boolean | undefined, runList: unknown[] | undefined = runs) {
  queryMock.mockImplementation((ref: string, args: unknown) => {
    if (ref === 'amIAdmin') return admin
    if (args === 'skip') return undefined
    if (ref === 'listRuns') return runList
    if (ref === 'getRun') {
      return {
        run: runs[0],
        results: [mkResult('r2', 3, 4, { rules: { ...rules, citations: false } })],
        previous: { run: runs[1], results: [mkResult('r1', 4, 5)] },
      }
    }
  })
}

beforeEach(() => queryMock.mockReset())
afterEach(cleanup)

describe('EvalsApp', () => {
  it('shows no-access and makes no data queries for non-admins', () => {
    wire(false)
    render(createElement(EvalsApp))
    expect(screen.getByText("You don't have access to evals.")).toBeTruthy()
    const dataCalls = queryMock.mock.calls.filter(([ref, args]) => ref !== 'amIAdmin' && args !== 'skip')
    expect(dataCalls).toEqual([])
  })

  it('renders trend and run list for admins', () => {
    wire(true)
    render(createElement(EvalsApp))
    const imgs = screen.getAllByRole('img')
    expect(imgs.some(i => /latest 3\.5/.test(i.getAttribute('aria-label') ?? '') && /down/.test(i.getAttribute('aria-label') ?? ''))).toBe(true)
    const list = screen.getByRole('table', { name: 'Eval runs' })
    expect(within(list).getAllByRole('row')).toHaveLength(3) // header + 2 runs
    expect(within(list).getByText('1 regression')).toBeTruthy()
  })

  it('expands a case with keyboard-accessible button and shows delta from previous', () => {
    wire(true)
    render(createElement(EvalsApp))
    const btn = screen.getByRole('button', { name: /clerk-401/ })
    expect(btn.getAttribute('aria-expanded')).toBe('false')
    fireEvent.click(btn)
    expect(btn.getAttribute('aria-expanded')).toBe('true')
    expect(screen.getByText('Because the token expired.')).toBeTruthy()
    expect(screen.getByText('Mostly grounded.')).toBeTruthy()
    expect(screen.getByText('rotate the key')).toBeTruthy()
    expect(screen.getAllByText(/-1\.0|−1\.0/).length).toBeGreaterThan(0)
    expect(screen.getByText(/citations: pass → fail/)).toBeTruthy()
  })

  it('shows the empty state when there are no runs', () => {
    wire(true, [])
    render(createElement(EvalsApp))
    expect(screen.getByText(/No eval runs yet\./)).toBeTruthy()
    expect(screen.getByText('make eval')).toBeTruthy()
  })
})

describe('trend and selection', () => {
  afterEach(() => window.history.pushState({}, '', '/'))

  it('leaves errored runs out of the trend but keeps them in the run list', () => {
    const errored = { ...mkRun('r3', Date.UTC(2026, 8, 27), 0), status: 'errored' }
    wireDetails([errored, ...runs])
    render(createElement(EvalsApp))
    const labels = screen.getAllByRole('img').map(i => i.getAttribute('aria-label') ?? '')
    expect(labels.some(l => /latest 3\.5/.test(l))).toBe(true)
    expect(labels.some(l => /latest 0/.test(l))).toBe(false)
    const list = screen.getByRole('table', { name: 'Eval runs' })
    expect(within(list).getAllByRole('row')).toHaveLength(4)
    expect(within(list).getByText('scheduled (errored)')).toBeTruthy()
  })

  it('selects the run named by ?run= when it exists', () => {
    window.history.pushState({}, '', '/?run=r1')
    wireDetails(runs)
    render(createElement(EvalsApp))
    expect(screen.getByRole('button', { name: /case-of-r1/ })).toBeTruthy()
  })

  it('falls back to the newest run when ?run= is unknown', () => {
    window.history.pushState({}, '', '/?run=nope')
    wireDetails(runs)
    render(createElement(EvalsApp))
    expect(screen.getByRole('button', { name: /case-of-r2/ })).toBeTruthy()
  })

  it('clicking a run row selects it and updates the case table', () => {
    wireDetails(runs)
    render(createElement(EvalsApp))
    expect(screen.getByRole('button', { name: /case-of-r2/ })).toBeTruthy()
    const list = screen.getByRole('table', { name: 'Eval runs' })
    const buttons = within(list).getAllByRole('button')
    expect(buttons[0].getAttribute('aria-pressed')).toBe('true')
    fireEvent.click(buttons[1])
    expect(buttons[1].getAttribute('aria-pressed')).toBe('true')
    expect(screen.getByRole('button', { name: /case-of-r1/ })).toBeTruthy()
    expect(screen.queryByRole('button', { name: /case-of-r2/ })).toBeNull()
  })

  it('sets aria-controls on a case button only while its row is open', () => {
    wire(true)
    render(createElement(EvalsApp))
    const btn = screen.getByRole('button', { name: /clerk-401/ })
    expect(btn.hasAttribute('aria-controls')).toBe(false)
    fireEvent.click(btn)
    const id = btn.getAttribute('aria-controls')
    expect(id).toBeTruthy()
    expect(document.getElementById(id as string)).toBeTruthy()
  })
})

describe('ungraded delta text', () => {
  it('says "not graded" when a previous case exists but is ungraded, "no baseline" when absent', () => {
    queryMock.mockImplementation((ref: string, args: unknown) => {
      if (ref === 'amIAdmin') return true
      if (args === 'skip') return undefined
      if (ref === 'listRuns') return runs
      if (ref === 'getRun') {
        return {
          run: runs[0],
          results: [mkResult('r2', 3, 4), mkResult('r2', 3, 4, { _id: 'b', caseId: 'other' })],
          previous: { run: runs[1], results: [mkResult('r1', 3, 4, { judge: undefined })] },
        }
      }
    })
    render(createElement(EvalsApp))
    expect(screen.getByText('not graded')).toBeTruthy()
    expect(screen.getByText('no baseline')).toBeTruthy()
  })
})

describe('format', () => {
  it('computes case score and delta', () => {
    expect(caseScore(mkResult('x', 3, 4) as never)).toBe(3.5)
    const d = caseDelta(mkResult('x', 3, 4, { rules: { ...rules, format: false } }) as never, mkResult('y', 4, 5) as never)
    expect(d.score).toBe(-1)
    expect(d.ruleChanges).toEqual([{ rule: 'format', from: true, to: false }])
    expect(caseDelta(mkResult('x', 3, 4) as never, undefined).score).toBeNull()
  })
})
