import React from 'react'
import { Textarea } from './ui/textarea'
import { Button } from './ui/button'

type QuestionInputProps = {
  value: string
  onChange: (value: string) => void
  onSubmit: () => void
  isLoading: boolean
  /** Empty state: show the large heading. Once there is an answer it shrinks to a small label. */
  hero?: boolean
}

export function QuestionInput({ value, onChange, onSubmit, isLoading, hero = false }: QuestionInputProps) {
  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
      e.preventDefault()
      if (!isLoading && value.trim()) onSubmit()
    }
  }

  return (
    <div style={{ padding: hero ? '48px 24px 0' : '24px 24px 0', display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <label htmlFor="question" className={hero ? 'q-hero' : 'q-label'}>
        What’s broken?
      </label>
      {hero && (
        <p className="q-hero-sub">
          Describe an auth, CORS, streaming or rate-limit problem. Answers are grounded in Clerk and MDN docs.
        </p>
      )}

      <Textarea
        id="question"
        value={value}
        onChange={e => onChange(e.target.value)}
        onKeyDown={handleKeyDown}
        placeholder="Paste an error message or describe what you see…"
        disabled={isLoading}
        rows={4}
        style={{
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: '13px',
          resize: 'vertical',
          backgroundColor: 'var(--bg-card)',
          borderColor: 'var(--border-color)',
          color: 'var(--text-primary)',
        }}
      />

      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span
          style={{
            fontFamily: "'DM Sans', sans-serif",
            fontSize: '11px',
            color: 'var(--text-muted)',
          }}
        >
          Ctrl + Enter to submit
        </span>
        <Button
          id="ask-btn"
          onClick={onSubmit}
          disabled={isLoading || !value.trim()}
          style={{
            backgroundColor: 'var(--accent)',
            color: 'var(--btn-text)',
            fontFamily: "'DM Sans', sans-serif",
          }}
        >
          {isLoading ? 'Thinking…' : 'Ask'}
        </Button>
      </div>
    </div>
  )
}
