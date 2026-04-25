import React, { useState } from 'react'
import { useMutation } from 'convex/react'
import { api } from '../../convex/_generated/api'
import type { Id } from '../../convex/_generated/dataModel'

type FeedbackButtonsProps = {
  evalId: string | null
}

export function FeedbackButtons({ evalId }: FeedbackButtonsProps) {
  const [active, setActive] = useState<'up' | 'down' | null>(null)
  const setFeedback = useMutation(api.evals.setFeedback)

  async function handleFeedback(direction: 'up' | 'down') {
    const next = active === direction ? null : direction
    setActive(next)
    if (!evalId) return
    try {
      await setFeedback({
        evalId: evalId as Id<'evals'>,
        feedback: next ?? undefined,
      })
    } catch {}
  }

  const btnBase: React.CSSProperties = {
    border: '1px solid var(--border-color)',
    borderRadius: '6px',
    padding: '4px 10px',
    fontSize: '14px',
    cursor: 'pointer',
    background: 'none',
  }

  return (
    <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
      <span
        style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '12px',
          color: 'var(--text-muted)',
        }}
      >
        Was this helpful?
      </span>
      <button
        id="thumb-up-btn"
        className={active === 'up' ? 'active-up' : ''}
        onClick={() => handleFeedback('up')}
        aria-pressed={active === 'up'}
        aria-label="Helpful"
        style={{
          ...btnBase,
          background: active === 'up' ? 'var(--accent-subtle)' : 'none',
        }}
      >
        👍
      </button>
      <button
        id="thumb-down-btn"
        className={active === 'down' ? 'active-down' : ''}
        onClick={() => handleFeedback('down')}
        aria-pressed={active === 'down'}
        aria-label="Not helpful"
        style={{
          ...btnBase,
          background: active === 'down' ? '#fef2f2' : 'none',
        }}
      >
        👎
      </button>
    </div>
  )
}
