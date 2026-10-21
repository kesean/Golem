import { useState } from 'react'
import { useTheme } from '../hooks/useTheme'
import { useIsAdmin, useRuns, useRunDetail } from './useEvalsData'
import { TrendChart } from './TrendChart'
import { RunList } from './RunList'
import { CaseTable } from './CaseTable'
import { formatDate, overallPassRate, pct } from './format'
import './evals.css'

export function EvalsApp() {
  const { theme, toggle } = useTheme()
  const admin = useIsAdmin()
  const ok = admin === true
  const scheduled = useRuns(ok, { limit: 26, label: 'scheduled' })
  const all = useRuns(ok, { limit: 60 })
  const [picked, setPicked] = useState<string | null>(null)
  const linked = new URLSearchParams(window.location.search).get('run')
  const linkedId = linked && all?.some(r => r._id === linked) ? linked : null
  const selectedId = picked ?? linkedId ?? all?.[0]?._id ?? null
  const detail = useRunDetail(ok, selectedId)

  let body
  if (admin === undefined) {
    body = <p className="ev-note" role="status">Loading…</p>
  } else if (!admin) {
    body = <p className="ev-note">You don't have access to evals.</p>
  } else if (all === undefined || scheduled === undefined) {
    body = <p className="ev-note" role="status">Loading…</p>
  } else if (all.length === 0) {
    body = <p className="ev-note">No eval runs yet. Run <code>make eval</code>.</p>
  } else {
    // Errored runs have no scores (meanScore 0), so keep them out of the [1,5] trend
    const trend = scheduled.filter(r => r.status === 'completed').reverse()
    body = (
      <>
        <section aria-labelledby="ev-trend-h">
          <h2 id="ev-trend-h">Trend</h2>
          {trend.length === 0 ? (
            <p className="ev-note">No scheduled runs yet, so there is no trend to chart.</p>
          ) : (
            <div className="ev-charts">
              <TrendChart
                title="Mean judge score"
                unitLabel="out of 5"
                points={trend.map(r => ({ id: r._id, startedAt: r.startedAt, value: r.summary.meanScore }))}
                domain={[1, 5]}
                ticks={[1, 3, 5]}
                fmt={v => v.toFixed(1)}
                color="var(--accent)"
                selectedId={selectedId}
                eps={0.05}
              />
              <TrendChart
                title="Rule pass rate"
                unitLabel="of rule checks passed"
                points={trend.map(r => ({ id: r._id, startedAt: r.startedAt, value: overallPassRate(r) }))}
                domain={[0, 1]}
                ticks={[0, 0.5, 1]}
                fmt={pct}
                color="var(--col-root)"
                selectedId={selectedId}
                eps={0.005}
              />
            </div>
          )}
        </section>
        <section aria-labelledby="ev-runs-h">
          <h2 id="ev-runs-h">Runs</h2>
          <RunList runs={all} selectedId={selectedId} onSelect={setPicked} />
        </section>
        <section aria-labelledby="ev-cases-h">
          <h2 id="ev-cases-h">
            Cases{detail ? `, ${formatDate(detail.run.startedAt)} (${detail.run.label})` : ''}
          </h2>
          {detail ? (
            <CaseTable results={detail.results} previous={detail.previous?.results ?? null} />
          ) : (
            <p className="ev-note" role="status">Loading…</p>
          )}
        </section>
      </>
    )
  }

  return (
    <div className="ev-page">
      <header className="ev-header">
        <h1>Evals</h1>
        <button type="button" className="ev-btn" onClick={toggle}>
          {theme === 'light' ? 'Dark theme' : 'Light theme'}
        </button>
      </header>
      <main>{body}</main>
    </div>
  )
}
