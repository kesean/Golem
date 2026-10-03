import { formatDate, trendWord } from './format'

type Point = { id: string; startedAt: number; value: number }

type Props = {
  title: string
  unitLabel: string // e.g. "out of 5"
  points: Point[] // oldest first
  domain: [number, number]
  ticks: number[]
  fmt: (v: number) => string
  color: string
  selectedId: string | null
  eps: number
}

const W = 640, H = 150, L = 40, R = 56, T = 12, B = 22

export function TrendChart({ title, unitLabel, points, domain, ticks, fmt, color, selectedId, eps }: Props) {
  const [lo, hi] = domain
  const x = (i: number) => (points.length < 2 ? (L + W - R) / 2 : L + (i * (W - L - R)) / (points.length - 1))
  const y = (v: number) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B)
  const last = points[points.length - 1]
  const first = points[0]
  const dir = trendWord(first.value, last.value, eps)
  const dirText = dir === 'flat' ? 'flat' : dir
  const label =
    `${title}: latest ${fmt(last.value)} ${unitLabel}, trending ${dirText} ` +
    `from ${fmt(first.value)} over ${points.length} scheduled ${points.length === 1 ? 'run' : 'runs'}`
  const path = points.map((p, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)} ${y(p.value).toFixed(1)}`).join(' ')
  const arrow = dir === 'up' ? '▲' : dir === 'down' ? '▼' : '●'

  return (
    <figure className="ev-chart">
      <figcaption className="ev-chart-title">
        <span>{title}</span>
        <span className="ev-chart-latest">
          {fmt(last.value)} <span aria-hidden="true">{arrow}</span>
          <span className="ev-chart-dir"> {dirText}</span>
        </span>
      </figcaption>
      <svg viewBox={`0 0 ${W} ${H}`} role="img" aria-label={label} className="ev-svg">
        {ticks.map(t => (
          <g key={t}>
            <line x1={L} x2={W - R} y1={y(t)} y2={y(t)} className="ev-grid" />
            <text x={L - 8} y={y(t) + 4} textAnchor="end" className="ev-axis">{fmt(t)}</text>
          </g>
        ))}
        <text x={L} y={H - 4} className="ev-axis">{formatDate(first.startedAt)}</text>
        <text x={W - R} y={H - 4} textAnchor="end" className="ev-axis">{formatDate(last.startedAt)}</text>
        <path d={path} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
        {points.map((p, i) => (
          <circle
            key={p.id}
            cx={x(i)}
            cy={y(p.value)}
            r={p.id === selectedId ? 5 : 4}
            fill={p.id === selectedId ? color : 'var(--bg-card)'}
            stroke={color}
            strokeWidth={2}
          />
        ))}
      </svg>
      <table className="ev-sr-only">
        <caption>{title} by run</caption>
        <thead><tr><th scope="col">Run date</th><th scope="col">{title}</th></tr></thead>
        <tbody>
          {points.map(p => (
            <tr key={p.id}><th scope="row">{formatDate(p.startedAt)}</th><td>{fmt(p.value)}</td></tr>
          ))}
        </tbody>
      </table>
    </figure>
  )
}
