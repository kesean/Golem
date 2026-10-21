import { formatDate, overallPassRate, pct } from './format'
import type { EvalRun } from './types'

type Props = { runs: EvalRun[]; selectedId: string | null; onSelect: (id: string) => void }

export function RunList({ runs, selectedId, onSelect }: Props) {
  return (
    <div className="ev-scroll" role="region" aria-label="Eval runs, scrollable" tabIndex={0}>
      <table className="ev-table" aria-label="Eval runs">
        <thead>
          <tr>
            <th scope="col">Date</th>
            <th scope="col">Label</th>
            <th scope="col">Git SHA</th>
            <th scope="col" className="ev-num">Mean score</th>
            <th scope="col" className="ev-num">Pass rate</th>
            <th scope="col">Regressions</th>
          </tr>
        </thead>
        <tbody>
          {runs.map(r => {
            const n = r.regressions.length
            const sel = r._id === selectedId
            return (
              <tr key={r._id} className={sel ? 'ev-selected' : undefined}>
                <th scope="row">
                  <button type="button" className="ev-link" aria-pressed={sel} onClick={() => onSelect(r._id)}>
                    {formatDate(r.startedAt)}
                  </button>
                </th>
                <td>{r.label}{r.status === 'errored' ? ' (errored)' : ''}</td>
                <td className="ev-mono">{r.gitSha.slice(0, 7)}</td>
                <td className="ev-num">{r.summary.meanScore.toFixed(2)}</td>
                <td className="ev-num">{pct(overallPassRate(r))}</td>
                <td>{n === 0 ? 'none' : `${n} ${n === 1 ? 'regression' : 'regressions'}`}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
