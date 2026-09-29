import { DEMO_QUESTIONS } from '../lib/demoQuestions'

type SuggestedQuestionsProps = {
  onPick: (question: string) => void
}

export function SuggestedQuestions({ onPick }: SuggestedQuestionsProps) {
  return (
    <div style={{ padding: '20px 24px 0' }}>
      <div role="group" aria-label="Suggested questions" style={{ display: 'flex', flexWrap: 'wrap', gap: '8px' }}>
        {DEMO_QUESTIONS.map(({ label, question }) => (
          <button
            key={label}
            type="button"
            data-testid="suggested-question"
            onClick={() => onPick(question)}
            className="suggested-chip"
          >
            {label}
          </button>
        ))}
      </div>
    </div>
  )
}
