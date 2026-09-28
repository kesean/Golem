import { DEMO_QUESTIONS } from '../lib/demoQuestions'

type SuggestedQuestionsProps = {
  onPick: (question: string) => void
}

export function SuggestedQuestions({ onPick }: SuggestedQuestionsProps) {
  return (
    <div style={{ padding: '16px 24px 0', display: 'flex', flexDirection: 'column', gap: '8px' }}>
      <span
        id="suggested-questions-label"
        style={{
          fontFamily: "'DM Sans', sans-serif",
          fontSize: '12px',
          color: 'var(--text-muted)',
        }}
      >
        Try one of these
      </span>
      <div role="group" aria-labelledby="suggested-questions-label" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {DEMO_QUESTIONS.map(({ label, question }) => (
          <button
            key={label}
            type="button"
            data-testid="suggested-question"
            onClick={() => onPick(question)}
            style={{
              fontFamily: "'DM Sans', sans-serif",
              fontSize: '13px',
              padding: '6px 12px',
              borderRadius: '999px',
              border: '1px solid var(--border-color)',
              backgroundColor: 'var(--bg-card)',
              color: 'var(--text-secondary)',
              cursor: 'pointer',
            }}
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
