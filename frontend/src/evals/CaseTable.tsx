import { Fragment, useState } from 'react'
import { caseDelta, caseScore, formatDelta } from './format'
import { RULE_NAMES, type EvalResult } from './types'

type Props = { results: EvalResult[]; previous: EvalResult[] | null }

export function CaseTable({ results, previous }: Props) {
  const [open, setOpen] = useState<Set<string>>(new Set())
  const toggle = (id: string) =>
    setOpen(s => {
      const n = new Set(s)
      if (n.has(id)) n.delete(id)
      else n.add(id)
      return n
    })
  const prevBy = new Map((previous ?? []).map(r => [r.caseId, r]))

  return (
    <div className="ev-scroll" role="region" aria-label="Cases, scrollable" tabIndex={0}>
      <table className="ev-table" aria-label="Cases">
        <thead>
          <tr>
            <th scope="col">Case</th>
            <th scope="col" className="ev-num">Score</th>
            <th scope="col">Change from previous</th>
            <th scope="col">Rules passed</th>
          </tr>
        </thead>
        <tbody>
          {results.map(r => {
            const score = caseScore(r)
            const delta = caseDelta(r, prevBy.get(r.caseId))
            const passed = RULE_NAMES.filter(n => r.rules[n]).length
            const isOpen = open.has(r.caseId)
            const panelId = `case-${r.caseId}`
            return (
              <Fragment key={r._id}>
                <tr>
                  <th scope="row">
                    <button
                      type="button"
                      className="ev-link"
                      aria-expanded={isOpen}
                      aria-controls={panelId}
                      onClick={() => toggle(r.caseId)}
                    >
                      <span aria-hidden="true">{isOpen ? '▾' : '▸'} </span>
                      {r.caseId}
                    </button>
                  </th>
                  <td className="ev-num">{score === null ? (r.error ? 'error' : 'ungraded') : score.toFixed(1)}</td>
                  <td>{previous ? formatDelta(delta.score) : 'no baseline'}</td>
                  <td>{passed} of {RULE_NAMES.length}</td>
                </tr>
                {isOpen && (
                  <tr id={panelId} className="ev-detail-row">
                    <td colSpan={4}>
                      <div className="ev-detail">
                        <h3>Question</h3>
                        <p>{r.question}</p>
                        <h3>Answer</h3>
                        <pre className="ev-answer">{r.response || '(no answer)'}</pre>
                        {r.error && (<><h3>Error</h3><p>{r.error}</p></>)}
                        <h3>Rules</h3>
                        <ul className="ev-rules">
                          {RULE_NAMES.map(n => (
                            <li key={n}>{r.rules[n] ? '✓' : '✗'} {n}: {r.rules[n] ? 'pass' : 'fail'}</li>
                          ))}
                        </ul>
                        <h3>Grader's reason</h3>
                        {r.judge ? (
                          <>
                            <p>Groundedness {r.judge.groundedness}/5, coverage {r.judge.coverage}/5.</p>
                            <p>{r.judge.reason}</p>
                            <h3>Missed key points</h3>
                            {r.judge.keyPointsMissed.length ? (
                              <ul>{r.judge.keyPointsMissed.map(k => <li key={k}>{k}</li>)}</ul>
                            ) : (
                              <p>None.</p>
                            )}
                          </>
                        ) : (
                          <p>{r.judgeError ? `Not graded: ${r.judgeError}` : 'Not graded.'}</p>
                        )}
                        <h3>Change from previous run</h3>
                        {!previous || !prevBy.has(r.caseId) ? (
                          <p>No baseline for this case.</p>
                        ) : (
                          <>
                            <p>Score: {formatDelta(delta.score)}</p>
                            {delta.ruleChanges.length ? (
                              <ul>
                                {delta.ruleChanges.map(c => (
                                  <li key={c.rule}>
                                    {c.rule}: {c.from ? 'pass' : 'fail'} → {c.to ? 'pass' : 'fail'}
                                  </li>
                                ))}
                              </ul>
                            ) : (
                              <p>Rules unchanged.</p>
                            )}
                          </>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
